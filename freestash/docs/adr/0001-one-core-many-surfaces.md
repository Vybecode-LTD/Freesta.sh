# ADR 0001: One Python core, many surfaces

**Status:** accepted · 2026-10-30

**Context.** Freestash needs to work from Claude Code (MCP), the terminal, a team web app, and later a
desktop app. Duplicating provider logic or license rules across surfaces would let verdicts drift.

**Decision.** All search, license, download, and ledger logic lives in the `freestash` Python package.
CLI, MCP, and FastAPI are thin adapters over it. The Avalonia app will call the HTTP API (local
`freestash serve` or the hosted service) and never reimplement the engine.

**Consequences.** One place to fix a provider or a policy rule. The desktop app depends on a running API
(it can spawn `python -m freestash serve` itself in local mode). `models.py` is the cross-language contract.
