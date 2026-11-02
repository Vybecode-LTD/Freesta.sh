# Handoff — Freesta.sh (2026-11-02, fifth session, after the PR #8 merge)

## State (verified after the merge)
- `main` = `origin/main` = **71a29d6**, the merge of PR #8. PRs #1–#8 are merged. No PRs are open. The owner is the only
  production admin.
- **Live:** after the deploy the production bundle changed and contains "Game assets" (a string only PR #8 ships); the parse route
  answers 401 and a made-up `/api/search/` path 404, on both hosts. Not checked signed in on production (the owner's account).
- The checkout is `feat/pr9-github-curated-packs`, cut from 71a29d6, with this handoff as a local commit (not pushed).
- **PR #8 (merged on the owner's "it's green, go for it", CI green on c02cfbe): packs, and brushes, shapes and sprites.** Contract `dev plans/contracts/packs-and-new-kinds.md` (done; dated
  changes logged there). Built and verified, both apps:
  - **Model:** `MediaType` + `brush`/`shape`/`sprite`; `Asset` + `is_pack`, `item_count`, `formats`, `member_licenses`,
    `members_checked`; `SearchQuery.packs`; `QueryPick.media_type` nullable + `packs`; `ParsedQuery.packs`. Three mirrors in step.
  - **Policy (ground rule 1, matrix + `docs/LICENSE-POLICY.md` in the same change):** a brush's client and merch judge the
    artwork (a "modified only" merch clause doesn't hold a brush back); a per-file pack takes its strictest member's tier;
    fewer files read than it holds → every use but reference is Check. `strictest_license` picks the pack's shown licence.
  - **Sources:** Iconify sets (`set:<prefix>`, one SPDX licence, JSON download via jsDelivr); Freesound packs (`group_by_pack`,
    up to 6 `/packs/<id>/` lookups, detail reads up to 150 sounds' licences; **synthetic fixtures, no key yet**); Internet Archive
    items holding a ZIP/RAR/7z are packs, plus keyword queries for brush/shape/sprite (recorded `ia_packs.json`).
  - **Words and UI:** `shared/categories.json` gained the three categories, `pack_words` and the `game-assets` preset
    (exported to engine, web, desktop). `--packs` (CLI), `packs` (MCP, API, stream). Both apps: Packs Off/On, Game assets pill,
    pack words as a chip, packs lead each section, card badge `Pack · 24 files`, detail rows Pack / Formats / Licenses inside.
- **Gates at the merge:** pytest 205 · ruff clean · export check clean · vitest 50 · web build · dotnet build 0 warnings · dotnet 61.
  Live on the dev server: "game icon pack" → chips icon→Icons, pack→Packs, Packs On, Game Icons (4,133 files) first, drawer rows
  right; Game assets → one search with six media + packs; "grunge brushes" (Reference) → IA brush packs, all Check, "No license stated".
  Rendered contrast on the search page with pack cards: packs grid and Game assets sections, dark and light, 1440 and 390 and
  hovers, **0 failing**; positive control (badge in its own colour) fails at 1:1. The open drawer's own text passes; two
  "undecided" remain at 390 px in page chrome the drawer covers (the Downloads nav link, the aperture's "08"), not pack content.
  Desktop: headless renders `freestash-desktop/docs/screenshots/09e`, `09f`, `09g` (narrow window); the snapshot
  script asserts the chips, a set leading, the pack detail rows and the preset.
- **Review fixes (Codex, CodeRabbit), each with a test that failed first except the pill wrap (checked by a 760 px render):** assets saved before packs have no pack fields (the web's
  helpers default them); reference isn't floored by unread files; the dedupe key includes the media type; a late query read
  searches with the latest media and Packs; the desktop's Media pills wrap.
- **Contract change:** the Game assets pill has no dashed border (Avalonia can't); pack uids carry their kind
  (`iconify:set:…`, `freesound:pack:…`, `internet_archive:brush:…`). Both in the contract's dated list.

## Next
1. **Owner (optional):** signed in on https://freesta.sh, search "game icon pack": two chips, Packs On, Game Icons (4,133 files) first.
2. **PR #9: GitHub source and curated packs** (plan §3·1). Contract first. Needs the owner's GitHub token on `#/admin` and the
   curated-pack list (Kenney, Quaternius: admin-recorded licences). Then web or AI search (the AI Search question is still open).
3. **Owner (optional):** record real Freesound fixtures with a key (`freesound_packs_synthetic.json` is hand-built).
4. Still open from before: provider keys on `#/admin` (apply for Unsplash production first); the Wikimedia decision; test the
   reset email on production; Postgres volume backups; delete the spare volume `postgres-volume-EFLf`; `www.freesta.sh`; Google
   sign-in; the desktop installer; retire `railway.json` before 2026-12-01.

## Warnings
- Back up `FREESTASH_SECRETS_KEY`: it decrypts both members' and the site's stored keys.
- Pack searches cost more: Freesound spends up to 6 extra calls per search against the site's daily quota; Iconify's first
  pack search after a restart fetches `/collections` cold and can time out once.
- A Freesound pack's verdict is Check at best from a search (one file's licence read); the detail reads up to 150.
- Brush and shape finds on Internet Archive come from title/subject words: expect misses and mostly "No license stated".
- The rate limiter, caps and caches are in-process: one replica only. Pexels has paused new API keys.
- OpenGameArt's robots.txt bars every Anthropic agent; itch.io bars `/search` and `/game/download/`. Reach them only through
  web search (ground rule 2).
- This folder isn't `railway link`ed: pass `--project ba994460-f01e-4a4d-9e83-994f352b6634 --environment production
  --service <freestash|Postgres>` to `railway ssh`.
- The local dev database (`%LOCALAPPDATA%\Freestash\dev`) holds throwaway accounts (`*@example.test`): `admin@example.test`,
  `contrast-*`, and this session's `packs-*`.
- Query words are a first cut; edit `shared/categories.json`, then run the export.
