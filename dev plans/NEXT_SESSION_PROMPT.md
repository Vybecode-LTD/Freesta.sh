# Next session — Freesta.sh

## 1. What and where
Freesta.sh: open-media search with per-use clearance. One product, two apps on one account: website
(`freestash/`: Python engine + FastAPI + React, deploys to Railway with Railway Postgres) and Windows desktop
(`freestash-desktop/`: Avalonia 12). Monorepo at `C:\DEV\Freesta.sh`, GitHub `Vybecode-LTD/Freesta.sh`. Read
`CLAUDE.md` (root) first, then `docs/HANDOFF.md`.

## 2. Rules that override defaults
- **Parity is binding:** every user-facing change lands in both apps in one PR, with its `shared/parity.json` row.
  Colours only via `shared/design-tokens.json`, key help only via `freestash/src/freestash/providers/keys.py`, then
  `python scripts/export_shared.py`. Never hand-edit `tokens.css` or `DesignTokens.g.cs`.
- **No Supabase.** Never print Railway variables. Never store or log a provider key in plaintext.
- Owner's OK needed for: merging, deploying, DNS, anything sent to providers, dropping a parity feature.

## 3. State (verified 2026-10-31, end of session)
- `main` = baseline 95f3cc9. Branch `feat/accounts-sync-aperture` holds all the work (see `git log main..`).
- Pushed? Check `git ls-remote origin`; at session end the GitHub repo was empty unless the owner said "push" in the
  closing turn. Open PRs: none unless pushed (first PR number is #1).
- Not deployed. Gates: pytest 99, ruff clean, vitest 6, dotnet 27 / 0 warnings, contrast gate 0 failing.

## 4. First job, then the order
1. If pushed: open/read PR #1, fix CI with batched pushes. If not: ask the owner to push.
2. Walk the owner through Railway (`freestash/IMPLEMENTATION.md` → P2); smoke-test `https://freesta.sh/api/health`,
   sign-up, a search, and the desktop signing into the live site.
3. Live on-screen check of the desktop build (computer-use; ask first, it was declined last time).
4. Then: Google sign-in on both apps (copy Seeq'r: `C:\DEV\Seeqr\backend\app\routers\auth.py` `/auth/google`).

## 5. Open owner decisions (ask, don't decide)
- Push and open PR #1 now? · Resend for reset email (needs the freesta.sh domain verified)? · Google sign-in?
- Should the desktop Collections layout match the web's drill-down exactly, or keep list + detail?

## 6. Environment that worked
- `cd freestash; .\.venv\Scripts\python.exe -m pytest` (venv exists). Accounts server: `python scripts/dev_accounts.py --port 8790`.
- NuGet: if restore says a version "can't be found", `dotnet nuget locals http-cache --clear` (stale cache, hit this session).
- Desktop against local server: env `FREESTASH_DESKTOP_HOME` + settings `RemoteUrl`. Headless renders + sync proof:
  `dotnet run --project tools/Freestash.Desktop.Snapshots -- http://127.0.0.1:8791 <out> http://127.0.0.1:8790`.
- Contrast gate: `node C:\DEV\knowledge\skills\verify-real-pass\scripts\rendered_contrast.mjs <url> --click-each "<sel>"`.

## 7. Evidence and IDs
Decisions `docs/decisions/0001` (next 0002). Contract `dev plans/contracts/accounts-sync.md`. Renders `dev plans/renders/`.

## 8. Promotion candidates (owner approves)
- Railway edge: rate limits must key on CF-Connecting-IP/XFF (already in the playbook; this project hit it at design time).
- NuGet stale http-cache gives false "package not found" (NU1102) → `dotnet nuget locals http-cache --clear`.
- axe "too short to determine" fails single-digit counters; a two-digit readout passes.
- Web/desktop parity pattern: one token JSON → CSS + C# generator, one key catalog → API + embedded JSON, parity map test.
