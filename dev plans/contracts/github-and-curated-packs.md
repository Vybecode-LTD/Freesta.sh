---
feature: github-and-curated-packs
status: done
approved: 2026-11-01 (decision 0003: the owner accepted plan §3 ask 1 and the order; "First job: PR #9" 2026-11-04)
plan: dev plans/2026-11-01-packs-web-admin-plan.md (§3 ask 1, the GitHub and Curated packs rows; §4 step 5)
pr: 9
---

# Contract: GitHub asset repositories and curated packs

## 1. Goal
With Packs on, a search also finds **game-asset repositories on GitHub** (one pack per repository, the repo's SPDX licence
at uploader trust). The site's admin can **record packs by hand** on `#/admin` (Kenney, Quaternius: the licence they read
on the publisher's page), and every member's search finds those at curated trust, in both apps.

## 2. Interfaces
- **Models** (`models.py` ↔ `web/src/lib/types.ts`; admin-only, so not in the desktop's `Models.cs`):
  `CuratedPack {id: str | None, title (1–200), url (https, ≤2048, unique), publisher (1–120), license_id, license_checked_on:
  date (not in the future), media_type: MediaType, download_url: str | None (https), thumbnail_url: str | None (https),
  item_count: int | None (≥1), formats: list[str] (lowercase, no dot), tags: list[str], description: str | None (≤2000),
  updated_at: datetime | None}`, `extra="forbid"`. `license_id` is stored normalized (`normalize_license`) and may not
  normalize to `RIGHTS-UNKNOWN`.
- **Settings** (`config.py`): `github_access_token` (env `FREESTASH_GITHUB_ACCESS_TOKEN` or `GITHUB_ACCESS_TOKEN`, not
  `GITHUB_TOKEN`, which CI and `gh` set) and `curated_packs: list[CuratedPack] = []` (the API fills it per request).
- **Key catalog** (`providers/keys.py`): `GITHUB_ACCESS_TOKEN`, provider `github`, label `Fine-grained personal access
  token`, url `https://github.com/settings/personal-access-tokens/new`, optional, limits `Repository search: 30 requests a
  minute (10 without a token)`. Exported to `shared/provider-keys.json`, so both apps' key help and the admin's key list show it.
- **Registry**: `ProviderInfo.packs_only: bool = False`; `select_providers(settings, media, only=None, packs=False)` skips a
  `packs_only` source unless `packs`. `Freestash.search_stream`/`search` pass `query.packs`. The admin's key test runs with
  `packs=cls.info.packs_only`, so a GitHub token test really calls GitHub.
- **`providers/github.py` `GitHubProvider`**: id `github`, name `GitHub`, media sprite, model, texture, audio, icon;
  `Trust.UPLOADER`; `packs_only`. Search: `GET https://api.github.com/search/repositories?q=<query words> topic:game-assets`
  (`per_page` = limit; see Changes), `Authorization: Bearer <token>` when set. Kind from topics, name and description
  (`kind_of`: audio, then model, texture, icon, else sprite). In-process budget per token: 25 searches a minute with one,
  8 without; after a 403 or 429, no search on that token for 60 s, and no retry of the 429 (`HttpClient.get_json` gains
  `retry_on`). Pure parsers `parse_github_repo(item) -> Asset | None` and `parse_github_tree(tree) -> (item_count | None,
  formats)`. uid `github:repo:<owner>/<name>`; `get` reads `/repos/<owner>/<name>` and its recursive git tree for the count
  of asset files (by extension) and their formats (`None` when GitHub truncates the tree).
  Asset: `is_pack`, pack-wide licence (`members_checked` None) from `license.spdx_id`, with `license.raw`
  `MIT (GitHub's reading of the repository's license file)` / `Other (GitHub couldn't identify the repository's license
  file)` for `NOASSERTION` / `No license file in the repository`; one rendition `<name>-<branch>.zip (whole repository)` at
  `https://github.com/<owner>/<name>/archive/refs/heads/<branch>.zip`; thumbnail the owner's avatar (see Changes); note `GitHub reads the repository's license file; art inside can
  carry its own terms, so check the README.`; tips for size, stars and archived; `detail_required`.
- **`providers/curated.py` `CuratedProvider`**: id `curated`, name `Curated packs`, every media type, `Trust.CURATED`,
  enabled only when `settings.curated_packs` has entries. Not packs-only (no quota): an entry shows whenever it matches,
  like an archive item. Ranked with `design._score` over title, publisher, tags, description and formats (score > 0).
  `curated_asset(pack) -> Asset`: uid `curated:<id>`, `source_name` and `creator` the publisher, `is_pack`, `license.raw`
  `CC0 1.0, recorded by Freesta.sh from <url> on 2026-11-04`, one rendition when `download_url` is set.
- **Admin** (`admin.py`, `api/admin.py`, every write audited): `GET /api/admin/curated` → `list[CuratedPack]` (title order);
  `POST /api/admin/curated` → 201 `CuratedPack` (409 when the url is listed); `PUT /api/admin/curated/{pack_id}` →
  `CuratedPack` (404, 409); `DELETE /api/admin/curated/{pack_id}` → 204 (404);
  `POST /api/admin/curated/import` `{packs: list[CuratedPack]}` (≤ 500) → `{added, updated}`, matched by url, all or
  nothing (422 names the row). Audit actions `curated.add`, `curated.update`, `curated.delete`, `curated.import`.
  `api/app.py::search_settings` adds `admin.curated()` (cached, cleared on write) in accounts mode.
- **Web** (`#/admin`, web only): `CuratedSection` between Limits and Shared quota: a table (Pack, Kind, License, Checked,
  Edit/Delete), a form (Title, Page URL, Publisher, Kind, License, License checked on, Download URL, Preview image URL,
  Files, Formats, Tags, Description) and an `Import JSON` box. `lib/admin.ts` `parseCuratedImport(text)`,
  `CURATED_LICENSES`; `api.ts` `curatedPacks`, `addCuratedPack`, `saveCuratedPack`, `deleteCuratedPack`, `importCuratedPacks`.
- **Desktop**: no code. GitHub and curated results are packs, which both apps already show (PR #8 rows); the token's help
  comes from the regenerated `shared/provider-keys.json`.

## 3. Data
`Base.metadata.create_all` adds the table (no migration tool yet; `store.py`).

| Table | Column | Type | Null | Default / FK / index |
|---|---|---|---|---|
| curated_packs | id | UUID | no | PK, uuid4 |
| | title, publisher | String(200), String(120) | no | |
| | url | String(2048) | no | unique |
| | license_id | String(40) | no | |
| | license_checked_on | Date | no | |
| | media_type | String(20) | no | |
| | download_url, thumbnail_url | String(2048) | yes | |
| | item_count | Integer | yes | |
| | formats, tags | JSON (JSONB on Postgres) | no | `[]` |
| | description | Text | yes | |
| | created_at, updated_at | DateTime(tz) | no | now |
| | updated_by | UUID | yes | the admin |

## 4. Files
Engine: `models.py`, `config.py`, `http.py`, `providers/{__init__,base,keys,github,curated}.py`, `search.py`, `admin.py`,
`api/{admin,app}.py`; fixtures `github_search.json`, `github_repo.json`, `github_tree.json` (recorded); `docs/PROVIDERS.md`.
Shared: `shared/provider-keys.json` (export), `shared/parity.json` (`packs` and `admin` rows). Web: `lib/{types,api,admin}.ts`,
`pages/AdminPage.tsx`, `styles.css` if needed.

## 5. Conventions this follows
`freestash/CLAUDE.md` ground rules 1, 2 (GitHub's own API within its limits; no scraping of Kenney or Quaternius), 4, 5, 9;
root `CLAUDE.md` (parity, key help, generated files); `dev plans/contracts/admin-shared-keys.md` (admin routes, audit);
`dev plans/contracts/packs-and-new-kinds.md` (pack fields, pack-wide licences).

## 6. Non-goals
- Brushes, shapes or fonts from GitHub (brush topics are painting apps: probe 2026-11-04); any topic but `game-assets`.
- GitHub search without Packs on (it spends a 30-a-minute quota the whole site shares).
- Reading a repository's README or per-file licences; unpacking a zip.
- Fetching Kenney's or Quaternius's catalogues automatically. Entries are typed or imported by the admin.
- A trust choice per curated entry (all curated); curated packs in the CLI, MCP or the desktop's local engine (they live
  in the site's database); admin on the desktop.

## 7. Acceptance
- `test_providers.py`: `parse_github_repo` (MIT, `NOASSERTION`, no licence; kind; rendition; uid with a slash),
  `parse_github_tree` (count, formats, truncated), the search sends `topic:game-assets` and the token, the budget and the
  403 cool-down stop calls, `get` reads the tree; `CuratedProvider` ranks, filters by kind, is off when empty, gets by id.
- `test_search_store.py`: a packs-only source isn't searched without `packs`.
- `test_admin.py`: CRUD, 409 on a duplicate url, https and licence validation, import upsert all or nothing, audit rows,
  members get 403; a member's search returns a curated entry; the GitHub key test calls GitHub.
- `test_licenses.py` matrix: a GitHub MIT pack at uploader trust (demo Clear, bundled Check with the licence text) and a
  `NOASSERTION` pack (blocked when shipped). No policy change.
- `admin.test.ts`: `parseCuratedImport`. `export_shared.py --check` clean; the desktop builds and its tests pass.
- Live on the dev server: an admin-added Kenney entry leads "space" results, Clear for bundled; Game assets with "space"
  shows GitHub repositories, Check; a GitHub drawer shows the file count. Contrast gate on `#/admin` with the new
  section, both themes, 1440 + 390.

## 8. Open questions
None.

## Changes after approval
- 2026-11-04 (review, CodeRabbit): a query with no searchable words (non-Latin text, only symbols) returns an
  empty GitHub page without a call, instead of searching `topic:game-assets` alone.
- 2026-11-04 (review, Codex): GitHub asks for `per_page` = limit, not 3 × limit (cutting a bigger page down skipped the
  cut repos on the next page); after any curated write the API drops cached `curated:` assets
  (`RecentCache.forget_provider`), so the drawer and a uid-only ledger entry see the corrected or removed pack.
- 2026-11-04 (live): a GitHub pack's thumbnail and preview are the owner's avatar (`<avatar_url>&s=240`), not
  `opengraph.githubassets.com/1/<owner>/<name>`: GitHub draws those on request and throttles them per IP (a grid of cards
  got 429s, then every one did). GitHub packs also carry `source_name` `GitHub`, so the drawer's Source row says so.
