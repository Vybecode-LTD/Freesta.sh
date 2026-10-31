# ADR 0002: Verdicts are per use case, not per asset

**Status:** accepted · 2026-10-30

**Context.** "Free to use" is meaningless without the use. Unsplash photos are fine on a demo site and
forbidden as files inside a template download; CC BY-SA is fine on a page but complicates a client
handover; a factory library redistributes raw files, which is the strictest case of all.

**Decision.** Five use cases (reference, demo, client, bundled, merch). Every verdict is
`evaluate(asset, use_case)` → GREEN / YELLOW / RED, plus reasons and obligations. Search filters by
`max_tier` for the chosen use case.

**Consequences.** Users must pick a use up front (default: demo). The same asset can appear in one
search and be hidden in another. Collections carry a use case so their items are scored consistently.
