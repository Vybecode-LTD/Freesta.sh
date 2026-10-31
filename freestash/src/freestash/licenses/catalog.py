"""License facts. Pure data: what each license permits. Verdicts live in policy.py.

IDs follow SPDX where SPDX has one (CC0-1.0, CC-BY-4.0, OFL-1.1, MIT ...). Non-SPDX statuses
use descriptive IDs (PDM-1.0, PD-US-GOV, NOC-US, UNSPLASH ...). Versioned Creative Commons
IDs ("CC-BY-SA-3.0") resolve to their base entry ("CC-BY-SA") via `lookup`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

Redistribute = Literal["yes", "with_notice", "no"]
Merch = Literal["yes", "modified_only", "no"]
Family = Literal["public_domain", "creative_commons", "open_source", "font", "platform", "restricted", "unknown"]


@dataclass(frozen=True)
class LicenseDef:
    id: str
    label: str
    family: Family
    url: str | None = None
    commercial: bool = True
    derivatives: bool = True
    attribution: bool = False
    share_alike: bool = False
    copyleft: bool = False  # software-style copyleft (GPL/MPL); differs from CC ShareAlike in scope
    redistribute: Redistribute = "yes"  # may the raw file ship inside a product / pack / template download?
    merch: Merch = "yes"
    is_claim: bool = False  # a statement that something is PD (PDM, NoC), not a grant by a rights holder
    notes: tuple[str, ...] = field(default_factory=tuple)


_CC = "https://creativecommons.org/licenses"

_DEFS: list[LicenseDef] = [
    # ---- public domain ------------------------------------------------------------------
    LicenseDef("CC0-1.0", "CC0 1.0", "public_domain",
               "https://creativecommons.org/publicdomain/zero/1.0/"),
    LicenseDef("PDM-1.0", "Public Domain Mark 1.0", "public_domain",
               "https://creativecommons.org/publicdomain/mark/1.0/", is_claim=True,
               notes=("PDM is a label saying the work is free of known copyright, not a waiver; status can differ by country.",)),
    LicenseDef("PD-US-GOV", "Public domain (US federal government work)", "public_domain",
               "https://www.usa.gov/government-copyright",
               notes=("US federal works are public domain in the US; protection abroad can differ.",
                      "Don't imply government endorsement; agency logos and insignia are restricted.")),
    LicenseDef("NOC-US", "No Copyright – United States", "public_domain",
               "https://rightsstatements.org/vocab/NoC-US/1.0/", is_claim=True,
               notes=("Public domain in the United States only; check other markets before distributing abroad.",)),
    LicenseDef("NKC", "No Known Copyright", "public_domain",
               "https://rightsstatements.org/vocab/NKC/1.0/", is_claim=True,
               notes=("The institution believes it is free to use but makes no guarantee.",)),
    LicenseDef("Unlicense", "The Unlicense", "public_domain", "https://unlicense.org/"),
    LicenseDef("WTFPL", "WTFPL", "public_domain", "http://www.wtfpl.net/"),
    # ---- creative commons (base entries; versions resolve here) ----------------------------
    LicenseDef("CC-BY", "CC BY", "creative_commons", f"{_CC}/by/4.0/", attribution=True),
    LicenseDef("CC-BY-SA", "CC BY-SA", "creative_commons", f"{_CC}/by-sa/4.0/", attribution=True, share_alike=True),
    LicenseDef("CC-BY-ND", "CC BY-ND", "creative_commons", f"{_CC}/by-nd/4.0/", attribution=True, derivatives=False),
    LicenseDef("CC-BY-NC", "CC BY-NC", "creative_commons", f"{_CC}/by-nc/4.0/", attribution=True, commercial=False),
    LicenseDef("CC-BY-NC-SA", "CC BY-NC-SA", "creative_commons", f"{_CC}/by-nc-sa/4.0/", attribution=True,
               commercial=False, share_alike=True),
    LicenseDef("CC-BY-NC-ND", "CC BY-NC-ND", "creative_commons", f"{_CC}/by-nc-nd/4.0/", attribution=True,
               commercial=False, derivatives=False),
    LicenseDef("CC-SAMPLING+", "CC Sampling Plus (retired)", "creative_commons",
               f"{_CC}/sampling+/1.0/", attribution=True, redistribute="no", merch="no",
               notes=("Retired license; whole-work commercial use is not allowed, only transformed samples.",)),
    # ---- software / icon licenses ----------------------------------------------------------
    LicenseDef("MIT", "MIT License", "open_source", "https://opensource.org/license/mit", redistribute="with_notice"),
    LicenseDef("ISC", "ISC License", "open_source", "https://opensource.org/license/isc-license-txt",
               redistribute="with_notice"),
    LicenseDef("BSD-2-Clause", "BSD 2-Clause", "open_source", "https://opensource.org/license/bsd-2-clause",
               redistribute="with_notice"),
    LicenseDef("BSD-3-Clause", "BSD 3-Clause", "open_source", "https://opensource.org/license/bsd-3-clause",
               redistribute="with_notice"),
    LicenseDef("Apache-2.0", "Apache License 2.0", "open_source", "https://www.apache.org/licenses/LICENSE-2.0",
               redistribute="with_notice"),
    LicenseDef("MPL-2.0", "Mozilla Public License 2.0", "open_source", "https://www.mozilla.org/MPL/2.0/",
               redistribute="with_notice", copyleft=True,
               notes=("File-level copyleft: modified MPL files must stay MPL.",)),
    LicenseDef("LGPL", "GNU LGPL", "open_source", "https://www.gnu.org/licenses/lgpl-3.0.html",
               redistribute="with_notice", copyleft=True),
    LicenseDef("GPL", "GNU GPL", "open_source", "https://www.gnu.org/licenses/gpl-3.0.html",
               redistribute="with_notice", copyleft=True,
               notes=("Strong copyleft: bundling GPL assets can pull the combined work under the GPL.",)),
    # ---- fonts ----------------------------------------------------------------------------
    LicenseDef("OFL-1.1", "SIL Open Font License 1.1", "font", "https://openfontlicense.org/",
               redistribute="with_notice",
               notes=("Embed and bundle freely; don't sell the font files on their own.",
                      "Modified versions can't use the font's Reserved Font Name.")),
    LicenseDef("UFL-1.0", "Ubuntu Font Licence 1.0", "font", "https://ubuntu.com/legal/font-licence",
               redistribute="with_notice"),
    # ---- platform "free to use" licenses ---------------------------------------------------
    LicenseDef("UNSPLASH", "Unsplash License", "platform", "https://unsplash.com/license",
               redistribute="no", merch="modified_only",
               notes=("Can't compile Unsplash photos into a similar or competing service.",
                      "Can't sell unaltered copies; recognizable people, brands, and property aren't released.")),
    LicenseDef("PEXELS", "Pexels License", "platform", "https://www.pexels.com/license/",
               redistribute="no", merch="modified_only",
               notes=("Can't redistribute on stock/wallpaper platforms or sell unaltered copies.",
                      "Don't imply endorsement by identifiable people or brands.")),
    LicenseDef("PIXABAY", "Pixabay Content License", "platform", "https://pixabay.com/service/license-summary/",
               redistribute="no", merch="modified_only",
               notes=("Can't distribute or sell content standalone; trademarks, logos, and brands are excluded.",)),
    # ---- restricted / unknown -------------------------------------------------------------
    LicenseDef("VAM-TERMS", "V&A image terms (non-commercial)", "restricted",
               "https://www.vam.ac.uk/info/va-websites-terms-conditions", commercial=False,
               redistribute="no", merch="no",
               notes=("Free for personal and educational use; commercial use needs a paid V&A license.",)),
    LicenseDef("IN-COPYRIGHT", "In copyright", "restricted", "https://rightsstatements.org/vocab/InC/1.0/",
               commercial=False, derivatives=False, redistribute="no", merch="no"),
    LicenseDef("RIGHTS-UNKNOWN", "Rights not determined", "unknown", None,
               commercial=False, derivatives=False, redistribute="no", merch="no",
               notes=("No usable license information; treat as all rights reserved until verified.",)),
]

CATALOG: dict[str, LicenseDef] = {d.id: d for d in _DEFS}

_VERSION_SUFFIX = re.compile(r"-(\d+(\.\d+)*)(-(only|or-later|igo))?$", re.IGNORECASE)


def base_id(license_id: str) -> str:
    """'CC-BY-SA-3.0' -> 'CC-BY-SA'; 'GPL-3.0-or-later' -> 'GPL'; 'CC0-1.0' stays (it's in the catalog)."""
    if license_id in CATALOG:
        return license_id
    stripped = _VERSION_SUFFIX.sub("", license_id)
    if stripped.upper().startswith("LGPL"):
        return "LGPL"
    if stripped.upper().startswith("GPL") or stripped.upper().startswith("AGPL"):
        return "GPL"
    return stripped


def lookup(license_id: str) -> LicenseDef:
    return CATALOG.get(license_id) or CATALOG.get(base_id(license_id)) or CATALOG["RIGHTS-UNKNOWN"]


def is_public_domain(license_id: str) -> bool:
    return lookup(license_id).family == "public_domain"
