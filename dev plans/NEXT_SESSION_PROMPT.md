# Next session — Freesta.sh

## 1. What and where
Open-media search with per-use clearance. One product, two apps, one account: the website (`freestash/`: Python
engine, FastAPI, React; **live at https://freesta.sh** on Railway) and the Windows desktop app (`freestash-desktop/`,
Avalonia 12). Monorepo `C:\DEV\Freesta.sh`, GitHub `Vybecode-LTD/Freesta.sh`. Read the root `CLAUDE.md`, then
`docs/HANDOFF.md`.

## 2. Rules that override defaults
- **Parity is binding** (root `CLAUDE.md`): every user-facing change lands in both apps in one PR.
- **No Supabase.** Never list or print Railway variables. Set secrets only with `railway variable set KEY --stdin`.
- Needs the owner's OK: merging, DNS, anything sent to providers, accounts on production (smoke tests use made-up
  emails), deleting Railway resources, and computer-use.

## 3. State (verified 2026-11-01, end of session)
- `main` = the PR #3 merge (bfdae9b). PRs #1–#3 are live. **PR #4** (`feat/pr4-followups`): accounts mode refuses
  to start without `DATABASE_URL`, plus docs. Open; the next PR is #5.
- **Database incident 2026-11-01:** the first Postgres service was deleted, and its data is gone. A new `Postgres`
  service runs on `postgres-volume`, with `DATABASE_URL=${{Postgres.DATABASE_URL}}`. 9 tables, 0 users at 23:58.
- Verified on production: path-traversal fix, CSP (an injected script is blocked), health `auth_mode: accounts`.
- Railway is on **Pro**, and the owner has set `FREESTASH_SMTP_USERNAME` and `FREESTASH_SMTP_PASSWORD`. A reset
  email hasn't been tested yet.
- Desktop: CI artifact `freestash-desktop-win-x64` from `main`. Local build `freestash-desktop/publish/Freestash.exe`.

## 4. First job, then the order
1. Check PR #4 (merge needs the owner's OK). Confirm production is on Postgres: run
   `railway ssh -s Postgres -- psql -U postgres -d railway -tAc 'select count(*) from users'`.
2. Once the owner has re-registered, have them request a reset and confirm the email arrives. Logs show only
   `SMTP send failed: <type> <code>`.
3. Ask what the owner saw signing the desktop app in.
4. PR #5: an HttpOnly cookie session for the web (decision 0002). The desktop keeps bearer; add CSRF protection
   (SameSite plus an Origin check). Contract first (`_templates/feature-CONTRACT.md`).
5. Then `www.freesta.sh`, Google sign-in on both apps, the live desktop check (ask first), a desktop installer
   (`C:\DEV\SOFTWARE_RELEASE.md`), and retiring `railway.json` before 2026-12-01.

## 5. Open owner decisions (ask, don't decide)
- Volume backups for Postgres (Railway → Postgres → Backups). Delete the spare empty volume `postgres-volume-EFLf`?
- The Google OAuth client. The `www` CNAME. Desktop signing and distribution.

## 6. Environment that worked
- `cd freestash; .\.venv\Scripts\python.exe -m pytest` (122) · `ruff check src tests scripts` ·
  `python scripts/export_shared.py --check`
- `cd freestash/web; npm test` (15) · `npm run build` · `cd freestash-desktop/tests/Freestash.Client.Tests; dotnet test`
  (33; run it from that folder)
- `.claude/launch.json` → `preview_start freestash-accounts` (:8790). Linux checks: `wsl.exe -e python3 -`.
- Railway: MCP (`describe-environment`, `domain-status`, `list-deployments`, `get-logs`), CLI 5.63.1, `railway ssh`.
- Traps:
  - A Python `open(p, "wb")` truncates the file before the write.
  - The Bash tool collapses `\\`.
  - Bound the pytest paging loops.

## 7. Evidence and IDs
Decisions `docs/decisions/0001–0002` (next 0003) · Postgres service `2a2d55fd-…` (IMPLEMENTATION P2) · next PR #5.

## 8. Promotion candidates (owner approves)
- **Railway: a deleted service's reference variable resolves to "".** Fail fast when a required URL is empty.
  Don't fall back to local files.
- **Starlette path params arrive percent-decoded:** a catch-all `FileResponse(DIST / path)` is a file-read hole.
- **Railway blocks SMTP below Pro.** A CSP check needs a positive control.
