# IMPLEMENTATION.md — ordered runbook

Work top to bottom. Each task has a done-when line. Update **Last Completed Task** in `CLAUDE.md`
after each one.

---

## P0 — Bring it up on the dev machine (Windows)

1. `python -m venv .venv` → activate → `python -m pip install -e ".[all]"`
2. `copy .env.example .env` and set at least `FREESTASH_CONTACT_EMAIL`.
3. `python -m pytest` → 79 passed.
4. `python -m freestash providers`, then `python -m freestash search lighthouse -n 3`.
5. `cd web && npm install && npm run build && cd ..` → `python -m freestash serve` → open http://127.0.0.1:8787.
6. Register the MCP server with Claude Code: `claude mcp add freestash -- python -m freestash mcp`
   (or copy `.mcp.json.example` to `.mcp.json`). Ask Claude: *"use freestash to find 6 CC0 textures of
   weathered concrete for a bundled template"*.

**Done when:** tests pass on Windows, the UI loads, and an MCP search returns results.
Watch for: Windows paths in `download.py` filenames (slugify already strips `:` and `/`), and
`asyncio` event loop policy (Python 3.11+ on Windows is fine with the default Proactor loop).

## P1 — Get keys and verify the "docs" adapters

Free keys (all take minutes): Smithsonian (api.data.gov), Freesound, Unsplash, Pexels, Pixabay,
Europeana, plus a Wikimedia OAuth 2.0 owner-only token and an Openverse app registration.

1. Put keys in `.env`. `python -m freestash providers` should show them `on`.
2. Run `python scripts/record_fixtures.py smithsonian freesound pexels pixabay unsplash wikimedia`.
   It overwrites the `_synthetic` fixtures with real (trimmed) responses.
3. Run `python -m pytest`. Fix any parser drift the real responses reveal.
4. Flip `verified_live=True` on each adapter you verified; update `docs/PROVIDERS.md`.

**Done when:** no fixture contains `"_synthetic"` and all tests pass.

## P2 — Deploy to Railway (one service + Railway Postgres)

**Live since 2026-11-01** at https://freestash-production.up.railway.app (workspace "color8's Projects", project
**Freesta.sh** `ba994460-f01e-4a4d-9e83-994f352b6634`, environment `production`). Done:
- Service `freestash` (`977b573d-bfbc-4b10-a432-26ace23770bf`): GitHub `Vybecode-LTD/Freesta.sh`, Root Directory
  `/freestash`, Dockerfile build, healthcheck `/api/health`, watch `/freestash/**`. **Builds from
  `main`** (switched from the PR branch when PR #1 merged, 2026-11-01).
- Postgres (template), referenced as `DATABASE_URL=${{Postgres.DATABASE_URL}}`. Schema is created at startup.
- Variables: `FREESTASH_AUTH_MODE=accounts`, `FREESTASH_PUBLIC_URL`, `FREESTASH_CORS_ORIGINS=["https://freesta.sh"]`,
  `FREESTASH_SIGNUP_OPEN=true`, and the two secrets, generated and set through the CLI's stdin (never shown):
  `FREESTASH_SECRET_KEY` (signs sessions) and `FREESTASH_SECRETS_KEY` (encrypts users' keys: **copy it from the
  Variables tab into your password manager**; losing it makes every saved key unreadable).
- Custom domain `freesta.sh` (port 8080): **verified 2026-11-01**. DNS is at Spaceship (nameservers
  `launch1/2.spaceship.net`); the root is a `CNAME @ → xx0vt3ns.up.railway.app`, which Spaceship serves as an ALIAS.
  Re-adding the domain in Railway issues a new target: update that record if it ever happens again.

Owner steps left:
1. Optional variables: `FREESTASH_CONTACT_EMAIL` (sent to providers in the User-Agent), `RESEND_API_KEY` +
   `FREESTASH_EMAIL_FROM` for reset email. **Without it password reset doesn't work**: no email goes out, and links
   are never written to the log (log access would be account takeover).
   `FREESTASH_TRUST_CF_CONNECTING_IP=true` **only** if the domain moves behind Cloudflare's proxy.
2. **Done when** `https://freesta.sh/api/health` answers `{"ok":true,...,"auth_mode":"accounts","signup_open":true}`,
   you can create an account on the site, and the desktop app (default server `https://freesta.sh`) signs into it.

Before 2026-12-01: Railway retires config-as-code (`railway.json`); it already refuses a config-file path on new
services. That's why the healthcheck, restart policy and watch path are set on the service itself, so nothing breaks; delete `railway.json` or move to `.railway/railway.ts` (read the playbook's IaC
warning first: a whole-project file deletes whatever it omits). Add Alembic before the first change to an existing table.
## P3 — CLI/MCP remote mode (team ledger from the terminal)

Today the CLI/MCP write to a local SQLite ledger. Add `FREESTASH_API_URL` + `FREESTASH_API_TOKEN`:
when set, `ledger list/export/add` and MCP `download_asset`/`export_credits` call the hosted API
(`POST /api/ledger`, `GET /api/ledger/export`) instead of the local Store. Add a `freestash login` command
that runs the Supabase magic-link flow and stores the refresh token in the OS keyring (`keyring` package).

**Done when:** a download from Claude Code shows up in the team's web ledger.

## P4 — More sources

In priority order (each = adapter + fixture + test + PROVIDERS.md row):
1. **Rijksmuseum native** (data.rijksmuseum.nl, Linked Art JSON-LD; search returns IDs, resolve each).
   Openverse covers it meanwhile.
2. **Wellcome Collection** (`api.wellcomecollection.org/catalogue/v2/works`, keyless, CC-BY/PDM).
3. **Yale LUX** (Linked Art, keyless).
4. **Musopen / IMSLP** for PD recordings and scores (check API terms first).
5. **ambientCG decals/atlases** split out as their own media types if the team wants them.
6. **Kenney** assets (CC0 game art, no API: a curated static index in `providers/static/`).
7. **Sample libraries** from the granular-synth research (VCSL, VSCO 2 CE, Iowa MIS, Karoryfer):
   static manifest provider, since they're GitHub/zip distributions, not APIs.

## P5 — Quality of life

- Saved searches + "watch" (re-run nightly, notify on new GREEN results), with a scheduled job on Railway.
- Bulk download a whole collection into a folder with one ATTRIBUTION.md (`freestash collection pull <id>`).
- Perceptual-hash dedupe across providers (the same Met painting via Met, Openverse, Wikimedia, Europeana).
- `freestash audit <folder>`: walk a project, read `.license.json` sidecars, flag files with no sidecar
  or whose license would now be RED for a given use case.
- Public Domain Day job: every Jan 1, re-score ledger entries whose YELLOW came from the date heuristic.
- Thumbnail proxy endpoint (`/api/thumb`) with caching for hosts that block hotlinking, **only** for
  hosts whose terms allow it; never as a way around a block.

## P6 — Avalonia desktop app

See `desktop/README.md`. C#/.NET 9 + Avalonia 11, talks to the same API (local `freestash serve` or
the hosted one). Killer features over the web UI: drag results straight into a DAW/Figma/Explorer
with the sidecar attached, watch-folders that auto-attach provenance, and offline browsing of
downloaded collections.
