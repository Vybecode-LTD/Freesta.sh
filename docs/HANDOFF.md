# Handoff — Freesta.sh (2026-11-02, end of the fourth session)

## State (verified at the end of the session)
- `main` = `origin/main` = **2cfc414**, the merge of PR #6. PRs #1–#6 are merged and **live** (Railway deploy
  `ac05d804`). The owner is the only production admin; production has 1 account.
- **PR #7 is open, not merged:** `feat/pr7-grouped-results`, grouped results and query words, both apps.
  Contract: `dev plans/contracts/grouped-results.md` (one dated build change, logged there).
  - `shared/categories.json` (the eight media: label, order, query words) → `export_shared.py` writes
    `categories_data.py` (engine), `web/src/lib/categories.ts` and `Freestash.Client/Categories.g.cs`. Both apps'
    Media pills now come from it.
  - Engine: `query_words.parse_query` and `GET /api/search/parse?q=&keep=` (needs sign-in; ≤500 characters; ≤20 keep).
    The CLI reads words unless `--media` or `--literal`; MCP `search_assets` reads them only without `media_types`
    (`read_as`, `searched_for`, `literal`).
  - Both apps: picks replace the media and show as "Read as" chips; removing one searches the word as a word in the
    media chosen before. With two or more media: one section per category, 8 cards, "Show all (n)" / "Show fewer", and
    a jump bar with counts. One medium looks as before. The rules live in `web/src/lib/results.ts` and
    `Freestash.Client/ResultGroups.cs`, with mirrored tests.
  - **Contract change:** `groupResults` / `ResultGroups.Group` dropped an unused `media` argument; the desktop's jump
    bar sits above its scrolling results; both apps share one example list (three use query words).
- Gates on the branch: pytest 165 · ruff · export check · vitest 38 · web build · dotnet build 0 warnings · dotnet 54.
  - Mutation pass: 10 of 10 killed (parser and web helpers).
  - Rendered contrast on the grouped search page (chips, jump bar, section heads, Show all, all three verdict tones):
    dark and light, 1440 and 390, hovers, **0 failing**; the positive control fails (1.28:1).
  - The cards whose remote images failed to load came out "undecided" (axe gives up on broken images). A hit test
    shows their text sits on the flat plate, and the run without `<img>` tags decides them all as passing.
  - Desktop: headless renders against a local engine, `freestash-desktop/docs/screenshots/09b–09d` and `10`. The script
    asserts the read, the sections and the chip removal.
  - Live on the dev server: the "sfx" chip, its removal (one search per action, from the network log), the sections,
    the jump and the toggle.

## Next
1. **Owner:** review PR #7 and say whether to merge. After the merge, check it on https://freesta.sh:
   `GET /api/search/parse` answers 401 signed out (404 before the deploy); then a signed-in "rain sfx" shows the chip.
2. **Owner:** sign in → Settings → Site administration → paste the provider keys → Test each. Apply for Unsplash
   production first: demo mode allows 50 requests an hour for everyone. Decide on Wikimedia: a normal OAuth consumer,
   or drop the owner-only token.
3. **PR #8: packs and brush/shape/sprite** (plan §2, decision 0003). Contract first. It brings the model change
   (`is_pack`, `item_count`, `formats`), the policy rows, the three new categories in `categories.json` with their
   words, pack words ("pack", "bundle") and packs leading each section.
4. Then GitHub and curated packs, then web search. **Open decision:** the owner's AI Search idea (plan §2b) or Brave.
5. Still open from before: test the reset email on production; Postgres volume backups; delete the spare volume
   `postgres-volume-EFLf`; `www.freesta.sh`; Google sign-in; the desktop installer; retire `railway.json` before
   2026-12-01.

## Warnings
- Back up `FREESTASH_SECRETS_KEY`: it decrypts both members' and the site's stored keys.
- Any provider keys in Railway's env now serve every member, so the meter on `#/admin` shows their use.
- The rate limiter, caps and caches are in-process: one replica only. Pexels has paused new API keys.
- OpenGameArt's robots.txt bars every Anthropic agent; itch.io bars `/search` and `/game/download/`. Reach them only
  through web search (ground rule 2).
- This folder isn't `railway link`ed: pass `--project ba994460-f01e-4a4d-9e83-994f352b6634 --environment production
  --service <freestash|Postgres>` to `railway ssh`.
- The local dev database (`%LOCALAPPDATA%\Freestash\dev`) holds throwaway accounts (`*@example.test`), among them
  `admin@example.test` (an admin there) and `contrast-*@example.test` from the contrast gate.
- Query words are a first cut. A wrong pick is one click to undo; edit `shared/categories.json`, then run the export.
