# CLAUDE.md — Freesta.sh

## Identity
Freesta.sh: federated search for public-domain and openly licensed media (~20 museums, archives and libraries),
with every result **cleared per use** (reference / demo / client / bundled / merch). One product, two apps:
the website at **freesta.sh** and a Windows desktop app, on **one account**. GitHub: `Vybecode-LTD/Freesta.sh`.
Deploys to **Railway** (one service + Railway Postgres). **No Supabase** (owner, 2026-10-31).

## Current State
- PR #1 (`feat/accounts-sync-aperture` → `main`): accounts, synced keys + prefs, key help, Aperture redesign
  on both apps, parity gates. `main` = the imported v0.1.0 baseline.
- **Live** on Railway (project **Freesta.sh**, service `freestash` + Postgres) at
  https://freestash-production.up.railway.app, deploying from the PR branch until the merge. freesta.sh waits for
  the owner's DNS at Spaceship. IDs and steps: `freestash/IMPLEMENTATION.md` → P2.
- Gates 2026-11-01: pytest 108 · ruff clean · vitest 11 · dotnet 32 · 0 warnings. Rendered-contrast 11 runs /
  136 states / 0 failing (2026-10-31).

## The parity rule (binding)
**Web and desktop are the same product.** Every user-facing change lands in both apps in the same pull request:
- Add or update the feature's row in `shared/parity.json` (a one-platform feature needs a `why`).
- Colours: edit `shared/design-tokens.json`, then `python scripts/export_shared.py` (in `freestash/`) writes
  `web/src/tokens.css` and the desktop's `Services/DesignTokens.g.cs`. Never hand-edit those two.
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
- Behind Railway's edge the peer IP is the proxy: rate limits key on `api/auth.py::_ip` (leftmost XFF, which the edge
  overwrites). `CF-Connecting-IP` is forgeable unless Cloudflare fronts the domain: trust it only with
  `FREESTASH_TRUST_CF_CONNECTING_IP=true` (forged rotation got past the login limit on production, 2026-11-01).
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
