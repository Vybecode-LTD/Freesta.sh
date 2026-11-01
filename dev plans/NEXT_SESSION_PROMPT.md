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
  - merging PR #1, and switching the Railway branch to `main`;
  - DNS, and anything sent to providers;
  - creating accounts on production (smoke tests use made-up emails and create nothing);
  - computer-use.

## 3. State (verified 2026-11-01, end of session)
- `main` = 95f3cc9 (baseline). **PR #1** https://github.com/Vybecode-LTD/Freesta.sh/pull/1 is open, head is the
  review-fix commit on `feat/accounts-sync-aperture`. Auto-fix is on. Check CI with the ccd_pr tools; don't poll.
- Railway project **Freesta.sh** (`ba994460-f01e-4a4d-9e83-994f352b6634`): service `freestash` and Postgres.
  It deploys from the **PR branch**. Live at https://freestash-production.up.railway.app, health reports
  `auth_mode: accounts`.
- Live smoke test: search returns 401 without a session; the CF-Connecting-IP forgery fix was re-probed (429).
  IDs and owner steps: `freestash/IMPLEMENTATION.md` → P2.
- **freesta.sh doesn't resolve to Railway yet.** The domain is added in Railway; the owner sets DNS at Spaceship.
  Check with the Railway MCP `domain-status`.

## 4. First job, then the order
1. Read PR #1's CI (`mcp__ccd_pr__get_status`). Fix any red with one batched push.
2. If the owner has set DNS, check `domain-status` and then `https://freesta.sh/api/health`. Ask the owner to sign
   up on the site and sign the desktop app into it.
3. When the owner says "merge": merge PR #1, then switch the Railway source branch to `main`
   (`connect-service-source`), and check the new deployment builds from `main`.
4. Live on-screen check of the desktop build (computer-use; ask first, it was declined before).
5. Then: Google sign-in on both apps (Seeq'r: `C:\DEV\Seeqr\backend\app\routers\auth.py` `/auth/google`).
6. Before 2026-12-01: retire `freestash/railway.json` (config-as-code). The service's own settings already hold
   everything it sets.

## 5. Open owner decisions (ask, don't decide)
- Merge PR #1 now?
- Resend for reset email (needs the freesta.sh domain verified there)?
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
