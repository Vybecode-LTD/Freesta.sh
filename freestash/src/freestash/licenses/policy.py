"""The verdict engine: license × trust × use case (+ date heuristics) -> Tier with reasons.

Design rules
------------
* GREEN means "go, and do what the obligations list says". It never hides an obligation.
* YELLOW means a human has to check or decide something that could reasonably come out either way.
* RED means don't, for this use case. The same asset can be GREEN for DEMO and RED for BUNDLED.
* Every tier bump appends a plain-English reason, so the UI can show *why*.

This is a risk-triage tool, not legal advice. When in doubt it errs toward YELLOW.
"""

from __future__ import annotations

from datetime import date

from freestash.licenses.attribution import build_attribution
from freestash.licenses.catalog import LicenseDef, lookup
from freestash.models import Asset, LicenseInfo, MediaType, Tier, Trust, UseCase, Verdict

SHIPPED = {UseCase.CLIENT, UseCase.BUNDLED, UseCase.MERCH}  # uses where a mistake costs real money
ARTWORK = {UseCase.CLIENT, UseCase.MERCH}  # for a brush these judge what you paint with it; BUNDLED judges the file
BRUSH_NOTE = "This covers artwork you make with the brush; shipping the brush file is judged under Bundled."


def us_public_domain_cutoff(media_type: MediaType, today: date | None = None) -> int:
    """Latest publication year that is reliably public domain in the US as of `today`.

    * Most published works: 95-year term, entering the public domain each Jan 1
      (Jan 1 2026 -> works published in 1930 and earlier).
    * Sound recordings (Music Modernization Act): pre-1923 entered PD in 2022; 1923–1946
      recordings get 100 years (Jan 1 2026 -> recordings published in 1925 and earlier).
      Remember the *composition* in a recording has its own, separate copyright.
    """
    today = today or date.today()
    return today.year - (101 if media_type == MediaType.AUDIO else 96)


class _Acc:
    def __init__(self) -> None:
        self.tier = Tier.GREEN
        self.reasons: list[str] = []
        self.obligations: list[str] = []

    def bump(self, tier: Tier, reason: str) -> None:
        if tier.rank > self.tier.rank:
            self.tier = tier
        if reason not in self.reasons:
            self.reasons.append(reason)

    def oblige(self, text: str) -> None:
        if text not in self.obligations:
            self.obligations.append(text)


def _license_rules(acc: _Acc, lic: LicenseDef, use: UseCase, label: str, brush: bool = False) -> None:
    if lic.id in ("RIGHTS-UNKNOWN", "IN-COPYRIGHT"):
        if use == UseCase.REFERENCE:
            acc.bump(Tier.YELLOW, f"{label}: fine to look at internally, but it can't go into anything you ship or show.")
        else:
            acc.bump(Tier.RED, f"{label}: no license that allows this use.")
        return

    if not lic.commercial:
        if use == UseCase.REFERENCE:
            acc.bump(Tier.YELLOW, f"{label} is non-commercial: internal reference only.")
        else:
            acc.bump(Tier.RED, f"{label} forbids commercial use.")
        return

    if use == UseCase.REFERENCE:
        return  # anything commercial-OK is fine for internal reference

    if not lic.derivatives:
        if use in (UseCase.DEMO, UseCase.CLIENT):
            acc.bump(Tier.YELLOW, f"{label} allows no derivatives: use it unmodified (no crops, filters, or overlays).")
        else:
            acc.bump(Tier.RED, f"{label} allows no derivatives, which rules out bundling or merch.")

    if use == UseCase.BUNDLED:
        if lic.redistribute == "no":
            acc.bump(Tier.RED, f"{label} doesn't allow redistributing the file itself (template downloads, "
                               "sample packs, and app bundles all count). Ship a placeholder or link instead.")
        elif lic.redistribute == "with_notice":
            acc.oblige(f"Ship the {label} license text alongside the file.")

    if use == UseCase.MERCH:
        if lic.merch == "no":
            acc.bump(Tier.RED, f"{label} doesn't allow use on goods for sale.")
        elif lic.merch == "modified_only" and not brush:  # painted artwork is never an unaltered copy of the brush
            acc.bump(Tier.YELLOW, f"{label} only allows merch if the image is substantially modified, not a straight print.")

    if lic.share_alike:
        if use == UseCase.DEMO:
            acc.oblige("ShareAlike: if you modify it, the modified version must be released under the same license.")
        else:
            acc.bump(Tier.YELLOW, "ShareAlike: the file and any modified version must stay under the same license. "
                                  "Keep it separable from proprietary content, and make sure the client or product can accept that.")

    if lic.copyleft and use in (UseCase.CLIENT, UseCase.BUNDLED):
        acc.bump(Tier.YELLOW, f"{label} is copyleft; check how it combines with the rest of the project.")

    if lic.attribution:
        where = {UseCase.DEMO: "on the page or a credits page", UseCase.CLIENT: "on the site or in the credits",
                 UseCase.BUNDLED: "in the product's credits/ATTRIBUTION file", UseCase.MERCH: "on the listing or tag"}[use]
        acc.oblige(f"Credit required {where}.")


def _trust_rules(acc: _Acc, asset: Asset, lic: LicenseDef, use: UseCase, today: date | None) -> None:
    if use == UseCase.REFERENCE:
        return

    # PD claims (PDM, NoC, plain "public domain") depend on dates; CC0 is a waiver, so dates don't matter.
    pd_claim = lic.is_claim or (lic.family == "public_domain" and lic.id not in ("CC0-1.0", "Unlicense", "WTFPL"))
    if pd_claim and asset.trust != Trust.GOVERNMENT and lic.id != "PD-US-GOV" and asset.year:
        cutoff = us_public_domain_cutoff(asset.media_type, today)
        if asset.year > cutoff:
            kind = "sound recordings" if asset.media_type == MediaType.AUDIO else "works"
            acc.bump(Tier.YELLOW, f"Marked public domain but dated {asset.year}; US public domain currently covers {kind} "
                                  f"published in {cutoff} or earlier. It might be a government work, never registered or "
                                  "renewed, or just mislabeled. Verify before relying on it.")

    if lic.id == "NKC" and use in SHIPPED:
        acc.bump(Tier.YELLOW, "\"No Known Copyright\" is the institution's best guess, not a guarantee.")

    if asset.trust in (Trust.UPLOADER, Trust.UNKNOWN):
        msg = ("License is asserted by whoever uploaded it, not verified by the platform. "
               "Check the source page (and that the uploader actually owns it).")
        if use in SHIPPED:
            acc.bump(Tier.YELLOW, msg)
        elif msg not in acc.reasons:
            acc.reasons.append(msg)

    if asset.media_type == MediaType.AUDIO and pd_claim and use in SHIPPED:
        acc.oblige("Recordings have two copyrights: the recording and the composition. Both must be public domain.")


def _pack_rules(acc: _Acc, asset: Asset) -> None:
    """A pack licensed file by file is cleared only as far as its files' licenses were read (not for reference use,
    which is judged on the licenses that were read, as for any asset)."""
    checked, count = asset.members_checked or 0, asset.item_count
    if count is None:
        acc.bump(Tier.YELLOW, f"Licenses were read for {checked} files in this pack, which may hold more: "
                              "check the rest on its page.")
    elif checked < count:
        acc.bump(Tier.YELLOW, f"Licenses were read for {checked} of {count} files in this pack: check the rest on its page.")


def evaluate(asset: Asset, use: UseCase, today: date | None = None) -> Verdict:
    """A per-file pack (`members_checked` set) is judged against every member license: the strictest wins."""
    per_file = asset.is_pack and asset.members_checked is not None
    infos: list[LicenseInfo] = (asset.member_licenses or [asset.license]) if per_file else [asset.license]
    brush = asset.media_type == MediaType.BRUSH
    acc = _Acc()

    lics = [lookup(info.id) for info in infos]
    for info, lic in zip(infos, lics, strict=True):
        _license_rules(acc, lic, use, info.label, brush)
        _trust_rules(acc, asset, lic, use, today)
    if per_file and use != UseCase.REFERENCE:
        _pack_rules(acc, asset)

    if use != UseCase.REFERENCE and acc.tier != Tier.RED:
        for note in (*(n for lic in lics for n in lic.notes), *asset.notes):
            acc.oblige(note)

    if acc.tier == Tier.GREEN and not acc.reasons:
        acc.reasons.append(_green_summary(lics[0], asset))
    if brush and use in ARTWORK:
        acc.reasons.append(BRUSH_NOTE)

    return Verdict(use_case=use, tier=acc.tier, reasons=acc.reasons, obligations=acc.obligations,
                   attribution=build_attribution(asset))


def evaluate_all(asset: Asset, today: date | None = None) -> dict[UseCase, Verdict]:
    return {u: evaluate(asset, u, today) for u in UseCase}


def strictest_license(licenses: list[LicenseInfo], trust: Trust, media: MediaType = MediaType.IMAGE) -> LicenseInfo:
    """The license that clears least across the uses (then: carries most obligations). A per-file pack shows it as its
    `license`; its verdict still comes from every member (`evaluate`)."""
    def weight(info: LicenseInfo) -> tuple[int, int]:
        probe = Asset(provider="pack", source_id="-", title="-", media_type=media, license=info, trust=trust)
        verdicts = evaluate_all(probe).values()
        return sum(v.tier.rank for v in verdicts), sum(len(v.obligations) for v in verdicts)
    return max(licenses, key=weight)


def _green_summary(lic: LicenseDef, asset: Asset) -> str:
    who = {
        Trust.INSTITUTION: "rights determination published by the institution",
        Trust.GOVERNMENT: "US government work",
        Trust.CURATED: "original content published by the platform",
        Trust.COMMUNITY: "community-reviewed",
    }.get(asset.trust, "")
    if lic.id == "PD-US-GOV" and asset.trust == Trust.GOVERNMENT:
        who = ""  # the label already says it
    return f"{asset.license.label}" + (f" ({who})" if who else "") + "."
