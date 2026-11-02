# Architecture

```
                    ┌──────────── surfaces ────────────┐
   Claude Code ───► │ MCP server (stdio)               │
   Terminal ──────► │ CLI (Typer + Rich)               │──┐
   Browser ───────► │ React UI ──► FastAPI (+SSE)      │  │   all import the same core
   (planned) ─────► │ Avalonia desktop ──► FastAPI     │  │
                    └──────────────────────────────────┘  │
                                                           ▼
 ┌──────────────────────────────── freestash core ─────────────────────────────────┐
 │ search.Freestash ── fan out (asyncio) ──► providers/* ──► http.HttpClient ──► APIs│
 │      │  per-provider timeout + status; stream batches as they land            │
 │      ▼                                                                         │
 │ licenses.evaluate(asset, use_case) → Verdict(tier, reasons, obligations, credit)│
 │      │                                                                         │
 │      ▼                                                                         │
 │ download → file + .license.json sidecar ──► store.Store (ledger, collections) │
 │                                              SQLite (local) | Supabase PG (team)│
 └────────────────────────────────────────────────────────────────────────────────┘
```

## Decisions

- **One Python core, many surfaces** (ADR 0001). CLI, MCP, and API are thin. The desktop app will be a
  client of the API, not a reimplementation of the engine.
- **Verdicts are per use case** (ADR 0002). A single "is it free?" boolean is how people get burned:
  Unsplash is fine on a demo site and not inside a template zip.
- **Trust is separate from license** (ADR 0003). The same CC0 string means different things from the
  Met and from an anonymous upload.
- **Streaming search.** Museums answer in under 1s; Openverse can take 40s. The SSE endpoint yields each
  provider's batch on arrival, so the UI fills in progressively.
- **Recent-results cache.** `get_asset(uid)` serves from what a previous search returned (persisted to
  `~/.freestash/recent.json` for the CLI/MCP), so most providers don't need a detail endpoint, and
  downloads don't re-hit APIs.
- **Ledger snapshots.** Each entry stores the full asset + verdict JSON as of retrieval. If a source
  changes its license later, you still have what it said on the day you took it.

## Request flow (web search)

0. UI → `GET /api/search/parse?q=…` when the text is new: `query_words.parse_query` reads category words out of it
   ("rain sfx" → "rain" in Audio, from `shared/categories.json`); the UI shows each pick as a removable chip
1. UI → `GET /api/search/stream?q=…&media=image&use=bundled&max_tier=yellow`
2. API → `Freestash.search_stream` → `select_providers` (enabled + media overlap) → one task per provider
3. Each provider → `search()` → `ProviderPage(assets)`; `_run` wraps it with timeout + error capture
4. As each finishes: dedupe by landing URL, `evaluate()` each asset, drop above `max_tier`, emit `batch`
5. UI interleaves batches round-robin by provider, greens first; with several media it lays them out as one section
   per category (8 each, "Show all (n)", a jump bar). Contract: `../../dev plans/contracts/grouped-results.md`

## Auth (accounts mode, the hosted app)

Open sign-up on the API itself (no third-party auth): `POST /api/auth/register|login` → an HS256 JWT carrying the
user id and `token_version` (bumped by password change and sign-out-everywhere, which kills old tokens). The desktop
app sends it as `Authorization: Bearer`; the website gets it only as an HttpOnly cookie and cookie-signed writes must
carry the site's own `Origin` (`api/auth.py::check_origin`, contract `dev plans/contracts/web-cookie-session.md`). Each account owns a personal team, so every store query stays
team-scoped. Provider keys are Fernet-encrypted per account and merged into that user's engine settings for each
search (`providers/keys.py::settings_with_keys`). Data lives in Railway Postgres; decision: `../../docs/decisions/0001`.