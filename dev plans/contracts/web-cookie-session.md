---
feature: web-cookie-session
status: done
approved: 2026-11-01 (decision 0002 chose the cookie; decision 0003 put it first)
plan: dev plans/2026-11-01-packs-web-admin-plan.md (§4 step 1)
pr: 5
---

# Contract: the website signs in with an HttpOnly cookie

## 1. Goal
The website never holds its sign-in token in script-readable storage: the server keeps it in an HttpOnly cookie.
An XSS can no longer copy the token off the machine. The desktop keeps its bearer token, unchanged.

## 2. Interfaces
- **Opting in:** a request header `X-Freestash-Session: cookie` on `POST /api/auth/login`, `/register` and
  `/change-password`. With it, the response sets the cookie, and its body is
  `{"token_type": "cookie", "user": {...}}` with **no `access_token`**. Without it, nothing changes:
  `{"access_token", "token_type": "bearer", "user"}`. This is what the desktop and the CLI send today.
- **The cookie:** `freestash_session=<the same HS256 JWT>`, with `HttpOnly; SameSite=Lax; Path=/api; Max-Age=token_days×86400`.
  It is `Secure` unless the request's Host is a loopback name (`localhost`, `127.0.0.1`, `[::1]`). Railway's edge
  speaks HTTPS, and uvicorn there sees `http`, so the scheme can't decide it.
- **`freestash.api.auth.current_user` / `optional_user`:** the bearer header comes first, then the cookie. A request
  that has both uses the bearer.
- **CSRF:** a cookie-authenticated request whose method isn't GET, HEAD or OPTIONS must carry an `Origin` (or, failing
  that, a `Referer`) whose host matches one of: the request's `Host`; the host of `FREESTASH_PUBLIC_URL`; or a host
  in `FREESTASH_CORS_ORIGINS`. Otherwise it gets `403 "Cross-site request refused."`. Bearer requests are never checked.
  The same check runs on the three opt-in auth routes.
- **New `POST /api/auth/logout` → 204.** It clears the cookie (`Max-Age=0`, same Path) and needs no session.
  `POST /api/auth/logout-all` also clears it.
- **Web `lib/session.ts`:** `Session = { user: SessionUser }`. There is no token. `localStorage["freestash.session"]`
  holds only the user, so the shell draws at once and other tabs follow a sign-out. A value saved in the old format
  (with a `token`) is deleted on load: that browser has no cookie yet, so it signs in once. Each `setSession` bumps an epoch (`sessionEpoch()`); a 401 signs
  out only if the epoch hasn't moved since the request was sent. `getToken` is removed.
- **Web `lib/api.ts`:** every request is `credentials: "include"` (it also covers a cross-origin `VITE_API_BASE`); the auth calls send `X-Freestash-Session: cookie`;
  `api.signOut()` calls `/api/auth/logout`. Settings → Sign out and the 401 path use it.

## 3. Data
None. Same JWT and `token_version` revocation; no server-side session table.

## 4. Files
`freestash/src/freestash/api/auth.py` (cookie helpers, CSRF check, logout) · `freestash/tests/test_accounts.py` ·
`freestash/web/src/lib/session.ts`, `api.ts`, `session.test.ts` · `freestash/web/src/pages/SettingsPage.tsx`, `SignInPage.tsx` ·
`freestash/docs/WEB.md` (auth section).

## 5. Conventions this follows
Root `CLAUDE.md` → Critical gotchas (`_ip`, the CSP) · `freestash/CLAUDE.md` ground rule 9 (never log or return a
key) · skill `jwt-session-revocation` (`token_version` stays the revocation path).

## 6. Non-goals
- No change to the desktop, CLI or MCP: they stay on bearer.
- No server-side session store. A single sign-out clears this browser's cookie; "Sign out everywhere" still revokes.
- No `__Host-` cookie prefix: it needs `Secure` and `Path=/`, which breaks the http dev server.
- No CSRF token. SameSite=Lax plus the Origin check is what decision 0002 called for.

## 7. Acceptance
- `test_accounts.py`:
  - `test_web_sign_in_sets_an_httponly_cookie_and_returns_no_token`: the flags, and no `access_token` in the body.
  - `test_the_cookie_signs_requests_in`
  - `test_a_cross_site_write_with_the_cookie_is_refused`: a foreign Origin gets 403, a missing Origin gets 403,
    the site's own Origin works, and a bearer write with a foreign Origin still works.
  - `test_logout_clears_the_cookie`
  - `test_desktop_sign_in_is_unchanged`
  - `test_cookie_is_not_secure_only_on_loopback`
- `session.test.ts`: no token is persisted; an old-format token is dropped on load; the epoch guard; `signOut` calls logout.
- **Live:** on the dev server (:8790), sign up in the browser pane. DevTools shows `freestash_session` HttpOnly,
  `localStorage` has no token, search streams results, and Sign out clears the cookie.

## 8. Open questions
None.

## Changes after approval
- 2026-11-01, during the build: an old-format saved session is deleted rather than kept without its token (a shell
  with no cookie behind it would only bounce to sign-in on the first request). `credentials` is `include`, not
  `same-origin`, so a cross-origin `VITE_API_BASE` still works.
