# Next session — Freesta.sh

## 1. What and where
Open-media search with per-use clearance. One product, two apps, one account: the website (`freestash/`, live at
https://freesta.sh on Railway) and the Windows desktop app (`freestash-desktop/`). Monorepo `C:\DEV\Freesta.sh`, GitHub
`Vybecode-LTD/Freesta.sh`. Read the root `CLAUDE.md`, then `docs/HANDOFF.md`.

## 2. Rules that override defaults
- **Parity is binding:** every user-facing change lands in both apps in one PR (`shared/parity.json`).
- No Supabase. Never print Railway variables.
- **Needs the owner's OK:** merging, DNS, production accounts, deleting Railway resources, computer-use, admin grants.
- No email address makes an admin: grants go only through `python -m freestash admin grant`.

## 3. State (verified 2026-11-02, end of session)
- `main` = `origin/main` = **f1737d6** (PR #7 merge), deployed and verified on production (the parse route answers
  401; the bundle carries PR #7's strings). No open PRs; next #8.
- The checkout is `feat/pr8-packs`, cut from f1737d6: one local docs commit, not pushed, no upstream. It goes in with PR #8.
- The owner hasn't stored provider keys on `#/admin` yet.

## 4. First job, then the order
1. **PR #8: packs and brush/shape/sprite** (plan `dev plans/2026-11-01-packs-web-admin-plan.md` §2, asks 1 and 5).
   Contract first. Model mirrors gain `is_pack`/`item_count`/`formats` and three media types; brush policy rows
   (ground rule 1); new rows and pack words in `shared/categories.json`; packs lead each section (`lib/results.ts` ↔
   `ResultGroups.cs`); Iconify sets, Freesound and Internet Archive packs.
2. Then GitHub + curated packs, then web or AI search (decision 0003's order).

## 5. Open owner decisions (ask, don't decide)
- AI Search (plan §2b) instead of Brave web search.
- The Unsplash production application; Wikimedia (a normal OAuth consumer, or drop the token).
- The infrastructure items in `docs/HANDOFF.md` → Next 5.

## 6. Environment that worked
- **Python:** `cd freestash; .venv/Scripts/python.exe -m pytest` (167) · `ruff check src tests scripts` ·
  `python scripts/export_shared.py --check`.
- **Web and desktop:** `cd freestash/web; npm test` (39) · `npm run build`. Desktop: `dotnet test --project
  tests/Freestash.Client.Tests` from `freestash-desktop/` (54).
- **Servers:** `preview_start freestash-accounts` (:8790, accounts mode); `preview_start freestash-local` (:8791, local
  mode, for the desktop snapshot tool: `dotnet run --project tools/Freestash.Desktop.Snapshots -- http://127.0.0.1:8791 <out>`).
- **Contrast gate on a signed-in page:** Playwright (the `verify-real-pass` skill's `node_modules`), `bypassCSP: true`.
  Register a throwaway `*@example.test` with `X-Freestash-Session: cookie` and set `localStorage["freestash.session"]`
  to `{user}`. Write one script-free snapshot per `data-theme` into `web/dist`, gate with `--schemes dark` (positive
  control first), delete them. Broken remote images read as "undecided": re-run without `<img>`.
- **Traps:**
  - Bash heredocs eat `\\n` and quotes: patch with the Edit tool, or a script file.
  - `gh` sometimes hits TLS timeouts: retry.
  - A branch cut from `origin/main` tracks `main`: push with `git push -u origin <branch>:<branch>`.

## 7. Evidence and IDs
- Decisions `docs/decisions/0001–0003` (next 0004).
- Contracts `dev plans/contracts/{accounts-sync,web-cookie-session,admin-shared-keys,grouped-results}.md`.
- Next PR #8.

## 8. Promotion candidates (owner approves)
- **Contrast-gate a signed-in SPA:** the snapshot recipe above (local-session marker, `bypassCSP`, broken images
  read as undecided).
- **A parse-then-search UI must key its filter re-run on the last *started* search** (set synchronously before the
  first await), or a programmatic media change searches twice.
- Earlier candidates (email-keyed bootstrap admin; key Test bypassing the cache): the previous prompt, in git history.
