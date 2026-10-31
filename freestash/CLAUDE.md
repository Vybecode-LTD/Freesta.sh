# CLAUDE.md — Freestash

Internal tool for VybeCod.ing / Vibrant Mindz: **federated search for public domain and openly licensed
assets** (images, audio, video, PBR textures, HDRIs, 3D, fonts, icons) across ~20 sources, with every
result scored **GREEN / YELLOW / RED for a specific use case**. Used by a small team for demo website
templates, client work, plugin factory libraries, and app assets.

Surfaces, all sharing one Python core:

| Surface | Entry | Status |
|---|---|---|
| Python core (`src/freestash/`) | `from freestash.search import Freestash` | Done, tested |
| CLI | `python -m freestash …` | Done |
| MCP server (stdio) | `python -m freestash mcp` | Done, verified over stdio |
| Web API (FastAPI) | `python -m freestash serve` | Done, tested (local + Supabase auth) |
| Web UI (React 19 + Vite) | `web/` | Done, builds clean, screenshots verified |
| Supabase schema + RLS | `supabase/migrations/` | Done, RLS verified on real Postgres 16 |
| Avalonia desktop app | `desktop/` | **Planned**: see `desktop/README.md` |

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
7. **Models are the contract.** `src/freestash/models.py` ↔ `web/src/lib/types.ts` ↔ `supabase/migrations/*`
   ↔ `src/freestash/store.py` must stay in sync. The future Avalonia app consumes the same JSON.
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

python -m freestash serve --reload            # API on :8787 (serves web/dist if built)
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

Dark identity: `#0a0a0a` canvas, Ember `#e8440a` accent, Geist Sans + JetBrains Mono, OKLCH tokens
(`web/src/styles.css`). To reskin with **Machined Light**, point Claude Code at the
machined-light-design-system repo and swap the tokens; component class names are stable.

---

## Last Completed Task

**2026-10-30 — v0.1.0 scaffold, built in claude.ai and handed to Claude Code.**

- Core engine, 20 provider adapters (15 live-verified against real responses, 5 keyed ones from docs),
  license policy engine with trust levels and the US PD date heuristic.
- CLI, MCP server (7 tools), FastAPI with SSE streaming search, React UI (search, drawer with verdict
  matrix, collections, ledger, license check, sources).
- Supabase migration with RLS, verified on Postgres 16 with three simulated users.
- 79 tests passing, ruff clean, `npm run build` clean (TS 7, Vite 8).

**Next:** `IMPLEMENTATION.md` → P0.
