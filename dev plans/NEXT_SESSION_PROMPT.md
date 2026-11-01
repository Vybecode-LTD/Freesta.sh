# Next session — Freesta.sh

## 1. What and where
Freesta.sh: open-media search with per-use clearance. One product, two apps on one account: the website
(`freestash/`: Python engine, FastAPI and React, **live on Railway**) and the Windows desktop app
(`freestash-desktop/`, Avalonia 12). Monorepo at `C:\DEV\Freesta.sh`, GitHub `Vybecode-LTD/Freesta.sh`.
Read the root `CLAUDE.md`, then `docs/HANDOFF.md`.

## 2. Rules that override defaults
- **Parity is binding** (root `CLAUDE.md`): every user-facing change lands in both apps in one PR, with its
  `shared/parity.json` row.
- **No Supabase.** Never list or print Railway variables (the playbook's secrets rule). Set a secret only through
  `railway variable set KEY --stdin`, from a value generated in the shell.
- Owner's OK is needed for:
  - merging any PR;
  - DNS, and anything sent to providers;
  - creating accounts on production (smoke tests use made-up emails and create nothing);
  - computer-use.

## 3. State (verified 2026-11-01, end of session)
- `main` = the merge of **PR #1** (https://github.com/Vybecode-LTD/Freesta.sh/pull/1). It holds accounts, key help,
  the Aperture redesign and every review fix. No PRs are open; the next is #2.
- The checkout is on **`feat/pr2-followups`**, cut from `main`, with one local docs commit (not pushed). Do PR #2's
  work on this branch so that commit goes in with it.
- Railway project **Freesta.sh** (`ba994460-f01e-4a4d-9e83-994f352b6634`): service `freestash` and Postgres.
  It builds from **`main`**. Live at https://freestash-production.up.railway.app, health reports
  `auth_mode: accounts`.
- Live smoke test: search returns 401 without a session; the CF-Connecting-IP forgery fix was re-probed (429).
  IDs and owner steps: `freestash/IMPLEMENTATION.md` → P2.
- **freesta.sh DNS is set.** The domain is verified in Railway (`domain-status`) and HTTP redirects to HTTPS.
  The certificate was still being issued at session end (no error).

## 4. First job, then the order
1. Check `https://freesta.sh/api/health` (and `domain-status` if it fails). Ask the owner to sign up on the site and
   sign the desktop app into it.
2. Ask the owner the open decisions in section 5, then do PR #2: page Downloads past 500 ledger entries, plus
   whatever the owner decides on token storage. Check the desktop for the same limit, for parity.
3. Resolve PR #1's last three review threads once each item lands.
4. Live on-screen check of the desktop build (computer-use; ask first, it was declined before).
5. Then: Google sign-in on both apps (Seeq'r: `C:\DEV\Seeqr\backend\app\routers\auth.py` `/auth/google`).
6. Before 2026-12-01: retire `freestash/railway.json` (config-as-code). The service's own settings already hold
   everything it sets.

## 5. Open owner decisions (ask, don't decide)
- Resend for reset email (needs the freesta.sh domain verified there)? **Until then, password reset doesn't work
  on production**, because links are never logged (CodeRabbit thread 4437200744, still open).
- The web keeps the JWT in `localStorage`. Keep it, add a strict CSP, or move to an HttpOnly cookie (the desktop
  uses the same bearer token)? CodeRabbit thread 4437200772 is still open. Record the answer in decision 0002.
- Downloads reads only the newest 500 ledger entries: page it (thread 4437200777, a follow-up).
- `FREESTASH_CONTACT_EMAIL` address?
- Google sign-in?
- Put Cloudflare in front? If yes, set `FREESTASH_TRUST_CF_CONNECTING_IP=true`.

## 6. Environment that worked
- `cd freestash; .\.venv\Scripts\python.exe -m pytest` (the venv exists). Web: `cd freestash/web; npm test`.
  Desktop: `dotnet test --project tests/Freestash.Client.Tests`.
- Railway: the MCP connector, plus the CLI 5.63.1 (browser login, user Vybecode LTD).
- GitHub: `gh` as color8. Push large branches with `git -c http.postBuffer=524288000 push`: the first push hung up.
- Traps:
  - The Bash tool collapses `\\` in commands, so write backslashes with `chr(92)` in Python.
  - Python `write_text` on Windows writes CRLF; pass `newline="\n"`.

## 7. Evidence and IDs
- Decisions: `docs/decisions/0001` (the next one is 0002).
- Contract: `dev plans/contracts/accounts-sync.md`.
- Renders: `dev plans/renders/`.
- The next PR number is #2.

## 8. Promotion candidates (owner approves)
- **Fix the railway-deploy-playbook's client-IP lesson.** It says to resolve CF-Connecting-IP first. That is only
  safe when Cloudflare fronts the domain; otherwise the client forges it, and that bypassed the login limit on
  production here. Resolve the leftmost XFF instead (the edge overwrites it; proven) and gate CF behind a setting.
- Spaceship DNS: a CNAME on `@` acts as an ALIAS, so a root domain can point at Railway without Cloudflare.
- NuGet NU1102 "package not found" can be a stale HTTP cache: `dotnet nuget locals http-cache --clear`.
- axe "too short to determine" fails single-digit counters; a two-digit readout passes.
- The web/desktop parity pattern: one token JSON → CSS + C#, one key catalogue → API + embedded JSON, a parity map test.
