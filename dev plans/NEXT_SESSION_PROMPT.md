# Next session — Freesta.sh

## 1. What and where
Open-media search with per-use clearance. One product, two apps, one account: the website (`freestash/`: Python
engine, FastAPI, React; **live on Railway**) and the Windows desktop app (`freestash-desktop/`, Avalonia 12).
Monorepo `C:\DEV\Freesta.sh`, GitHub `Vybecode-LTD/Freesta.sh`. Read the root `CLAUDE.md`, then `docs/HANDOFF.md`.

## 2. Rules that override defaults
- **Parity is binding** (root `CLAUDE.md`): every user-facing change lands in both apps in one PR.
- **No Supabase.** Never list or print Railway variables. Set secrets only via `railway variable set KEY --stdin`.
- Owner's OK is needed for: merging, DNS, anything sent to providers, creating accounts on production (smoke tests
  use made-up emails), and computer-use.

## 3. State (verified 2026-11-01, end of session)
- `main` = merge of **PR #1** (accounts, key help, Aperture, every review fix). CI green on `main`, Windows publish
  included. No open PRs; the next is #2.
- Checkout: branch **`feat/pr2-followups`** from `main`, two local docs commits, not pushed. Do PR #2 here.
- Railway project **Freesta.sh** (`ba994460-f01e-4a4d-9e83-994f352b6634`), service `freestash` + Postgres, builds
  from **`main`**. https://freestash-production.up.railway.app is healthy (`auth_mode: accounts`). IDs and owner
  steps: `freestash/IMPLEMENTATION.md` → P2.
- **freesta.sh**: the DNS is set and the domain is verified. The certificate was still being issued at session end,
  with no error.

## 4. First job, then the order
1. Check `https://freesta.sh/api/health` (if it fails, run Railway MCP `domain-status`). Then ask the owner to sign
   up on the site and sign the desktop app into it.
2. Ask the section 5 decisions, then PR #2:
   - page Downloads past 500 ledger entries (check the desktop for the same limit);
   - plus whatever the owner chooses on token storage.
   Then resolve PR #1's last 3 review threads (4437200744, 4437200772, 4437200777).
3. Live on-screen check of the desktop build (computer-use; ask first, it was declined before).
4. Google sign-in on both apps (Seeq'r: `C:\DEV\Seeqr\backend\app\routers\auth.py`, `/auth/google`).
5. Before 2026-12-01: retire `freestash/railway.json`. The service's own settings already hold all of it.

## 5. Open owner decisions (ask, don't decide)
- Resend for reset email? **Password reset doesn't work on production until then.**
- Web JWT in `localStorage`: keep it, add a strict CSP, or move to an HttpOnly cookie (the desktop shares the
  bearer format)? Record the answer in decision 0002.
- `FREESTASH_CONTACT_EMAIL`? Google sign-in? Cloudflare in front (then `FREESTASH_TRUST_CF_CONNECTING_IP=true`)?

## 6. Environment that worked
- Tests:
  - `cd freestash; .\.venv\Scripts\python.exe -m pytest`
  - `cd freestash/web; npm test`
  - `cd freestash-desktop; dotnet test --project tests/Freestash.Client.Tests` (it must run from that folder, for
    `global.json`)
- Railway: MCP connector, plus CLI 5.63.1 (browser login). `gh` as color8. Big pushes: `git -c http.postBuffer=524288000 push`.
- Traps:
  - The Bash tool collapses `\\`, so build backslashes with `chr(92)` or use the Edit tool.
  - Python `write_text` writes CRLF; pass `newline="\n"`.

## 7. Evidence and IDs
Decisions `docs/decisions/0001` (next 0002) · contract `dev plans/contracts/accounts-sync.md` · renders `dev plans/renders/`.

## 8. Promotion candidates (owner approves)
- **railway-deploy-playbook client-IP lesson:** CF-Connecting-IP first is safe only behind Cloudflare. Here a client
  forged it past the login limit on production. Use the leftmost XFF (the edge overwrites it; proven) and gate CF
  behind a setting.
- Spaceship DNS: a CNAME on `@` acts as an ALIAS, so a root domain can point at Railway.
- NuGet NU1102 "not found" can be a stale cache: `dotnet nuget locals http-cache --clear`.
- The parity pattern: one token JSON → CSS + C#, one key catalogue → API + embedded JSON, a parity-map test.
