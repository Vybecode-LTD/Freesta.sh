# License policy

How Freestash turns "what the source says" into GREEN / YELLOW / RED. Code: `src/freestash/licenses/`.
Tests: `tests/test_licenses.py` (the matrix below is asserted there row by row).

> Risk triage, not legal advice. When the engine can't be sure, it says YELLOW and explains why.

## Three inputs

**1. License** (normalized from whatever the provider sends) → facts in `catalog.py`:
commercial use? derivatives? attribution? ShareAlike? copyleft? may the raw file be redistributed?
merch? is it a *claim* (PDM, NoC) rather than a grant (CC0)?

**2. Trust**: who's asserting it.

| Trust | Meaning | Examples |
|---|---|---|
| institution | Museum/library publishes its own rights determination | Met, AIC, Cleveland, SMK, Smithsonian, LoC, Europeana partners |
| government | US federal work (17 U.S.C. §105) | NASA, NPS |
| curated | Platform publishes its own original content | Poly Haven, ambientCG, Google Fonts via Fontsource |
| community | Community upload with review | Wikimedia Commons, Iconify sets, Pexels/Pixabay/Unsplash |
| uploader | Uploader-asserted, little review | Internet Archive, Freesound, Flickr via Openverse |
| unknown | Can't tell, or the credit line suggests a third party | NASA items credited to ESA/Getty/AP… |

**3. Use case**: what you'll do with it.

| Use | Meaning |
|---|---|
| reference | Mood boards, internal reference. Never shipped or shown publicly. |
| demo | Shown on demo/preview sites and mockups. Files aren't handed to customers. |
| client | A commercial client deliverable or production website. |
| bundled | The file ships inside a product: template download, plugin factory library, app bundle. |
| merch | Printed or pressed onto goods for sale. |

## The matrix

| License | Trust | reference | demo | client | bundled | merch |
|---|---|---|---|---|---|---|
| CC0 | institution | 🟢 | 🟢 | 🟢 | 🟢 | 🟢 |
| CC0 | uploader | 🟢 | 🟢 | 🟡 | 🟡 | 🟡 |
| CC BY | community | 🟢 | 🟢 | 🟢 | 🟢 | 🟢 |
| CC BY-SA | community | 🟢 | 🟢 | 🟡 | 🟡 | 🟡 |
| CC BY-ND | community | 🟢 | 🟡 | 🟡 | 🔴 | 🔴 |
| CC BY-NC (any NC) | any | 🟡 | 🔴 | 🔴 | 🔴 | 🔴 |
| Unsplash / Pexels / Pixabay | community | 🟢 | 🟢 | 🟢 | 🔴 | 🟡 |
| OFL-1.1 (fonts) | curated | 🟢 | 🟢 | 🟢 | 🟢 | 🟢 |
| MIT / Apache / ISC | community | 🟢 | 🟢 | 🟢 | 🟢 | 🟢 |
| GPL / LGPL / MPL | community | 🟢 | 🟢 | 🟡 | 🟡 | 🟢 |
| US government work | government | 🟢 | 🟢 | 🟢 | 🟢 | 🟢 |
| No Known Copyright | institution | 🟢 | 🟢 | 🟡 | 🟡 | 🟡 |
| V&A terms | institution | 🟡 | 🔴 | 🔴 | 🔴 | 🔴 |
| In copyright / unknown | any | 🟡 | 🔴 | 🔴 | 🔴 | 🔴 |

**Brushes** (`media_type: brush`): client and merch judge the artwork you paint with the brush; bundled judges the
brush file. The only difference that makes: a "modified only" merch clause doesn't hold a brush back, since painted
artwork is never an unaltered copy. Client and merch verdicts say so in their reasons.

| License | Trust | reference | demo | client | bundled | merch |
|---|---|---|---|---|---|---|
| Pixabay / Unsplash / Pexels (brush) | community | 🟢 | 🟢 | 🟢 | 🔴 | 🟢 |
| CC BY-ND (brush) | community | 🟢 | 🟡 | 🟡 | 🔴 | 🔴 |
| CC BY-SA (brush) | community | 🟢 | 🟢 | 🟡 | 🟡 | 🟡 |
| CC BY-NC (brush) | community | 🟡 | 🔴 | 🔴 | 🔴 | 🔴 |
| CC0 (brush) | uploader | 🟢 | 🟢 | 🟡 | 🟡 | 🟡 |

**Packs** (`is_pack`): one result holding many files. When the publisher states one license for the whole pack
(an Iconify set, an Internet Archive item), the pack is judged on it at the publisher's trust, like any asset.
When the source licenses each file (Freesound), the pack is judged against every distinct member license and the
strictest wins, reasons and obligations merged. If fewer files were read than the pack holds, or the count is
unknown, every use is 🟡 at best.

| Files inside | Trust | reference | demo | client | bundled | merch |
|---|---|---|---|---|---|---|
| CC0 + CC BY-NC | uploader | 🟡 | 🔴 | 🔴 | 🔴 | 🔴 |
| CC0 + CC BY | community | 🟢 | 🟢 | 🟢 | 🟢 | 🟢 |
| CC0 + CC BY | uploader | 🟢 | 🟢 | 🟡 | 🟡 | 🟡 |
| CC BY-SA + CC BY-ND | community | 🟢 | 🟡 | 🟡 | 🔴 | 🔴 |
| CC0, 1 of 24 files read | institution | 🟡 | 🟡 | 🟡 | 🟡 | 🟡 |
| One CC0 license for the pack | curated | 🟢 | 🟢 | 🟢 | 🟢 | 🟢 |

GREEN still carries obligations: credit lines for CC BY, a license file for MIT/OFL when bundled,
NASA's no-endorsement rule, Unsplash's download ping, and so on. The UI and MCP always show them.

## Why these calls

- **Platform licenses are RED for bundled.** Unsplash, Pexels, and Pixabay all forbid redistributing
  the files themselves or compiling them into a competing collection. A template download *is*
  redistribution. Use them on demo sites; ship placeholders in the download.
- **ShareAlike is YELLOW outside demos.** The file and any modified version must stay CC BY-SA. Fine
  when kept separable and credited; a problem if a client expects exclusive rights.
- **Uploader trust caps shipped uses at YELLOW.** Same license string, different reliability.
- **NC is RED everywhere but reference**, including "internal" business use, which is still commercial.

## The public-domain date heuristic

PD *claims* (PDM, "public domain", NoC, NKC) depend on dates; CC0 is a waiver and doesn't. For a claim on
an asset with a year, from a non-government source:

- works: published in `today.year − 96` or earlier (2026 → 1930; Jan 1 2027 → 1931)
- sound recordings: `today.year − 101` or earlier (2026 → 1925; Jan 1 2027 → 1926), per the Music
  Modernization Act schedule for 1923–1946 recordings

Anything newer → YELLOW with a reason. This exists because a live probe of Internet Archive found a
2025 TV clip marked Public Domain Mark. Audio PD claims also get the obligation that **both** the
recording and the composition must be public domain.

## Changing the policy

1. Edit `catalog.py` (facts) or `policy.py` (rules).
2. Add or adjust a row in `test_policy_matrix`.
3. Update the matrix above in the same commit.
4. If verdicts for existing ledger entries change meaningfully, note it in the changelog: the ledger
   keeps the verdict *as of retrieval*, by design.
