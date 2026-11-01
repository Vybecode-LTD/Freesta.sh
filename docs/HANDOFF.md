# Handoff — Freesta.sh (2026-11-01)

## State
- **PR #1 is merged into `main`** (https://github.com/Vybecode-LTD/Freesta.sh/pull/1, a merge commit, on the owner's
  OK). CI was green on its last code commit, c83dda4. No PRs are open; the next is #2.
- **Live on Railway** at https://freestash-production.up.railway.app: project **Freesta.sh**, service `freestash` and
  Postgres, **building from `main`**. `/api/health` reports `auth_mode: accounts`. Facts, IDs and owner steps:
  `freestash/IMPLEMENTATION.md` → P2.
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
- Fixed 4 of CodeRabbit's findings, each with a regression test:
  - An unknown `FREESTASH_AUTH_MODE` now fails at startup instead of serving everyone anonymously.
  - Mail logs carry no reset link and no address.
  - `dev_accounts.py` always uses its own SQLite file.
  - One malformed URL can't crash Downloads.
  - Two other findings were already fixed.
- Three findings are still open on PR #1:
  - Resend before launch: owner.
  - JWT in `localStorage` versus a cookie or CSP: owner.
  - Ledger past 500 entries on Downloads: follow-up.
- CodeRabbit's 18 minor comments were fixed in one batch. Two (the session token's server and mode) were already
  covered by `TokenFor`. Highlights:
  - bcrypt now runs in the thread pool;
  - `/forgot` mails in the background, so an outage can't reveal who has an account;
  - the rate limiter sweeps idle keys;
  - names too long for Postgres get a 400;
  - Openverse registration mails only the account's own address, 3 an hour;
  - a late 401 for an old token no longer signs out its replacement;
  - "sign out everywhere" clears the local session only once the server confirms, on both apps.
- Gates: pytest 113 · ruff clean · export check clean · vitest 13 · web build clean · dotnet 32 · 0 warnings.
- Merged PR #1 on the owner's OK, and switched the Railway source to `main`.

## Next
1. Owner: DNS at Spaceship (P2 step 1). Then check `https://freesta.sh/api/health`, sign up on the site, and sign
   the desktop app into it (default server `https://freesta.sh`).
2. The three review threads still open on the merged PR #1:
   - Resend for reset email (owner; thread 4437200744);
   - where the web keeps the JWT (owner; thread 4437200772; record the answer in decision 0002);
   - paging Downloads past 500 ledger entries (thread 4437200777): a small PR #2 with a desktop parity check.
3. Live on-screen check of the desktop build (computer-use was declined before; ask first).
4. Google sign-in on both apps (Seeq'r's loopback PKCE); Alembic; thumbnail proxy; config-as-code exit before 2026-12-01.

## Warnings
- Copy `FREESTASH_SECRETS_KEY` from Railway → freestash → Variables into a password manager. Losing or changing it
  makes every saved provider key unreadable.
- No `RESEND_API_KEY` yet, so **password reset doesn't work on production**: no email is sent, and links are no
  longer logged. The owner decides on Resend (needs the freesta.sh domain verified there).
- `FREESTASH_CONTACT_EMAIL` is unset. The User-Agent carries `+https://freesta.sh` as the contact; set an address if a
  provider asks.
- Rate limiter is in-process: fine for one replica, move it to Postgres/Redis before scaling out.
- Pexels has paused new API keys (checked 31 Oct 2026); the help says so.
