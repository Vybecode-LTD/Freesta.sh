# CLAUDE.md — Freesta.sh

## Identity
Freesta.sh: federated search for public-domain and openly licensed media (~20 museums, archives and libraries),
with every result **cleared per use** (reference / demo / client / bundled / merch). One product, two apps:
the website at **freesta.sh** and a Windows desktop app, on **one account**. GitHub: `Vybecode-LTD/Freesta.sh`.
Deploys to **Railway** (one service + Railway Postgres). **No Supabase** (owner, 2026-10-31).

## Current State
- `main` holds PRs #1–#8, all live and verified 2026-11-01/02 (#4: accounts mode needs a database URL; #5: cookie
  session; #6: admin screen and shared keys):
  - #1: accounts, synced keys + prefs, key help, the Aperture redesign on both apps, parity gates;
  - #2: the path-traversal hotfix;
  - #3: ledger paging, the CSP, SMTP reset email.
  PRs #5 (the website's HttpOnly cookie session) and #6 (site administration + shared keys) merged 2026-11-02 and are
  live, verified on production. The owner is the production admin (granted 2026-11-02). `docs/HANDOFF.md`.
- **PR #7** (merged 2026-11-02 as f1737d6, live, verified on production): results grouped by category and query words
  as chips, both apps; `shared/categories.json` → `export_shared.py`; `GET /api/search/parse`. Contract
  `dev plans/contracts/grouped-results.md`.
- **PR #8** (merged 2026-11-02 as 71a29d6, live: the production bundle carries "Game assets"; not checked signed in): packs
  (Iconify sets, Freesound packs, Internet Archive bundles) and brush/shape/sprite, both apps; brush and pack policy rows;
  Packs switch, pack words, Game assets preset. Contract `dev plans/contracts/packs-and-new-kinds.md`.
- **PR #9** (open 2026-11-04 from `feat/pr9-github-curated-packs`, verified locally; not merged): GitHub game-asset
  repos as packs (Packs on only; the site's `GITHUB_ACCESS_TOKEN` on `#/admin`) and curated packs the admin records on
  `#/admin` (form + JSON import, table `curated_packs`). Contract `dev plans/contracts/github-and-curated-packs.md`.
  Decisions: `docs/decisions/0002` (Spacemail SMTP, CSP then cookie, no Cloudflare); `0003` (admin-held keys, then
  grouped results, packs, brush/shape/sprite, web search; plan `dev plans/2026-11-01-packs-web-admin-plan.md`).
- **Live** on Railway (project **Freesta.sh**, service `freestash` + Postgres) at **https://freesta.sh** (certificate
  valid 2026-11-01) and https://freestash-production.up.railway.app, building from `main`. IDs and steps:
  `freestash/IMPLEMENTATION.md` → P2.
- Gates 2026-11-04 (PR #9 branch): pytest 241 · ruff clean · export check · vitest 54 · web build · dotnet 61 · 0 warnings.
  Rendered contrast on `#/admin` with curated packs (and editing one): both themes, 1440 + 390, hovers, 0 failing,
  positive control fails.

## The parity rule (binding)
**Web and desktop are the same product.** Every user-facing change lands in both apps in the same pull request:
- Add or update the feature's row in `shared/parity.json` (a one-platform feature needs a `why`).
- Colours: edit `shared/design-tokens.json`, then `python scripts/export_shared.py` (in `freestash/`) writes
  `web/src/tokens.css` and the desktop's `Services/DesignTokens.g.cs`. Never hand-edit those two.
- Categories (labels, order, query words): edit `shared/categories.json`; the same script writes the engine's
  `categories_data.py`, the web's `lib/categories.ts` and the desktop's `Freestash.Client/Categories.g.cs`.
- Key help: edit `freestash/src/freestash/providers/keys.py` (`KEY_CATALOG`), then the same script writes
  `shared/provider-keys.json` (embedded in the desktop). Re-check a provider's signup page before changing its steps.
- Same words in both: nav labels and order, CLEAR / CHECK / BLOCKED, filter labels.
- `freestash/tests/test_parity.py` + `test_key_catalog.py` fail on drift; CI runs `export_shared.py --check`.

## Commands
```bash
cd freestash && python -m pytest && ruff check src tests scripts && python scripts/export_shared.py --check
cd freestash && python scripts/dev_accounts.py --port 8790     # API + built web in accounts mode (throwaway DB in %LOCALAPPDATA%)
cd freestash/web && npm test && npm run build
cd freestash-desktop && dotnet build Freestash.Desktop.sln && dotnet test --project tests/Freestash.Client.Tests
cd freestash-desktop && dotnet run --project tools/Freestash.Desktop.Snapshots -- http://127.0.0.1:8791 <out> http://127.0.0.1:8790
```
Desktop against a local server: set `FREESTASH_DESKTOP_HOME` to a throwaway folder (keeps your real settings clean).

## Architecture (brief)
`freestash/`: Python engine + FastAPI (`api/`) + React web (`web/`). Accounts: `accounts.py` (bcrypt, HS256 JWT with
`token_version`, Fernet-encrypted provider keys, synced `UserPrefs`), routes in `api/auth.py` + `api/account.py`.
Search runs with the caller's own keys (`providers/keys.py::settings_with_keys`). `freestash-desktop/`: Avalonia 12
client of the same API (`Freestash.Client/Account/*`), hosted engine by default, local Python engine optional.

## Critical gotchas
- Accounts need `DATABASE_URL=${{Postgres.DATABASE_URL}}` on `freestash`. Deleting the Postgres service empties that
  reference; the app used to fall back to a SQLite file that each deploy wiped (2026-11-01). It now refuses to start.
- Behind Railway's edge the peer IP is the proxy: rate limits key on `api/auth.py::_ip` (leftmost XFF, which the edge
  overwrites). `CF-Connecting-IP` is forgeable unless Cloudflare fronts the domain: trust it only with
  `FREESTASH_TRUST_CF_CONNECTING_IP=true` (forged rotation got past the login limit on production, 2026-11-01).
- The SPA catch-all serves only files inside `web/dist` (`api/app.py::spa_file`): route paths arrive percent-decoded,
  so `/..%2f..%2fpyproject.toml` read the server's own files on production until PR #2 (2026-11-01).
- Admins are granted only by `python -m freestash admin grant <email>` on the server, or on `#/admin`; never by an
  email address, since sign-up doesn't prove an address (PR #6 review). Members search on the site's keys (admin-stored,
  then env) unless they add their own; caps and the meter are in-process / per UTC day (one replica). Admin routes take
  `api/admin.py::Admin`; every admin write goes to `admin_audit`, never with a key value.
- The website signs in with an HttpOnly cookie (`freestash_session`, Path `/api`); the desktop uses bearer. The CSRF
  Origin check lives in `api/auth.py::current_user`, so a new route must take `User`/`MaybeUser` and never read the cookie itself.
- `FREESTASH_SECRETS_KEY` encrypts users' keys: rotating it makes saved keys unreadable (users re-save). Back it up.
- Text colours: never `--text-faint` / `TextFaintBrush` for words (3:1). Colour a link by its own class.
- Windows: open text files with `encoding="utf-8"` (cp1252 crashed exports; `tests/test_cli.py`).

## Project map
| Topic | File | Read this when |
|---|---|---|
| Handoff | `docs/HANDOFF.md` | starting a session |
| Next agent's brief | `dev plans/NEXT_SESSION_PROMPT.md` | starting a session |
| Decisions | `docs/decisions/` | before re-deciding accounts, keys, desktop default, the look |
| Accounts contract | `dev plans/contracts/accounts-sync.md` | changing auth, keys, prefs or their API |
| Design board | `dev plans/design-directions.html` (+ `renders/`) | changing the look |
| Engine / web | `freestash/CLAUDE.md`, `freestash/IMPLEMENTATION.md` | working in `freestash/` |
| Desktop | `freestash-desktop/CLAUDE.md`, `freestash-desktop/IMPLEMENTATION.md` | working in `freestash-desktop/` |
