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
  emails), and computer-use.

## 3. State (verified 2026-11-01, end of session)
- `main` = the PR #3 merge (bfdae9b). PRs #1–#3 are merged and live, and none are open (the next is #4).
- On production:
  - the path-traversal fix is verified on both hosts;
  - the CSP header is served, and in a browser the page shows no violations while an injected script is blocked;
  - health reports `auth_mode: accounts`.
- The checkout is on **`feat/pr4-followups`**: one local docs commit on `main`, not pushed. Do PR #4 here.
- **Railway is on Pro** (SMTP allowed). Reset email still waits on the owner's Spacemail mailbox and
  `FREESTASH_SMTP_*` variables (`freestash/IMPLEMENTATION.md` → P2).
- Desktop: CI artifact `freestash-desktop-win-x64` on every push to `main`. Local Release build at
  `freestash-desktop/publish/Freestash.exe` (unsigned).

## 4. First job, then the order
1. Ask whether the SMTP variables are set. If so, have the owner request a reset for their own account and confirm
   it arrives. Read the service logs for `SMTP send failed` (type and code only).
2. Ask whether the owner has signed up and signed the desktop app in, and what they saw.
3. PR #4: an HttpOnly cookie session for the web (decision 0002). Keep the bearer header for the desktop, and add
   CSRF protection (SameSite plus an Origin check or a token). Contract first (`_templates/feature-CONTRACT.md`).
4. Then `www.freesta.sh` (after the owner's CNAME), Google sign-in on both apps, the live desktop check (ask first),
   a desktop installer and releases (`C:\DEV\SOFTWARE_RELEASE.md`), and retiring `railway.json` before 2026-12-01.

## 5. Open owner decisions (ask, don't decide)
- The Google OAuth client (for sign-in). The `www` CNAME at Spaceship.
- Desktop distribution: an installer, code signing, and where downloads live.

## 6. Environment that worked
- `cd freestash; .\.venv\Scripts\python.exe -m pytest` (121) · `ruff check src tests scripts` ·
  `python scripts/export_shared.py --check`
- `cd freestash/web; npm test` (15) · `npm run build`
- `cd freestash-desktop/tests/Freestash.Client.Tests; dotnet test` (33). It must run from that folder, for `global.json`.
- Browser check: `.claude/launch.json` → `preview_start freestash-accounts` (dev_accounts.py on :8790).
- Linux-only behaviour (production and CI run Linux): `wsl.exe -e python3 -` (3.14).
- Railway: MCP connector (`domain-status`, `list-deployments`), CLI 5.63.1. `gh` as color8.
- Traps:
  - A Python `open(p, "wb")` truncates the file before the write: build the bytes first.
  - The Bash tool collapses `\\`.
  - pytest loops that page must be bounded.

## 7. Evidence and IDs
Decisions `docs/decisions/0001–0002` (next 0003) · contract `dev plans/contracts/accounts-sync.md` · next PR #4.

## 8. Promotion candidates (owner approves)
- **Starlette path params arrive percent-decoded:** a catch-all `FileResponse(DIST / path)` is a file-read hole.
  Resolve the path, refuse NUL, and check `is_relative_to`. Add this to `railway-deploy-playbook` or a FastAPI skill.
- **Railway blocks outbound SMTP below Pro:** check the plan before choosing SMTP.
- **CSP check:** a positive control (inject an inline script and see it blocked), or "no violations" proves nothing.
- Spaceship: re-adding a Railway domain changes its CNAME target.
