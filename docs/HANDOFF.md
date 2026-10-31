# Handoff — Freesta.sh (2026-10-31)

## State
- Monorepo initialised: `main` = imported v0.1.0 baseline (95f3cc9). Work on **`feat/accounts-sync-aperture`**
  (e962820 engine accounts · 35cb966 web · daaad0d desktop + parity + CI · docs commit after). **Nothing pushed**;
  the GitHub repo `Vybecode-LTD/Freesta.sh` is empty. No PR yet (the first will be #1).
- Not deployed. Railway steps: `freestash/IMPLEMENTATION.md` → P2 (owner, dashboard).
- Decisions (owner, this session): Railway Postgres, no Supabase · open sign-up · keys encrypted in the account ·
  desktop uses the hosted engine by default · the **Aperture** look. Record: `docs/decisions/0001`.

## Done this session
- Engine: app-level accounts (bcrypt, JWT + token_version, reset by email, rate limits on the real client IP),
  Fernet-encrypted per-user keys used by search, synced prefs, verified key catalog (`/api/keys/catalog`),
  Openverse register endpoint. Windows UTF-8 bug fixed with a regression test.
- Web + desktop: same nav, sign-in, Settings with key help under every input, Downloads with `.license.json`,
  Aperture redesign from one token file. Parity gates: `shared/parity.json`, generated tokens + key catalog, nav test.
- Evidence: pytest 99 · ruff clean · vitest 6 · dotnet 27 / 0 warnings · rendered-contrast gate 11 runs, 136 states,
  0 failing · drawer axe-clean · no sideways scroll at 390 px · desktop sign-up → key + accent seen on the web.

## Next
1. Owner: push + PR (#1), then Railway P2 + DNS for freesta.sh. Smoke test on the live URL.
2. Live check of the desktop build on screen (owner declined computer-use this session): sign up, save a key, see it on the web.
3. Google sign-in on both apps (Seeq'r's loopback PKCE) once a Google Cloud OAuth client exists.
4. Alembic before the first change to an existing table; thumbnail proxy for hosts that block hotlinks (CORP).

## Warnings
- `FREESTASH_SECRETS_KEY` must be backed up; changing it makes every saved key unreadable.
- Pexels has **paused new API keys** (checked 31 Oct 2026); the help says so. Re-check before removing the notice.
- The web Collections page drills down; the desktop shows list + detail side by side (same features, wider screen).
- Rate limiter is in-process: fine for one Railway replica, move it to Postgres/Redis before scaling out.
