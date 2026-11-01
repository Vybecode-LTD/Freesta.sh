# Handoff — Freesta.sh (2026-11-01)

## State
- **PR #1** https://github.com/Vybecode-LTD/Freesta.sh/pull/1 (`feat/accounts-sync-aperture` → `main`), open, Auto-fix
  on. Holds the accounts + key help + Aperture work and the rate-limit fix below. `main` = baseline 95f3cc9.
  **Merging is the owner's call.**
- **Live on Railway** at https://freestash-production.up.railway.app: project **Freesta.sh**, service `freestash` and
  Postgres. `/api/health` reports `auth_mode: accounts`. The service **deploys from the PR branch**; switch it to
  `main` after the merge. Facts, IDs and owner steps: `freestash/IMPLEMENTATION.md` → P2.
- **freesta.sh is not pointing at Railway yet.** The custom domain is added in Railway, and the DNS records
  (Spaceship) are the owner's step (P2 step 1). The certificate issues once they resolve.

## Done this session
- Pushed `main` and the branch, opened PR #1. Created the Railway project: Postgres template, service from GitHub,
  root `/freestash`, healthcheck. Variables set, with both secrets piped through the CLI's stdin (never displayed).
- Live smoke test, with no accounts created:
  - health OK; the page serves; the key catalogue is public.
  - search, stream and `/api/auth/me` all return 401 without a session.
  - A forged `X-Forwarded-For` can't dodge the login limit: the edge overwrites it, and the 9th try gets 429.
- **Found on production and fixed:** a forged, rotating `CF-Connecting-IP` got 9 failed logins past the limit
  (freesta.sh isn't behind Cloudflare). `_ip` now trusts that header only with `FREESTASH_TRUST_CF_CONNECTING_IP`.
  Regression test fails before, passes after. Re-probed live: the 9th try gets 429.
- Fixed the 4 Codex review findings on PR #1, each with a regression test:
  - The desktop session is bound to the server that issued it (`SessionStore.TokenFor`), so changing the server
    never sends the freesta.sh token elsewhere.
  - Old `settings.json` files still load: the `EmberDark` / `MachinedLight` / `Ember` names are mapped.
  - Switching from the account to the local engine no longer wipes this machine's keys (`LocalKeyWrites`).
  - A web reset link opens even in a browser that's still signed in (`lib/gate.ts`).
- Gates: pytest 101 · ruff clean · export check clean · vitest 10 · web build clean · dotnet 32 · 0 warnings.

## Next
1. Owner: DNS at Spaceship (P2 step 1). Then check `https://freesta.sh/api/health`, sign up on the site, and sign
   the desktop app into it (default server `https://freesta.sh`).
2. Owner: merge PR #1 once CI is green, then switch the Railway branch to `main`.
3. Live on-screen check of the desktop build (computer-use was declined before; ask first).
4. Google sign-in on both apps (Seeq'r's loopback PKCE); Alembic; thumbnail proxy; config-as-code exit before 2026-12-01.

## Warnings
- Copy `FREESTASH_SECRETS_KEY` from Railway → freestash → Variables into a password manager. Losing or changing it
  makes every saved provider key unreadable.
- No `RESEND_API_KEY`: password-reset links are written to the deploy log only. Only the owner can read that, but
  users get no email.
- `FREESTASH_CONTACT_EMAIL` is unset. The User-Agent carries `+https://freesta.sh` as the contact; set an address if a
  provider asks.
- Rate limiter is in-process: fine for one replica, move it to Postgres/Redis before scaling out.
- Pexels has paused new API keys (checked 31 Oct 2026); the help says so.
