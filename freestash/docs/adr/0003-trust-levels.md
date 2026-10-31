# ADR 0003: Trust is a separate axis from license

**Status:** accepted · 2026-10-30

**Context.** A live probe found Internet Archive items marked Public Domain Mark that are plainly recent
copyrighted TV. The license string was identical to the Met's genuine CC0 determinations.

**Decision.** Every asset carries a `trust` level (institution, government, curated, community,
uploader, unknown) set by the adapter. Uploader/unknown trust caps shipped uses (client, bundled,
merch) at YELLOW. PD *claims* get a date check against the US public-domain cutoff.

**Consequences.** Some legitimately free uploads show YELLOW for shipped uses: that's intended friction.
Aggregators (Openverse, Europeana) map trust per original source.
