---
feature: admin-shared-keys
status: done
approved: 2026-11-01 (decision 0003: the owner accepted plan §3·3; "Yes, start PR #6" 2026-11-02)
plan: dev plans/2026-11-01-packs-web-admin-plan.md (§3 ask 3, §4 step 2)
pr: 6
---

# Contract: an admin screen, and searches that run on the site's keys

## 1. Goal
The owner sets provider keys once, on an admin screen, and every member's search uses them. A member's own key is
optional and raises only their limits. The admin can also:
- cap searches per member and see how much of each shared quota is spent;
- open or close sign-up and turn sources on or off;
- make users admins or disable them;
- read an audit log of every admin change.

## 2. Interfaces
- **Admins:** granted only by `python -m freestash admin grant|revoke|list <email>` on the server (Railway:
  `railway ssh`), or by another admin on the screen. No email address makes an admin by itself (see Changes after
  approval). `FREESTASH_SHARE_SERVER_KEYS` is **retired**: decision 0003 makes the shared keys the rule.
- **Key order** (`providers/keys.py::settings_with_keys(base, own, site)`): the member's own key, then the admin's
  stored key, then the env key.
- **Admin routes.** All are `/api/admin/*`. A non-admin gets 403. With `FREESTASH_AUTH_MODE=none` they all answer 404.
  - `GET  /admin/keys` → `[{name, provider, provider_name, label, limits, source: "admin"|"env"|null, hint, updated_at, last_ok_at, last_error, last_error_at}]`
  - `PUT  /admin/keys` `{values: {NAME: str|null}}` → the same list (null or "" removes the stored key)
  - `POST /admin/keys/{name}/test` → `{ok, elapsed_ms, error}`. It runs a one-result search with that key alone
    and records `last_ok_at` or `last_error`.
  - `GET  /admin/settings` → `{signup_open, searches_per_hour, disabled_providers}`
  - `PUT  /admin/settings`, with any subset of those → the full settings
  - `GET  /admin/usage` → `[{provider, provider_name, today, month, limits}]`. `today` and `month` are
    `{calls, errors}`, counting searches sent with the **site's** key (UTC days).
  - `GET  /admin/users?q=` → `[{id, email, display_name, created_at, last_seen_at, is_admin, disabled}]` (newest 200)
  - `PATCH /admin/users/{id}` `{is_admin?, disabled?}` → that user. An admin can't change their own flags.
  - `GET  /admin/audit?before=<iso>` → `[{at, admin_email, action, target, detail}]`, newest 50
- **Changed routes:**
  - `GET /api/auth/me` and the auth responses' `user` gain `is_admin`.
  - `GET /api/me/keys` rows gain `site: bool`: Freesta.sh has a key for it.
  - A disabled account gets 403 "This account is disabled." on sign-in and on every authenticated call.
  - `/api/search` and `/api/search/stream` return 429 once a non-admin passes `searches_per_hour` (in-process
    limiter, one replica).
  - Sign-up follows the admin's `signup_open` (env sets the default).
- **Web:**
  - `#/admin` is not in the nav, so nav parity holds. An admin reaches it from Settings → "Site administration".
  - `pages/AdminPage.tsx` has sections Keys, Limits, Sources, Usage, Users, Audit.
  - `lib/admin.ts` holds the pure helpers, with `admin.test.ts`.
  - The member key list keeps its place. Its sub-line and per-row status say "Freesta.sh's key" when `site` is true.
- **Desktop:** `KeyState` gains `Site`; the Settings key rows show the same status and sub-line. There is no admin screen.

## 3. Data
New tables only. No existing table changes, so there's still no Alembic: `create_all` makes them on start.

| Table | Column | Type | Null | Default / FK / index |
|---|---|---|---|---|
| user_status | user_id | uuid | no | PK, FK users.id cascade |
| | is_admin, disabled | bool | no | false |
| | last_seen_at, updated_at | timestamptz | yes / no | — / now |
| server_secrets | name | varchar(64) | no | PK (a `KEY_CATALOG` name) |
| | ciphertext (Fernet, `FREESTASH_SECRETS_KEY`), hint (last 4) | text, varchar(8) | no | — |
| | updated_at, updated_by, last_ok_at, last_error, last_error_at | | yes | — |
| site_settings | key | varchar(64) | no | PK |
| | value | json | no | — |
| provider_usage | provider, day | varchar(50), date | no | PK (provider, day) |
| | calls, errors | int | no | 0 |
| admin_audit | id, at, admin_id, action, target, detail (json, never a key value) | | | PK id, index at |

## 4. Files
- **Server:** `freestash/src/freestash/admin.py` (new tables + `AdminService`); `api/admin.py` (new routes);
  `accounts.py` (`UserStatusRow`, disabled and admin checks); `api/auth.py`, `api/app.py`, `api/account.py`;
  `providers/keys.py`; `config.py`.
- **Tests:** `tests/test_admin.py` (new); `test_accounts.py`.
- **Web:** `web/src/pages/AdminPage.tsx`, `lib/admin.ts` + `admin.test.ts`, `App.tsx`, `SettingsPage.tsx`, `lib/api.ts`, `lib/types.ts`.
- **Desktop:** `freestash-desktop/src/Freestash.Client/Account/AccountModels.cs`, the Settings view model and view.
- **Shared and docs:** `shared/parity.json` (an `admin` row, web only, with the reason).

## 5. Conventions this follows
- Root `CLAUDE.md`: the parity rule and the gotchas (one replica; never print Railway variables).
- `freestash/CLAUDE.md` ground rule 9: keys are encrypted, never returned and never logged. The admin's keys get the
  same treatment as members', with not even a reveal.
- Skill `moderation-audit-log`: append-only audit rows.

## 6. Non-goals
- No web-search budget or caps (the web or AI search PR).
- No curated-pack list (step 5).
- No admin screen on the desktop.
- The member key list stays open, not collapsed: each row's status already says which keys the site covers.
- No multi-replica limiter.
- No per-request HTTP counting: the meter counts searches sent to each source, which is close to its request count.

## 7. Acceptance
- **`test_admin.py`:**
  - an admin granted by the server command, a 403 for members, a 404 in local mode; an email address alone never makes an admin;
  - a stored key is encrypted and never returned, and its audit row has no value;
  - member search uses the site key, a member's own key wins, and the env key is the last fallback;
  - the cap returns 429 and admins are exempt;
  - closing sign-up refuses registration;
  - a disabled source isn't searched;
  - a disabled user gets 403 and can't sign in, and an admin can't change their own flags;
  - usage counts only site-key calls;
  - Test records ok or error;
  - `is_admin` appears in `/api/auth/me`, and `site` in the member's key list.
- **`admin.test.ts`:** the status and usage helpers. **Desktop:** a `KeyState` JSON test.
- **Live (dev server :8790, the admin granted with `dev_accounts.py --grant-admin`):**
  - sign up as the admin, store a key, run Test, and check a second member's search uses it;
  - pass the cap;
  - check the screen in the rendered-contrast gate in both themes at 1440 and 390.

## 8. Open questions
None. The owner's answers are decision 0003.

## Changes after approval
- 2026-11-02, PR #6 review (Codex):
  - **P1:** `FREESTASH_ADMIN_EMAILS` made whoever first signed up with a listed address an admin. Sign-up doesn't
    verify email, so that's a takeover. It's removed: admins come from `python -m freestash admin grant` on the
    server (audited as "server command"), and `dev_accounts.py --grant-admin` does the same locally.
  - **P2:** the key Test ran on the shared HTTP client, so an hour-old cached success passed a revoked key. It now
    runs on a fresh client.
- 2026-11-02, during the build:
  - The usage table has separate "Today" and "This month" columns (`lib/admin.ts::countCell`), because the
    one-line summary wrapped at 1440.
  - Openverse's site key gets a "register in your own Settings, then paste the pair here" note instead of a
    disabled Register button.
  - The search stream's error carries the server's own words: the cap's 429 showed raw JSON in the toast.
