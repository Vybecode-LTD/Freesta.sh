# Next session — Freesta.sh

## 1. What and where
Open-media search with per-use clearance. One product, two apps, one account: the website (`freestash/`, live at
https://freesta.sh on Railway) and the Windows desktop app (`freestash-desktop/`). Monorepo `C:\DEV\Freesta.sh`, GitHub
`Vybecode-LTD/Freesta.sh`. Read the root `CLAUDE.md`, then `docs/HANDOFF.md`.

## 2. Rules that override defaults
- **Parity is binding:** every user-facing change lands in both apps in one PR (`shared/parity.json`).
- No Supabase. Never print Railway variables or the GitHub token.
- **Needs the owner's OK:** committing/pushing/merging, DNS, production accounts, deleting Railway resources, computer-use,
  admin grants, and anything entered on production `#/admin` (tokens, curated packs). Admins are granted only by
  `python -m freestash admin grant` on the server or by an admin on `#/admin`, never by an email address.

## 3. State (verified 2026-11-04, end of session)
- `main` = `origin/main` = **71a29d6** (PR #8), live.
- **PR #9 open** from `feat/pr9-github-curated-packs` (the checkout): GitHub game-asset repos as packs and admin-curated
  packs. Gates green locally (pytest 241, vitest 54, dotnet 61, contrast on `#/admin`). Read its CI and reviews with
  `gh pr checks 9` and `gh pr view 9 --comments`; don't trust this line, check.

## 4. First job, then the order
1. **Finish PR #9:** fix any red CI or review finding (a failing test first, one batched push); merge only on the owner's
   OK, then verify the deploy with a string only PR #9 ships (`Curated packs` in the production bundle).
2. **After the merge:** the owner pastes a fine-grained GitHub token on `#/admin` → Site keys and presses Test, then adds
   curated packs (Kenney, Quaternius, KayKit). Verify on production: a Game assets search shows GitHub packs; a curated one leads.
3. Then web or AI search (decision 0003; plan `dev plans/2026-11-01-packs-web-admin-plan.md` §2/§2b). Contract first.

## 5. Open owner decisions (ask, don't decide)
- Should the agent draft a starter curated list (titles, pages, kinds) for the owner to check before importing?
- AI Search (plan §2b) instead of Brave web search.
- The Unsplash production application; Wikimedia (a normal OAuth consumer, or drop the token).
- The infrastructure items in `docs/HANDOFF.md` → Next 4.

## 6. Environment that worked
- **Python:** `cd freestash; .venv/Scripts/python.exe -m pytest` (241, ~2 min) · `ruff check src tests scripts` ·
  `python scripts/export_shared.py --check` (silent, exit 0).
- **Web / desktop:** `cd freestash/web; npm test` (54) · `npm run build`. `cd freestash-desktop; dotnet build
  Freestash.Desktop.sln; dotnet test --project tests/Freestash.Client.Tests` (61).
- **Servers:** `preview_start freestash-accounts` (:8790). Grant a dev admin: `python scripts/dev_accounts.py --grant-admin EMAIL`.
- **Signed-in checks:** register inside the page (`fetch('/api/auth/register')`, `X-Freestash-Session: cookie`, password
  made in the page), set `localStorage["freestash.session"]`, reload. Contrast gate: script-free snapshots per `data-theme`
  in `web/dist`, `rendered_contrast.mjs --schemes dark` on each (positive control first), then delete them.
- **Traps:** quoted heredocs break (use a script file); `write_text` writes CRLF (use `write_bytes`); a hidden pane can't
  draw (use `javascript_tool` or headless Playwright); GitHub search without a token is 10 a minute from this IP.

## 7. Evidence and IDs
- Decisions `docs/decisions/0001–0003` (next 0004). Contracts in `dev plans/contracts/`. Next PR #9, then #10.
- Fixtures `github_*.json` recorded 2026-11-04; `freesound_packs_synthetic.json` is hand-built.

## 8. Promotion candidates (owner approves)
- **`create_all` never alters an existing table:** a local DB from an early build kept `NOT NULL` on a column the code
  later made nullable. Check a stale schema before blaming the code; real column changes need a migration.
- **Python `Path.write_text` on Windows writes CRLF:** in an `eol=lf` repo, patch files with `write_bytes`.
- **A provider's on-demand image service can rate-limit a results grid:** use a CDN image (owner avatar) for cards.
- **A packs-only source needs the key test to ask for packs**, or the test passes without calling it.
