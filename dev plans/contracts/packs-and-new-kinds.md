---
feature: packs-and-new-kinds
status: done
approved: 2026-11-02 (decision 0003: the owner accepted plan §2, asks 1 and 5, and the order; "First job: PR #8" 2026-11-02)
plan: dev plans/2026-11-01-packs-web-admin-plan.md (§2, §3 asks 1 and 5, §4 step 4)
pr: 8
---

# Contract: packs, and brushes, shapes and sprites

## 1. Goal
A search can return **packs** (one result holding many files: an icon set, a Freesound pack, an Internet Archive
bundle) and three new kinds: **brushes, shapes and sprites**. A pack is cleared as strictly as its strictest file.
Both apps show packs first in each section, a "Packs" switch, pack words ("pack", "bundle") and a "Game assets" preset.

## 2. Interfaces
- **Models** (`models.py` ↔ `web/src/lib/types.ts` ↔ desktop `Models.cs`):
  - `MediaType` gains `brush`, `shape`, `sprite` (after `icon`).
  - `Asset` gains `is_pack: bool = False`, `item_count: int | None = None` (files in the pack, when known),
    `formats: list[str] = []` (lowercase extensions inside: `["wav", "mp3"]`), `member_licenses: list[LicenseInfo] = []`
    (the distinct licences of the files inside, when the source licenses each file) and `members_checked: int | None
    = None` (how many files' licences were read). `members_checked is None` means the pack's own `license` covers
    every file, stated by its publisher. For a per-file pack, `license` is the strictest member's.
  - `SearchQuery` gains `packs: bool = False`: **also look for packs**. It is not a filter: a result that is a pack
    by nature (an archive item) shows either way.
  - `QueryPick.media_type` becomes `MediaType | None`, and `QueryPick` gains `packs: bool = False`. A pack word's pick
    is `{word, media_type: null, packs: true}`. `ParsedQuery` gains `packs: bool = False`.
- **Policy** (`licenses/policy.py::evaluate`, ground rule 1):
  - A per-file pack: each use's tier is the strictest over `member_licenses`, each judged at the pack's trust; reasons
    and obligations are merged. If fewer files were read than it holds (or the count is unknown), every use but
    reference is YELLOW at best: `Licenses were read for 1 of 24 files in this pack: check the rest on its page.`
  - A brush (`media_type == brush`): CLIENT and MERCH judge the artwork made with it; BUNDLED judges the brush file.
    So a `merch: modified_only` licence doesn't hold back MERCH (artwork painted with a brush is never an unaltered
    copy), and CLIENT/MERCH say `This covers artwork you make with the brush; shipping the brush file is judged under
    Bundled.` Nothing else loosens: ND, NC, ShareAlike and uploader trust apply as before.
- **Engine**: `SearchHints.packs: bool = False`, set from the query by `Freestash._run`.
  - **Iconify**: with `packs`, sets from `/collections` (cached a day, hidden sets skipped) ranked with
    `design._score` lead its page. `source_id` `set:<prefix>`, `is_pack`, `item_count` = the set's total, `formats`
    `["svg", "json"]`, landing `https://icon-sets.iconify.design/<prefix>/`, one rendition
    `https://cdn.jsdelivr.net/npm/@iconify-json/<prefix>/icons.json` labelled `icons.json (every icon)`.
  - **Freesound**: with `packs`, the search asks `group_by_pack=1`; for up to 6 distinct `pack` URIs it reads
    `/packs/<id>/` (cached a day) and adds a pack: `source_id` `pack:<id>`, `item_count` = `num_sounds`, one member
    licence read (`members_checked` 1), `detail_required`. `get("pack:<id>")` reads `/packs/<id>/sounds/`
    (`page_size` 150) for the members' licences and formats. No renditions: a pack download needs a Freesound login.
  - **Internet Archive**: an item holding an archive (`ZIP`, `RAR`, `7z`) is a pack; `formats` come from its `format`
    list. With `packs` it adds a query for archive items. It covers `brush`, `shape` and `sprite` with one keyword
    query per kind (title/subject words, never software items), each hit taking that kind.
- **HTTP**: `GET /api/search/stream?…&packs=true`; `POST /api/search` takes `packs` in the body. Parse is unchanged in
  shape (`ParsedQuery.packs`).
- **CLI** `freestash search --packs`; a pack word turns it on and prints `Read "pack" as Packs`. **MCP**
  `search_assets(packs: bool = False)`; a pack word turns it on; `read_as` items carry `packs`.
- **`shared/categories.json`** gains the three categories (Brushes, Shapes, Sprites, with words), `pack_words` and
  `presets: [{id, label, media, packs}]` with `game-assets` = sprite, 3D, texture, audio, icon, font, packs on.
  `export_shared.py` writes `PACK_WORDS` (engine), `PRESETS` (`categories.ts`) and `Categories.Presets` (desktop).
- **Web**: `lib/results.ts` `leadPacks(ordered)` (stable: packs first), used by `groupResults` and the flat grid;
  `Reading` gains `packsBefore`, and `readQuery`/`dropPick` return `{reading, media, packs}`. `api.searchStream` takes
  `packs`. `SearchPage`: a `Packs` filter group (`Off` / `On`) and a `Game assets` pill in Media. `AssetCard` and
  `AssetDrawer` show the pack.
- **Desktop**: `ResultGroups.LeadPacks`; `QueryReading` gains `PacksBefore`, `Read`/`Drop` return `(Reading, Media,
  Packs)`. `SearchRequest.Packs`. `SearchViewModel` gains `Packs` and `GameAssetsCommand`. Card and detail as the web.
- **Words, the same in both apps:** card badge `Pack · 24 files` (`Pack` when not counted). Detail rows `Pack` →
  `24 files`, `Formats` → `WAV · MP3`, `Licenses inside` → `CC0 1.0, CC BY 4.0` + ` · read for 1 of 24 files` when
  incomplete. Chip `“pack” → Packs`. Filter group `Packs` with `Off` / `On`. Preset `Game assets`, tooltip `Sprites,
  3D, textures, audio, icons and fonts, with packs`.

## 3. Data
None. Ledger snapshots keep the whole `Asset`, so the new fields ride along.

## 4. Files
- `shared/categories.json` → `scripts/export_shared.py` → `categories_data.py`, `web/src/lib/categories.ts`,
  `Freestash.Client/Categories.g.cs`. `shared/parity.json`: rows `packs`, `game-assets`.
- **Engine:** `models.py`, `licenses/policy.py`, `query_words.py`, `search.py`, `providers/{base,design,stock,archives}.py`,
  `api/app.py`, `cli.py`, `mcp_server.py`. Fixtures: `iconify_collections.json` (recorded), `freesound_*_synthetic.json`,
  `ia_packs.json` (recorded). Docs: `docs/LICENSE-POLICY.md`, `docs/PROVIDERS.md`.
- **Web:** `lib/{types,results,api}.ts`, `pages/SearchPage.tsx`, `components/{AssetCard,AssetDrawer,bits}.tsx`, `styles.css`.
- **Desktop:** `Models.cs`, `FreestashApi.cs`, `ResultGroups.cs`, `SearchViewModel.cs`, `SearchView.axaml`,
  `AssetCardView.axaml`, `AssetDetailView.axaml`(+ view model).

## 5. Conventions this follows
`freestash/CLAUDE.md` ground rules 1 (policy rows + doc), 2 (no scraping: archive.org's own API, jsDelivr's npm CDN),
5 (pure parsers on fixtures) and 7 (the three mirrors); root `CLAUDE.md` (parity, generated files);
`dev plans/contracts/grouped-results.md` (the export pattern and query words).

## 6. Non-goals
- GitHub and curated packs (Kenney, Quaternius): PR #9. Web search: the PR after.
- Downloading a Freesound pack (needs each user's Freesound login), or unpacking a zip to list what's inside.
- Packs in synced preferences: the switch is per search.
- Loosening ND, NC or ShareAlike for brushes; any brush rule for shapes or sprites (they are the content itself).

## 7. Acceptance
- `test_licenses.py::test_policy_matrix` gains brush rows (Pixabay merch GREEN for a brush, YELLOW for an image; ND and
  uploader CC0 unchanged) and pack rows (CC0 + CC BY-NC → NC everywhere; CC0 + CC BY → credit; incomplete → YELLOW
  floor; pack-wide CC0 at curated trust → GREEN). `docs/LICENSE-POLICY.md` in the same commit.
- `test_providers.py`: set parsing and ranking, Freesound pack + member licences, IA pack detection, formats, kinds.
- `test_query_words.py`: "medieval sword sfx pack" → audio + packs; "pack of wolves" → "wolves" + packs; keep.
- `test_api.py` / `test_cli.py`: `packs` reaches the providers; `--packs`. `test_parity.py`: presets name real media.
- `results.test.ts` ↔ `ResultGroupsTests.cs`: packs lead each section and the flat grid; packs from words and back.
- `export_shared.py --check` clean. Live on the dev server: "game icons" with Packs on shows Iconify sets first;
  "photoshop brushes" with Brushes shows Internet Archive items. Contrast gate on the search page with pack cards
  (both themes, 1440 + 390). Desktop snapshot with packs.

## 8. Open questions
None.

## Changes after approval
- 2026-11-02 (build): the web's Game assets pill has no dashed border; Avalonia can't draw one, so both apps use the plain pill.
- 2026-11-02 (build): a pack's uid carries its kind: `iconify:set:<prefix>`, `freesound:pack:<id>`, and for a brush, shape or
  sprite found on Internet Archive `internet_archive:<kind>:<identifier>` (the kind is how `get` keeps the media type).
  An archive item found by an ordinary audio/image/video query keeps the plain `internet_archive:<identifier>` uid.
- 2026-11-02 (build): `strictest_license(licenses, trust, media)` is exported from `freestash.licenses`; a Freesound pack's
  `license` is its strictest member's, so the card and the ledger never show the laxest one.
- 2026-11-02 (build): `GET /api/search/stream` takes `packs=true`; the desktop's `SearchRequest.Packs` and the web's
  `SearchParams.packs` send it. A pack word's chip reads `“pack” → Packs`, and removing it restores the user's own Packs setting.
- 2026-11-02 (live): the first Iconify pack search after a restart can time out while `/collections` is fetched cold
  (the desktop snapshot run failed once on it); the catalogue is cached for a day after that.
- 2026-11-02 (review, CodeRabbit): an unread-files pack is Check at best for every use **but reference**, as §2 says (the code
  and the matrix row floored reference too); `search.py::_dedupe_key` now includes the media type, so a page found as a
  sprite and as a brush stays two results.
- 2026-11-02 (review, Codex + CodeRabbit): assets saved before packs have no pack fields, so the web's pack helpers default
  them; a query read that answers after the user changed the media or Packs searches with the latest ones; the desktop's
  Media pills wrap (`09g-search-narrow.png`).
