from datetime import date

import pytest

from freestash.licenses import evaluate, evaluate_all, lookup, normalize_license, us_public_domain_cutoff
from freestash.models import Asset, MediaType, Tier, Trust, UseCase

from .conftest import load, make_asset

# ----------------------------------------------------------------------------- normalization


@pytest.mark.parametrize("raw,url,version,expected", [
    (None, "https://creativecommons.org/publicdomain/zero/1.0/", None, "CC0-1.0"),
    (None, "http://creativecommons.org/publicdomain/mark/1.0/", None, "PDM-1.0"),
    (None, "http://creativecommons.org/licenses/by-sa/3.0/", None, "CC-BY-SA-3.0"),
    (None, "https://creativecommons.org/licenses/by-nc-nd/4.0/deed.en", None, "CC-BY-NC-ND-4.0"),
    (None, "http://rightsstatements.org/vocab/NoC-US/1.0/", None, "NOC-US"),
    (None, "http://rightsstatements.org/vocab/InC/1.0/", None, "IN-COPYRIGHT"),
    (None, "https://unsplash.com/license", None, "UNSPLASH"),
    (None, "https://openfontlicense.org/", None, "OFL-1.1"),
    ("by-nc-sa", None, "2.0", "CC-BY-NC-SA-2.0"),  # Openverse style
    ("cc0", None, "1.0", "CC0-1.0"),
    ("pdm", None, None, "PDM-1.0"),
    ("CC BY-SA 4.0", None, None, "CC-BY-SA-4.0"),  # Wikimedia LicenseShortName
    ("CC-BY-4.0", None, None, "CC-BY-4.0"),  # SPDX
    ("Attribution Noncommercial 4.0", None, None, "CC-BY-NC-4.0"),  # Freesound prose
    ("OFL-1.1", None, None, "OFL-1.1"),
    ("Apache-2.0", None, None, "Apache-2.0"),
    ("GPL-3.0-or-later", None, None, "GPL-3.0-or-later"),
    ("Public domain", None, None, "PDM-1.0"),
    ("totally made up", None, None, "RIGHTS-UNKNOWN"),
    (None, None, None, "RIGHTS-UNKNOWN"),
])
def test_normalize(raw, url, version, expected):
    assert normalize_license(raw, url, version).id == expected


def test_versioned_ids_resolve_to_base_entries():
    assert lookup("CC-BY-SA-3.0").id == "CC-BY-SA"
    assert lookup("GPL-2.0-only").id == "GPL"
    assert lookup("nonsense").id == "RIGHTS-UNKNOWN"


def test_versioned_label_and_url():
    lic = normalize_license("CC BY 3.0")
    assert lic.label == "CC BY 3.0"
    assert lic.url == "https://creativecommons.org/licenses/by/3.0/"


# ----------------------------------------------------------------------------- policy matrix

GREEN, YELLOW, RED = Tier.GREEN, Tier.YELLOW, Tier.RED


_MATRIX = [
    #                                       reference demo   client  bundled merch
    ("CC0-1.0", Trust.INSTITUTION, (GREEN, GREEN, GREEN, GREEN, GREEN)),
    ("CC0-1.0", Trust.UPLOADER, (GREEN, GREEN, YELLOW, YELLOW, YELLOW)),
    ("CC-BY-4.0", Trust.COMMUNITY, (GREEN, GREEN, GREEN, GREEN, GREEN)),
    ("CC-BY-SA-4.0", Trust.COMMUNITY, (GREEN, GREEN, YELLOW, YELLOW, YELLOW)),
    ("CC-BY-ND-4.0", Trust.COMMUNITY, (GREEN, YELLOW, YELLOW, RED, RED)),
    ("CC-BY-NC-4.0", Trust.COMMUNITY, (YELLOW, RED, RED, RED, RED)),
    ("UNSPLASH", Trust.COMMUNITY, (GREEN, GREEN, GREEN, RED, YELLOW)),
    ("PEXELS", Trust.COMMUNITY, (GREEN, GREEN, GREEN, RED, YELLOW)),
    ("OFL-1.1", Trust.CURATED, (GREEN, GREEN, GREEN, GREEN, GREEN)),
    ("MIT", Trust.COMMUNITY, (GREEN, GREEN, GREEN, GREEN, GREEN)),
    ("GPL-3.0-or-later", Trust.COMMUNITY, (GREEN, GREEN, YELLOW, YELLOW, GREEN)),
    ("VAM-TERMS", Trust.INSTITUTION, (YELLOW, RED, RED, RED, RED)),
    ("IN-COPYRIGHT", Trust.INSTITUTION, (YELLOW, RED, RED, RED, RED)),
    ("RIGHTS-UNKNOWN", Trust.UNKNOWN, (YELLOW, RED, RED, RED, RED)),
    ("PD-US-GOV", Trust.GOVERNMENT, (GREEN, GREEN, GREEN, GREEN, GREEN)),
    ("NKC", Trust.INSTITUTION, (GREEN, GREEN, YELLOW, YELLOW, YELLOW)),
    ("PIXABAY", Trust.COMMUNITY, (GREEN, GREEN, GREEN, RED, YELLOW)),
]

# A brush: client and merch judge the artwork made with it, bundled judges the brush file (contract packs-and-new-kinds).
_BRUSH_MATRIX = [
    #                                       reference demo   client  bundled merch
    ("PIXABAY", Trust.COMMUNITY, (GREEN, GREEN, GREEN, RED, GREEN)),  # painted artwork is never an unaltered copy
    ("CC-BY-ND-4.0", Trust.COMMUNITY, (GREEN, YELLOW, YELLOW, RED, RED)),  # brushes loosen nothing else
    ("CC-BY-SA-4.0", Trust.COMMUNITY, (GREEN, GREEN, YELLOW, YELLOW, YELLOW)),
    ("CC-BY-NC-4.0", Trust.COMMUNITY, (YELLOW, RED, RED, RED, RED)),
    ("CC0-1.0", Trust.UPLOADER, (GREEN, GREEN, YELLOW, YELLOW, YELLOW)),
]


@pytest.mark.parametrize("lic,trust,expected,media", [(*r, MediaType.IMAGE) for r in _MATRIX]
                         + [(*r, MediaType.BRUSH) for r in _BRUSH_MATRIX])
def test_policy_matrix(lic, trust, expected, media):
    verdicts = evaluate_all(make_asset(lic, trust=trust, media=media))
    got = tuple(verdicts[u].tier for u in (UseCase.REFERENCE, UseCase.DEMO, UseCase.CLIENT, UseCase.BUNDLED, UseCase.MERCH))
    assert got == expected, {u.value: (v.tier.value, v.reasons) for u, v in verdicts.items()}


def test_every_non_green_verdict_explains_itself():
    for lic in ("CC-BY-NC-4.0", "UNSPLASH", "CC-BY-SA-4.0", "RIGHTS-UNKNOWN"):
        for v in evaluate_all(make_asset(lic, trust=Trust.COMMUNITY)).values():
            assert v.reasons, (lic, v)


def test_attribution_obligation_for_cc_by():
    v = evaluate(make_asset("CC-BY-4.0"), UseCase.BUNDLED)
    assert any("Credit required" in o for o in v.obligations)


def test_with_notice_licenses_require_license_file_when_bundled():
    v = evaluate(make_asset("MIT"), UseCase.BUNDLED)
    assert any("license text" in o for o in v.obligations)



def test_brush_says_what_client_and_merch_judge():
    note = "This covers artwork you make with the brush; shipping the brush file is judged under Bundled."
    verdicts = evaluate_all(make_asset("CC0-1.0", trust=Trust.CURATED, media=MediaType.BRUSH))
    assert [u for u, v in verdicts.items() if note in v.reasons] == [UseCase.CLIENT, UseCase.MERCH]
    assert all(v.tier == GREEN for v in verdicts.values())


# ----------------------------------------------------------------------------- packs

def make_pack(members: list[str], *, trust: Trust = Trust.UPLOADER, checked: int | None = None,
              count: int | None = None) -> Asset:
    """A pack whose files are licensed one by one (`checked` of `count` read); `members` empty = one pack-wide licence."""
    lics = [normalize_license(m) for m in members]
    # `license` is the laxest member here on purpose: the verdict must come from every member, not from `license`
    asset = make_asset(members[0] if members else "CC0-1.0", trust=trust, media=MediaType.AUDIO)
    return asset.model_copy(update={"is_pack": True, "item_count": count, "member_licenses": lics,
                                    "members_checked": checked if checked is not None else (len(lics) if lics else None)})


@pytest.mark.parametrize("members,trust,checked,count,expected", [
    #                                                            reference demo   client  bundled merch
    (["CC0-1.0", "CC-BY-NC-4.0"], Trust.UPLOADER, 2, 2, (YELLOW, RED, RED, RED, RED)),  # the strictest file wins
    (["CC0-1.0", "CC-BY-4.0"], Trust.COMMUNITY, 2, 2, (GREEN, GREEN, GREEN, GREEN, GREEN)),
    (["CC0-1.0", "CC-BY-4.0"], Trust.UPLOADER, 2, 2, (GREEN, GREEN, YELLOW, YELLOW, YELLOW)),
    (["CC-BY-SA-4.0", "CC-BY-ND-4.0"], Trust.COMMUNITY, 2, 2, (GREEN, YELLOW, YELLOW, RED, RED)),
    (["CC0-1.0"], Trust.INSTITUTION, 1, 24, (GREEN, YELLOW, YELLOW, YELLOW, YELLOW)),  # 23 files unread: check at best,
    (["CC0-1.0"], Trust.INSTITUTION, 3, None, (GREEN, YELLOW, YELLOW, YELLOW, YELLOW)),  # but reference stays as its files
    ([], Trust.CURATED, None, 40, (GREEN, GREEN, GREEN, GREEN, GREEN)),  # one licence for the pack, its publisher's
])
def test_pack_policy_matrix(members, trust, checked, count, expected):
    verdicts = evaluate_all(make_pack(members, trust=trust, checked=checked, count=count))
    got = tuple(verdicts[u].tier for u in (UseCase.REFERENCE, UseCase.DEMO, UseCase.CLIENT, UseCase.BUNDLED, UseCase.MERCH))
    assert got == expected, {u.value: (v.tier.value, v.reasons) for u, v in verdicts.items()}


def test_pack_merges_every_files_obligations():
    v = evaluate(make_pack(["CC0-1.0", "CC-BY-4.0"], trust=Trust.COMMUNITY), UseCase.BUNDLED)
    assert any("Credit required" in o for o in v.obligations)


def test_reference_is_not_held_back_by_unread_files():
    v = evaluate(make_pack(["CC0-1.0"], trust=Trust.INSTITUTION, checked=1, count=24), UseCase.REFERENCE)
    assert v.tier == GREEN and not any("Licenses were read" in r for r in v.reasons)


def test_incomplete_pack_says_how_much_was_read():
    v = evaluate(make_pack(["CC0-1.0"], trust=Trust.INSTITUTION, checked=1, count=24), UseCase.DEMO)
    assert "Licenses were read for 1 of 24 files in this pack: check the rest on its page." in v.reasons
    v = evaluate(make_pack(["CC0-1.0"], trust=Trust.INSTITUTION, checked=3), UseCase.DEMO)
    assert "Licenses were read for 3 files in this pack, which may hold more: check the rest on its page." in v.reasons

@pytest.mark.parametrize("repo,expected", [
    #                                                    reference demo   client  bundled merch
    ("kweezl/spacecraft-resources", (GREEN, GREEN, YELLOW, YELLOW, YELLOW)),  # MIT, asserted by the repo's owner
    ("KayKit-Game-Assets/KayKit-Space-Base-Bits-1.0", (YELLOW, RED, RED, RED, RED)),  # a license GitHub can't identify
    ("RhysBoxGameStudios/space-station-assets", (YELLOW, RED, RED, RED, RED)),  # no license file
])
def test_github_packs_are_uploader_trust_under_the_repos_license(repo, expected):
    """No policy change (contract github-and-curated-packs): uploader trust already holds shipped uses at Check."""
    from freestash.providers.github import parse_github_repo

    item = next(i for i in load("github_search")["items"] if i["full_name"] == repo)
    verdicts = evaluate_all(parse_github_repo(item))
    got = tuple(verdicts[u].tier for u in (UseCase.REFERENCE, UseCase.DEMO, UseCase.CLIENT, UseCase.BUNDLED, UseCase.MERCH))
    assert got == expected, {u.value: (v.tier.value, v.reasons) for u, v in verdicts.items()}
    if expected[1] == GREEN:
        bundled = verdicts[UseCase.BUNDLED].obligations
        assert any("license text" in o for o in bundled) and any("check the README" in o for o in bundled)


def test_a_curated_pack_is_clear_everywhere_under_its_recorded_cc0():
    from freestash.models import CuratedPack
    from freestash.providers.curated import curated_asset

    pack = CuratedPack(id="1", title="Space Kit", url="https://kenney.nl/assets/space-kit", publisher="Kenney",
                       license_id="CC0-1.0", license_checked_on=date(2026, 11, 4), media_type=MediaType.MODEL)
    assert all(v.tier == GREEN for v in evaluate_all(curated_asset(pack)).values())


# ----------------------------------------------------------------------------- public-domain date heuristic

def test_pd_cutoffs_track_the_calendar():
    assert us_public_domain_cutoff(MediaType.IMAGE, date(2026, 10, 30)) == 1930
    assert us_public_domain_cutoff(MediaType.AUDIO, date(2026, 10, 30)) == 1925
    assert us_public_domain_cutoff(MediaType.IMAGE, date(2027, 1, 1)) == 1931


def test_recent_work_marked_public_domain_is_flagged():
    """Live probe found a 2025 TV clip on Internet Archive marked PDM. That must not come back GREEN."""
    asset = make_asset("PDM-1.0", trust=Trust.UPLOADER, media=MediaType.VIDEO, year=2025)
    for use in (UseCase.DEMO, UseCase.CLIENT, UseCase.BUNDLED):
        v = evaluate(asset, use, today=date(2026, 10, 30))
        assert v.tier == Tier.YELLOW
        assert any("dated 2025" in r for r in v.reasons)


def test_old_pd_work_from_institution_is_green():
    v = evaluate(make_asset("PDM-1.0", trust=Trust.INSTITUTION, year=1846), UseCase.BUNDLED, today=date(2026, 10, 30))
    assert v.tier == Tier.GREEN


def test_cc0_ignores_dates():
    """CC0 is a waiver by the rights holder, so a recent date is fine."""
    v = evaluate(make_asset("CC0-1.0", trust=Trust.CURATED, year=2024), UseCase.BUNDLED)
    assert v.tier == Tier.GREEN


def test_us_gov_works_are_exempt_from_date_check():
    v = evaluate(make_asset("PD-US-GOV", trust=Trust.GOVERNMENT, year=2026), UseCase.CLIENT)
    assert v.tier == Tier.GREEN
    assert any("endorsement" in o for o in v.obligations)


def test_recording_from_1924_ok_but_1927_flagged():
    ok = evaluate(make_asset("PDM-1.0", media=MediaType.AUDIO, year=1924), UseCase.BUNDLED, today=date(2026, 10, 30))
    late = evaluate(make_asset("PDM-1.0", media=MediaType.AUDIO, year=1927), UseCase.BUNDLED, today=date(2026, 10, 30))
    assert ok.tier == Tier.GREEN and late.tier == Tier.YELLOW
    assert any("composition" in o for o in ok.obligations)


# ----------------------------------------------------------------------------- attribution

def test_attribution_formats():
    pd = evaluate(make_asset("CC0-1.0"), UseCase.DEMO).attribution
    assert pd.startswith("“Test Asset” by Someone, via test") and "CC0" in pd
    by = evaluate(make_asset("CC-BY-4.0"), UseCase.DEMO).attribution
    assert "is licensed under CC BY 4.0" in by and "https://example.com/a/1" in by
    unsplash = evaluate(make_asset("UNSPLASH"), UseCase.DEMO).attribution
    assert unsplash == "Photo by Someone on Unsplash"
