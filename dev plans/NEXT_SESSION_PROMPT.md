# Next session — Freesta.sh

## 1. What and where
Open-media search with per-use clearance. One product, two apps, one account: the website (`freestash/`: Python
engine, FastAPI, React; **live at https://freesta.sh** on Railway) and the Windows desktop app (`freestash-desktop/`,
Avalonia 12). Monorepo `C:\DEV\Freesta.sh`, GitHub `Vybecode-LTD/Freesta.sh`. Read the root `CLAUDE.md`, then
`docs/HANDOFF.md`.

## 2. Rules that override defaults
- **Parity is binding** (root `CLAUDE.md`): every user-facing change lands in both apps in one PR.
- **No Supabase.** Never list or print Railway variables. Set secrets only with `railway variable set KEY --stdin`.
- Needs the owner's OK: merging, DNS, the Railway plan, anything sent to providers, accounts on production (smoke tests
  use made-up emails), and computer-use.

## 3. State (verified 2026-11-01, end of session)
- `main` = the **PR #2** merge (3ac162b). It's the path-traversal hotfix: deployed, and verified on both hosts
  (`/..%2f..%2fpyproject.toml` and `%00` paths get the page).
- **PR #3** `feat/pr2-followups`: ledger paging, CSP, SMTP reset email, decision 0002. `main` is merged in. Not merged.
- PR #1's three review threads are answered but unresolved: resolving them was blocked by permissions, so the owner
  does it.
- freesta.sh: the certificate is valid, and health reports `auth_mode: accounts`. The CNAME target is now `cgl6fdva`
  (`freestash/IMPLEMENTATION.md` → P2).
- Reset email isn't configured: Railway needs **Pro** for SMTP, plus the Spacemail mailbox and its variables.

## 4. First job, then the order
1. Check PR #3: its CI and review. Fix findings, then ask the owner to merge. After the deploy, check the CSP header
   on https://freesta.sh.
2. Run one reset email end to end on production once SMTP is set up (section 5).
3. Ask whether the owner has signed up on the site and signed the desktop app in.
4. Then: the HttpOnly cookie PR (decision 0002), `www.freesta.sh`, Google sign-in on both apps, the live desktop
   check (ask first), and retiring `railway.json` before 2026-12-01.

## 5. Open owner decisions (ask, don't decide)
- Moving Railway to Pro (needed for SMTP), or a mail HTTP API instead.
- The OAuth client for Google sign-in. The `www` CNAME at Spaceship.

## 6. Environment that worked
- `cd freestash; .\.venv\Scripts\python.exe -m pytest` (121) · `ruff check src tests scripts` ·
  `python scripts/export_shared.py --check`
- `cd freestash/web; npm test` (15) · `npm run build`
- `cd freestash-desktop/tests/Freestash.Client.Tests; dotnet test` (33). It must run from that folder, for `global.json`.
- Browser check: `.claude/launch.json` → `preview_start freestash-accounts` (dev_accounts.py on :8790).
- Railway: MCP connector (`domain-status`, `list-deployments`), CLI 5.63.1. `gh` as color8.
- Linux-only behaviour (production and CI run Linux): `wsl.exe -e python3 -` (3.14) is available.
- Traps:
  - A Python `open(p, "wb")` truncates the file before the write: build the bytes first.
  - The Bash tool collapses `\\`.
  - pytest loops that page must be bounded.

## 7. Evidence and IDs
Decisions `docs/decisions/0001–0002` (next 0003) · contract `dev plans/contracts/accounts-sync.md` · PRs up to #3
(next #4).

## 8. Promotion candidates (owner approves)
- **Starlette path params arrive percent-decoded:** a catch-all `FileResponse(DIST / path)` is a file-read hole.
  Resolve the path and check `is_relative_to`. Add this to `railway-deploy-playbook` or a FastAPI skill.
- **Railway blocks outbound SMTP below Pro:** check the plan before choosing SMTP.
- **CSP check:** a positive control (inject an inline script and see it blocked), or "no violations" proves nothing.
- Spaceship: re-adding a Railway domain changes its CNAME target.
