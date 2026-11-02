# Handoff — Freesta.sh (2026-11-02, third session)

## State
- `main` = the merge of **PR #6** (2cfc414), merged 2026-11-02 on the owner's OK. PRs #1–#6 are **live**. The
  repository allows auto-merge (the owner, 2026-11-02). The checkout is on `feat/pr7-grouped-results` (PR #7); its only
  commit so far is this docs update.
- **PR #6: site administration and shared keys** (decision 0003; contract `dev plans/contracts/admin-shared-keys.md`).
  Merged and live. Verified on https://freesta.sh on 2026-11-02, without creating an account:
  - `/api/admin/keys` answered 404 before the deploy and 401 after;
  - search without a session gets 401;
  - the served bundle has the admin page;
  - the five new tables exist on production Postgres;
  - production has 1 account.

  Five review findings were fixed before the merge (Codex P1, the email-based admin; P2, the cached key test; three
  from CodeRabbit). What it holds:
  - `#/admin` (web only, reached from Settings → Account): site keys (stored encrypted, never returned, Test), the
    per-member hourly cap (60), sign-up open, sources on or off, the shared-quota meter, users (admin, disable) and an
    audit log that never holds a key value;
  - members search on the admin's key, then env, unless they add their own;
  - `FREESTASH_SHARE_SERVER_KEYS` is retired. Admins are granted only by `python -m freestash admin grant <email>` on
    the server (review fix: an email setting let anyone who signed up first with that address become admin);
  - new tables only (`user_status`, `server_secrets`, `site_settings`, `provider_usage`, `admin_audit`), so no Alembic;
  - both apps' key rows say "Freesta.sh's key".
  - Verified on the dev server:
    - the admin sees the link and the page;
    - a stored key never comes back, and the audit log holds only its name;
    - a member sees "Freesta.sh's key" and gets "Admins only." on `#/admin`;
    - the cap gave 200, 200, then 429, with readable words in the search toast.
  - The rendered-contrast gate passed on the admin page and Settings, in both themes at 1440 and 390 (every status
    tone), with a positive control that failed as it should.
- **PR #5: the website signs in with an HttpOnly cookie**, per decision 0002 and the contract
  `dev plans/contracts/web-cookie-session.md`:
  - The auth calls send `X-Freestash-Session: cookie`. The server sets `freestash_session` (`SameSite=Lax`,
    `Path=/api`, `Secure` except on loopback), and the body carries no token.
  - A cookie-signed write must carry the site's own Origin (or Referer), or it gets 403.
  - There's a new `POST /api/auth/logout`. "Sign out everywhere" also clears the cookie.
  - The desktop is unchanged (bearer).
  - Web localStorage holds only the user. An old saved token is deleted on load, so web users sign in once after the deploy.
  - Review fix (Codex): the stored session carries a random `gen`, so a password change still reaches other tabs.
  - Verified on the dev server (:8790): sign-up, script can't read the token, reads, a write and the search stream all
    work on the cookie alone, and Sign out leaves `/api/auth/me` at 401.
  - **Verified on https://freesta.sh** (2026-11-02, no account created):
    - logout answers 204 and clears the cookie with `HttpOnly; Path=/api; SameSite=lax; Secure`;
    - a web login and a cookie write from another site get 403, and from the site itself 401 (made-up account, bad cookie);
    - the served bundle asks for the cookie.
  - A real sign-in on production hasn't been checked: no production account exists yet.
- Gates at the PR #5 merge: pytest 128 · ruff · export check · vitest 19 · web build · CI green. On the PR #6 branch:
  pytest 140 · ruff · export check · vitest 27 · web build · dotnet 41, 0 warnings.
- **Decision 0003 (owner, 2026-11-01):**
  - Admin-held provider keys shared with every member, with caps of 60 searches an hour and 20 web searches a day.
  - Admin screen on the web only; web finds are always CHECK.
  - Order: cookie → admin → grouped results → packs and brush/shape/sprite → GitHub and curated packs → web search.
  - Plan: `dev plans/2026-11-01-packs-web-admin-plan.md`.
- **Open:** the owner proposed an "AI Search" screen (Claude Sonnet 5.5 searches, checks licences, and queues
  downloads) instead of plain Brave web search. The plan's §2b holds the assessment; the owner hasn't decided.
- Production database: the new `Postgres` service on `postgres-volume` (the first one was deleted 2026-11-01; its data
  is gone). PR #4 makes accounts mode refuse to start without `DATABASE_URL`.
- Railway is on Pro, so SMTP is allowed. Reset email is still untested on production.
- Desktop: CI artifact `freestash-desktop-win-x64` on every push to `main`; local `freestash-desktop/publish/Freestash.exe`.
  No installer, no signing, no release.

## Next
1. **Owner:** sign up again on https://freesta.sh (earlier accounts are gone). That is also the last PR #5 check: a
   search works, and Sign out returns to the sign-in page.
2. **Done 2026-11-02 (owner's OK):** `python -m freestash admin grant color8studios@gmail.com` on production
   (`railway ssh --project ba994460-f01e-4a4d-9e83-994f352b6634 --environment production --service freestash -- …`;
   this folder isn't `railway link`ed). `admin list` shows it, and `admin_audit` holds a server-command row. **Owner:**
   sign in, then Settings → Site administration: paste the provider keys and press Test on each. Any keys already in
   Railway's env serve every member now (decision 0003). Apply for Unsplash production first.
3. Then grouped results, packs and new kinds, GitHub and curated packs, and web or AI search (the owner chooses first).
4. Still open from before: the owner re-registers on production; test reset email; Postgres volume backups; delete the
   spare volume `postgres-volume-EFLf`; `www.freesta.sh`; Google sign-in; the desktop installer; retire `railway.json`
   before 2026-12-01.

## Warnings
- Back up `FREESTASH_SECRETS_KEY` (Railway → Variables) in a password manager.
- Before sharing keys, the owner applies for Unsplash production (demo mode is 50 requests an hour for everyone) and
  decides Wikimedia (its token is owner-only).
- The rate limiter is in-process: one replica only. Pexels has paused new API keys.
- OpenGameArt's robots.txt bars every Anthropic agent and most bots. itch.io bars `/search` and `/game/download/`.
  Neither gets scraped (ground rule 2).
- The local dev database (`%LOCALAPPDATA%\Freestash\dev`) holds throwaway test accounts (`cookie-check@example.test`).
