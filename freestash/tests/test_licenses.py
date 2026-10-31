from datetime import date

import pytest

from freestash.licenses import evaluate, evaluate_all, lookup, normalize_license, us_public_domain_cutoff
from freestash.models import MediaType, Tier, Trust, UseCase

from .conftest import make_asset

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


@pytest.mark.parametrize("lic,trust,expected", [
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
])
def test_policy_matrix(lic, trust, expected):
    verdicts = evaluate_all(make_asset(lic, trust=trust))
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
