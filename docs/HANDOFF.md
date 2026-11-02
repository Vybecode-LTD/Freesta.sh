# Handoff — Freesta.sh (2026-11-01, third session)

## State
- `main` = the merge of **PR #4** (a683d67). PRs #1–#4 are merged and **live**: deploy af809fd6, health
  `auth_mode: accounts`, verified 2026-11-02.
- **PR #5 is built on `feat/pr5-followups`, not pushed.** The website now signs in with an HttpOnly cookie, per
  decision 0002 and the contract `dev plans/contracts/web-cookie-session.md`:
  - The auth calls send `X-Freestash-Session: cookie`. The server sets `freestash_session` (`SameSite=Lax`,
    `Path=/api`, `Secure` except on loopback), and the body carries no token.
  - A cookie-signed write must carry the site's own Origin (or Referer), or it gets 403.
  - There's a new `POST /api/auth/logout`. "Sign out everywhere" also clears the cookie.
  - The desktop is unchanged (bearer).
  - Web localStorage holds only the user. An old saved token is deleted on load, so web users sign in once after the deploy.
  - Verified live on the dev server (:8790): sign-up, script can't read the token, reads, a write and the search
    stream all work on the cookie alone, and Sign out leaves `/api/auth/me` at 401.
- Gates on the branch: pytest 128 · ruff · export check · vitest 18 · web build. The desktop is untouched (dotnet 33 at PR #3).
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
1. **Owner OK → push `feat/pr5-followups` and open PR #5.** After the merge and deploy, check on https://freesta.sh:
   sign in, confirm DevTools shows `freestash_session` as HttpOnly and Secure, search, then sign out.
2. **PR #6: admin + shared keys** (plan §3·3). Contract first. Its pieces:
   - `users.is_admin`, with the first admin set by `FREESTASH_ADMIN_EMAILS`;
   - a `server_keys` table, Fernet-encrypted;
   - per-user caps and a usage meter;
   - 24 h caching (Pixabay requires it);
   - a web-only admin screen (`parity.json` row) and an audit log;
   - the member key list made optional.
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
