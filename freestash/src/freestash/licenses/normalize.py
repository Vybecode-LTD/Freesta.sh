"""Turn whatever a provider says about rights into a canonical LicenseInfo.

Inputs seen in the wild (all handled below):
  CC URLs ............ https://creativecommons.org/licenses/by-sa/3.0/   http://creativecommons.org/publicdomain/zero/1.0/
  rightsstatements ... http://rightsstatements.org/vocab/NoC-US/1.0/   .../InC/1.0/
  Openverse .......... license="by-nc-sa", license_version="2.0"   license="pdm"
  SPDX ............... CC0-1.0, CC-BY-4.0, OFL-1.1, GPL-3.0-or-later, Apache-2.0
  Prose .............. "CC BY-SA 4.0", "Public domain", "Attribution 4.0", "Creative Commons 0"
  Flags .............. Cleveland share_license_status="CC0", Met isPublicDomain=true
"""

from __future__ import annotations

import re

from freestash.licenses.catalog import CATALOG, base_id, lookup
from freestash.models import LicenseInfo

_CC_URL = re.compile(r"creativecommons\.org/licenses/([a-z+\-]+)/(\d+(?:\.\d+)?)", re.I)
_CC_PD_URL = re.compile(r"creativecommons\.org/publicdomain/(zero|mark)/(\d+(?:\.\d+)?)", re.I)
_RS_URL = re.compile(r"rightsstatements\.org/(?:vocab|page)/([A-Za-z\-]+)/", re.I)
_CC_PROSE = re.compile(r"\b(?:cc[\s\-]?)?(by(?:[\s\-](?:nc|sa|nd)){0,2})[\s\-]*(\d\.\d)?\b", re.I)

_SPDX_PASSTHROUGH = {
    "MIT", "ISC", "BSD-2-CLAUSE", "BSD-3-CLAUSE", "APACHE-2.0", "MPL-2.0", "OFL-1.1", "UNLICENSE", "WTFPL", "UFL-1.0",
}

_SIMPLE = {
    "cc0": "CC0-1.0", "cc0-1.0": "CC0-1.0", "cc-0": "CC0-1.0", "creative commons 0": "CC0-1.0",
    "creative commons zero": "CC0-1.0", "public domain dedication": "CC0-1.0",
    "pdm": "PDM-1.0", "pdm-1.0": "PDM-1.0", "public domain mark": "PDM-1.0",
    "public domain": "PDM-1.0", "public-domain": "PDM-1.0", "pd": "PDM-1.0",
    "pd-usgov": "PD-US-GOV", "pd-us-gov": "PD-US-GOV", "us government work": "PD-US-GOV",
    "unsplash": "UNSPLASH", "pexels": "PEXELS", "pixabay": "PIXABAY",
    "sampling+": "CC-SAMPLING+-1.0",
}

_URL_HINTS = [  # substring of a license URL -> license id (checked after CC / rightsstatements patterns)
    ("unsplash.com/license", "UNSPLASH"), ("pexels.com/license", "PEXELS"), ("pixabay.com/service/license", "PIXABAY"),
    ("pixabay.com/service/terms", "PIXABAY"), ("openfontlicense.org", "OFL-1.1"), ("scripts.sil.org/ofl", "OFL-1.1"),
    ("opensource.org/license/mit", "MIT"), ("opensource.org/licenses/mit", "MIT"), ("apache.org/licenses/license-2.0", "Apache-2.0"),
    ("opensource.org/license/isc", "ISC"), ("opensource.org/licenses/isc", "ISC"), ("mozilla.org/mpl/2.0", "MPL-2.0"),
    ("gnu.org/licenses/lgpl", "LGPL"), ("gnu.org/licenses/gpl", "GPL"), ("unlicense.org", "Unlicense"),
    ("usa.gov/government-copyright", "PD-US-GOV"), ("ubuntu.com/legal/font-licence", "UFL-1.0"),
    ("vam.ac.uk/info/va-websites-terms", "VAM-TERMS"),
]

_RS_MAP = {
    "noc-us": "NOC-US", "nkc": "NKC", "noc-nc": "IN-COPYRIGHT", "noc-oklr": "RIGHTS-UNKNOWN",
    "noc-cr": "RIGHTS-UNKNOWN", "inc": "IN-COPYRIGHT", "inc-edu": "IN-COPYRIGHT", "inc-nc": "IN-COPYRIGHT",
    "inc-ruu": "IN-COPYRIGHT", "inc-ow-eu": "IN-COPYRIGHT", "cne": "RIGHTS-UNKNOWN", "und": "RIGHTS-UNKNOWN",
}


def _cc_id(parts: str, version: str | None) -> str:
    parts = parts.lower().replace(" ", "-").strip("-")
    base = "CC-" + parts.upper()
    return f"{base}-{version}" if version else base


def _info(license_id: str, raw: str | None, url: str | None = None) -> LicenseInfo:
    d = lookup(license_id)
    version = license_id[len(base_id(license_id)):].lstrip("-") if license_id not in CATALOG else ""
    if d.family == "creative_commons" and version:
        label = f"{d.label} {version}"
    elif license_id != d.id and d.id != "RIGHTS-UNKNOWN":
        label = f"{d.label} ({license_id})"
    else:
        label = d.label
    if d.family == "creative_commons" and version and d.url:
        resolved_url = url or re.sub(r"/\d\.\d/$", f"/{version}/", d.url)
    else:
        resolved_url = url or d.url
    if d.id == "RIGHTS-UNKNOWN" and license_id != "RIGHTS-UNKNOWN":
        label = f"Unrecognized license ({license_id})"
    return LicenseInfo(id=license_id if d.id != "RIGHTS-UNKNOWN" else "RIGHTS-UNKNOWN",
                       label=label, url=resolved_url, raw=raw)


def normalize_license(raw: str | None = None, url: str | None = None, version: str | None = None) -> LicenseInfo:
    """Best-effort normalization. Unknown input returns RIGHTS-UNKNOWN (treated as all rights reserved)."""
    original = " | ".join(x for x in (raw, version, url) if x) or None
    for candidate in (url, raw):
        if not candidate:
            continue
        if m := _CC_PD_URL.search(candidate):
            return _info("CC0-1.0" if m.group(1).lower() == "zero" else "PDM-1.0", original, None)
        if m := _CC_URL.search(candidate):
            return _info(_cc_id(m.group(1), m.group(2)), original, None)
        if m := _RS_URL.search(candidate):
            return _info(_RS_MAP.get(m.group(1).lower(), "RIGHTS-UNKNOWN"), original, None)
        low_c = candidate.lower()
        for needle, lic_id in _URL_HINTS:
            if needle in low_c:
                return _info(lic_id, original, candidate if candidate.startswith("http") else None)

    if not raw:
        return _info("RIGHTS-UNKNOWN", original)
    text = raw.strip()
    low = text.lower()

    if low in _SIMPLE:
        return _info(_SIMPLE[low], original)
    if text.upper() in _SPDX_PASSTHROUGH:
        canon = next(k for k in CATALOG if k.upper() == text.upper())
        return _info(canon, original)
    if low.startswith(("gpl", "lgpl", "agpl")):
        return _info(text, original)
    if low.startswith("cc-by") or low.startswith("cc by") or re.fullmatch(r"by(-(nc|sa|nd))*", low):
        m = _CC_PROSE.search(low.replace("cc-by", "cc by"))
        if m:
            return _info(_cc_id(m.group(1), version or m.group(2)), original)
    if low.startswith("attribution"):  # Freesound/Flickr prose: "Attribution 4.0", "Attribution Noncommercial"
        parts = "by" + ("-nc" if "noncommercial" in low or "non-commercial" in low else "") + (
            "-sa" if "sharealike" in low or "share alike" in low else "") + (
            "-nd" if "noderiv" in low or "no deriv" in low else "")
        ver = re.search(r"(\d\.\d)", low)
        return _info(_cc_id(parts, ver.group(1) if ver else None), original)
    if "public domain" in low:
        return _info("PDM-1.0", original)
    return _info("RIGHTS-UNKNOWN", original)
