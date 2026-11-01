---
feature: accounts-sync
status: approved
approved: 2026-10-31 (owner chose open sign-up, keys in the account, hosted-first desktop; see docs/decisions/0001)
plan: docs/decisions/0001-accounts-sync-and-look.md
pr: TBD (repo has no PRs yet; first PR will be #1)
---

# Contract: accounts, synced keys and settings

## 1. Goal
One Freesta.sh account works on the website and the desktop app. Collections, ledger, search defaults,
appearance and provider API keys follow the user between them.

## 2. Interfaces
HTTP (FastAPI, `freestash/src/freestash/api/`). Auth = `Authorization: Bearer <jwt>` unless marked public.
- `POST /api/auth/register` (public) `{email, password, display_name?}` → 201 `AuthResponse{access_token, user}`; 409 taken; 403 sign-up closed; 429 limited
- `POST /api/auth/login` (public) `{email, password}` → `AuthResponse`; 401 bad credentials; 429
- `GET /api/auth/me` → `UserOut{id, email, display_name, created_at}` · `PATCH /api/auth/me {display_name}` → `UserOut`
- `POST /api/auth/change-password {current_password, new_password}` → `AuthResponse` (old tokens die)
- `POST /api/auth/logout-all` → 204 (bumps `token_version`)
- `POST /api/auth/forgot {email}` (public) → 200 always · `POST /api/auth/reset {token, new_password}` (public) → 204; 400 bad token
- `GET /api/me/settings` → `{data: UserPrefs, updated_at}` · `PUT /api/me/settings {data: UserPrefs}` → same
- `GET /api/me/keys` → `{keys: [{name, set, hint, updated_at}]}` · `PUT /api/me/keys {values: {NAME: str|null}}` → same
- `GET /api/me/keys/{name}` → `{name, value}` (owner only; reveal + desktop local-engine mirror)
- `GET /api/keys/catalog` (public) → `[KeySpec{name, setting, provider, provider_name, label, url, url_label, steps[], limits, optional}]`
- `GET /api/providers` → as today, `enabled` computed with the caller's keys when a token is sent

`UserPrefs` = `{default_use_case, default_max_tier, default_media[], results_per_source, theme: "dark"|"light", accent}`.
JWT claims: `sub` (user id), `ver` (token_version), `iat`, `exp` (30 days). HS256 with `FREESTASH_SECRET_KEY`.

Python: `freestash.accounts.AccountService` (register, authenticate, user, set_keys, keys_masked, reveal,
prefs, set_prefs, start_reset, finish_reset); `freestash.providers.keys.KEY_CATALOG: list[KeySpec]`;
`Freestash.search_stream(query, settings=None)` / `search(...)` / `get_asset(...)` take per-user settings.

Avalonia: `Freestash.Client.Account.AccountClient` (LoginAsync, RegisterAsync, MeAsync, PrefsAsync,
SavePrefsAsync, KeysAsync, SaveKeysAsync, RevealKeyAsync, KeyCatalogAsync); `SessionStore` keeps the token
in `SecretStore` under `FREESTASH_SESSION`. View-models: `SignInViewModel` (Email, Password, DisplayName,
IsRegister, Error, IsBusy; SubmitCommand, ToggleModeCommand, ForgotCommand); `SettingsViewModel` gains
`Account` + key rows bound to the catalog.

React: `lib/session.ts` (token in localStorage, `signIn`, `signUp`, `signOut`, `useSession`);
pages `SignInPage`, `SettingsPage`; `api.keys/saveKeys/revealKey/keyCatalog/prefs/savePrefs`.

## 3. Data (SQLAlchemy `create_all`, SQLite locally, Railway Postgres in production)

| Table | Column | Type | Null | Default / FK / index |
|---|---|---|---|---|
| users | id | uuid | no | pk |
| users | email | varchar(320) | no | unique, lower-cased |
| users | password_hash | varchar(100) | no | bcrypt |
| users | display_name | varchar(120) | yes | |
| users | token_version | int | no | 0 |
| users | created_at | timestamptz | no | now |
| user_secrets | user_id, name | uuid, varchar(64) | no | pk (user_id, name); fk users cascade |
| user_secrets | ciphertext / hint / updated_at | text / varchar(8) / timestamptz | no | Fernet; last 4 chars |
| user_prefs | user_id / data / updated_at | uuid / json / timestamptz | no | pk fk users cascade |
| password_resets | token_hash / user_id / expires_at / used_at | varchar(64) / uuid / timestamptz / timestamptz | used_at yes | pk sha256(token) |

Every user gets a personal team on register (`teams` + `team_members` role owner), so existing
collection/ledger scoping is unchanged. No RLS: the database is reached only through the API.

## 4. Files
Engine: `src/freestash/{accounts.py, mailer.py, ratelimit.py, providers/keys.py, api/auth.py, api/account.py,
api/app.py, config.py, search.py, store.py}`; delete `supabase/`. Web: `web/src/lib/{session.ts, api.ts}`,
`web/src/pages/{SignInPage, SettingsPage}.tsx`; drop `@supabase/supabase-js`. Desktop:
`src/Freestash.Client/Account/*`, `Settings/{AppSettings, ProviderKeys}.cs`, `ViewModels/{SignIn, Settings}*`,
`Views/{SignInView, SettingsView}.axaml`. Shared: `shared/provider-keys.json` (generated), `shared/parity.json`.

## 5. Conventions this follows
Seeq'r `backend/app/{auth.py, security.py, routers/auth.py}`; skills `railway-deploy-playbook`,
`verify-real-pass`; `freestash/CLAUDE.md` ground rules 4, 6, 7; `freestash-desktop/CLAUDE.md` rules 4–6.

## 6. Non-goals
Google sign-in (Seeq'r's loopback PKCE) · teams/invites UI · email verification on sign-up · Alembic ·
billing · admin console.

## 7. Acceptance
`tests/test_accounts.py`: register→login→me; duplicate email 409; wrong password 401; token dies after
change-password and logout-all; rate limit returns 429; keys encrypted at rest (ciphertext ≠ value), masked
on list, reveal only to owner; another user can't see them; search uses the caller's key (keyed provider
enabled only for that user); prefs round-trip; reset token single-use and expiring; personal team scoping.
`tests/test_key_catalog.py`: every keyed provider has a catalog entry; `shared/provider-keys.json` matches.
Desktop: `AccountClientTests` (fake handler), `KeyCatalogParityTests` (C# fallback list == shared JSON).
Live: register on the web, see the same collections and keys after signing into the desktop build.

## 8. Open questions
None.
