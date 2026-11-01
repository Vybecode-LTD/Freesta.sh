# CLAUDE.md — Freestash

The engine, API and website of **Freesta.sh** (monorepo root: `../CLAUDE.md`, read it first: it holds the
web/desktop parity rule). **Federated search for public domain and openly licensed assets** (images, audio,
video, PBR textures, HDRIs, 3D, fonts, icons) across ~20 sources, with every result scored **GREEN / YELLOW / RED
for a specific use case** (shown to users as Clear / Check / Blocked). Open sign-up; one account on web and desktop.

Surfaces, all sharing one Python core:

| Surface | Entry | Status |
|---|---|---|
| Python core (`src/freestash/`) | `from freestash.search import Freestash` | Done, tested |
| CLI | `python -m freestash …` | Done |
| MCP server (stdio) | `python -m freestash mcp` | Done, verified over stdio |
| Web API (FastAPI) | `python -m freestash serve` | Done: accounts mode (sign-up, JWT, encrypted keys, prefs) + local mode |
| Web UI (React 19 + Vite) | `web/` | Done: Aperture redesign, sign-in, Settings with key help; contrast-gated |
| Accounts + data | `accounts.py`, `store.py` | SQLite locally, **Railway Postgres** in production (`DATABASE_URL`) |
| Avalonia desktop app | `../freestash-desktop/` | Done: same account, same look (see its CLAUDE.md) |

**Start here:** `IMPLEMENTATION.md` is the ordered runbook of what's left. Work it top to bottom.

---

## Ground rules (read before changing anything)

1. **The license engine is the product.** `src/freestash/licenses/` decides what people ship. Any change to
   `catalog.py` or `policy.py` needs a matching row in `tests/test_licenses.py::test_policy_matrix`, and
   `docs/LICENSE-POLICY.md` must be updated in the same commit. When unsure, err toward YELLOW, never GREEN.
2. **Never circumvent a provider's bot protection or rate limits.** No browser UA spoofing, no proxy
   rotation, no scraping around a 403/429. If a host blocks automated downloads, surface the landing URL
   and let a human grab it (`freestash ledger add`). This is a hard rule; it came up during the build (AIC IIIF).
3. **Identify yourself.** Every request sends `FREESTASH_USER_AGENT` + `FREESTASH_CONTACT_EMAIL`. Wikimedia,
   Poly Haven, AIC, and the Met all throttle anonymous/generic clients.
4. **Provider failures never fail a search.** Adapters raise; `Freestash._run` catches, times out
   (`FREESTASH_PROVIDER_TIMEOUT`), and reports per-provider status. Keep it that way.
5. **Parsers are pure functions** (`parse_*`) tested against recorded fixtures in `tests/fixtures/`.
   New provider = adapter + fixture + parser test + row in `docs/PROVIDERS.md`.
6. **Python CLI commands always use the `python -m` form** (`python -m pip`, `python -m pytest`,
   `python -m freestash`). The owner's machine doesn't have pip/python script dirs on PATH.
7. **Models are the contract.** `src/freestash/models.py` + `accounts.py` ↔ `web/src/lib/types.ts` ↔
   `../freestash-desktop/src/Freestash.Client/{Models.cs,Account/AccountModels.cs}` must stay in sync.
9. **Accounts:** never store a provider key unencrypted, never return one except to its owner
   (`GET /api/me/keys/{name}`), never log one. Server env keys reach users only with `FREESTASH_SHARE_SERVER_KEYS=true`.
8. The ledger is **append-only** for members (RLS enforces it). Don't add update paths.

## Commands

```bash
python -m pip install -e ".[all]"          # core + mcp + api + dev
python -m pytest                           # 79 tests, ~1s, no network
python -m pytest -m live                   # real API smoke tests (network)
ruff check src tests

python -m freestash providers                 # what's enabled
python -m freestash search "brutalist concrete" -m image -m texture -u demo
python -m freestash show artic:66144
python -m freestash download cleveland:173965 -u bundled --project aurora-template
python -m freestash check "CC BY-SA 4.0" --trust community
python -m freestash ledger export -f md --project aurora-template -o ATTRIBUTION.md
python -m freestash pd-cutoff

python -m freestash serve --reload            # API on :8787, local mode (serves web/dist if built)
python scripts/dev_accounts.py --port 8790    # accounts mode, as on Railway (throwaway DB + secrets in %LOCALAPPDATA%)
python scripts/export_shared.py               # after editing providers/keys.py or ../shared/design-tokens.json
cd web && npm install && npm run dev       # UI on :5173, proxies /api to :8787
python -m freestash mcp                       # MCP over stdio
```

## Layout

```
src/freestash/
  models.py            Asset, Verdict, SearchQuery, LedgerEntry… (the contract)
  config.py            env-driven Settings (FREESTASH_*), API keys
  http.py              shared async client: UA, retries w/ backoff, TTL cache
  licenses/
    catalog.py         license FACTS (commercial? derivatives? redistribute? merch?)
    normalize.py       any provider string/URL -> canonical license id
    policy.py          VERDICTS: license x trust x use case x date heuristic
    attribution.py     TASL credit lines (text + HTML)
  providers/           one adapter per source; registry in __init__.py
  search.py            Freestash engine: federated + streaming search, recent cache, get_asset
  download.py          file + .license.json sidecar + ledger entry
  store.py             SQLAlchemy ledger/collections (SQLite local, Supabase Postgres team)
  export.py            ATTRIBUTION.md / credits HTML / CSV
  cli.py, mcp_server.py, api/
web/                   React 19 + Vite + TS (no router lib; hash routes)
supabase/migrations/   team schema + RLS
desktop/               Avalonia app plan (not started)
docs/                  ARCHITECTURE, LICENSE-POLICY, PROVIDERS, MCP, WEB, ROADMAP, adr/
tests/                 fixtures are REAL recorded responses except files with "_synthetic"
```

## Key facts discovered during the build (don't re-learn these)

- **Met**: `/public/collection/v1/search` was retired 2026-10-01 → use `/v1.1/search` (offset/limit).
  v1.1 ignores `isPublicDomain` as a filter; check per object.
- **Wikimedia**: global API rate limits enforced since March 2026; anonymous traffic from cloud IPs gets
  429. Needs an OAuth 2.0 owner-only token (`WIKIMEDIA_ACCESS_TOKEN`). Openverse covers Commons meanwhile.
- **Openverse**: anonymous = `page_size` ≤ 20, ≤ 240 results/query, sometimes 40s+ or an empty 200.
  `excluded_source` and `license_type=commercial` work. Covers 52 image sources incl. Smithsonian & Rijksmuseum.
- **Internet Archive**: licenses are uploader-asserted; a 2025 TV clip was marked PDM. The PD date
  heuristic in `policy.py` exists because of this.
- **AIC**: needs `AIC-User-Agent`; its IIIF image host 403s automated downloads from datacenter IPs.
- **LoC**: search results have no rights info; adapter reads each item's `rights_advisory` (N+1, capped at 10).
- **Poly Haven / Fontsource**: no search endpoint; full catalogs cached 24h and ranked locally.
- **MCP SDK is 2.x**: `from mcp.server.mcpserver import MCPServer` (FastMCP was renamed);
  client results use snake_case (`structured_content`, `server_info`).
- **US public domain**: Jan 1 2026 → works ≤1930, recordings ≤1925. Jan 1 2027 → ≤1931 / ≤1926.

## Design system

**Aperture** (owner-approved, `../dev plans/design-directions.html`, direction B): cold glass strata, warm sodium
accent, the live source aperture as the signature. Geist + Geist Mono. Colours come only from
`../shared/design-tokens.json` → generated `web/src/tokens.css` (dark "Glass" + light "Frost", four accents).
Every web page passes the rendered-contrast gate (`verify-real-pass`) in both themes at 1440 and 390.

---

## Last Completed Task

**2026-11-01: ledger paging (keyset cursor, both apps), strict CSP, SMTP reset email (PR #3); SPA path-traversal
hotfix (PR #2).** Decision `../docs/decisions/0002`.

**2026-10-31: accounts on Railway Postgres + Aperture redesign (PR #1, merged 2026-11-01).**
Supabase removed; app-level accounts (open sign-up, password reset, rate limits keyed on the real client IP);
per-user Fernet-encrypted provider keys used by search; synced preferences; `GET /api/keys/catalog` with verified
where-to-get-it steps (Pexels has paused new keys; Openverse registers via a button). Web redesigned (sign-in,
Settings, Downloads page with `.license.json`), Vitest added. 99 pytest, 6 vitest.

**Next:** `../docs/HANDOFF.md`.
