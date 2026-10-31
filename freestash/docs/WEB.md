# Web app

## Local

```bash
python -m freestash serve --reload          # API :8787
cd web && npm install && npm run dev     # UI :5173 (proxies /api)
```

Or build once (`npm run build`) and the API serves `web/dist` at http://127.0.0.1:8787.

## Team mode

`VITE_AUTH_MODE=supabase` + `VITE_SUPABASE_URL` + `VITE_SUPABASE_PUBLISHABLE_KEY` at build time;
`FREESTASH_AUTH_MODE=supabase` + `SUPABASE_URL` (+ `SUPABASE_JWT_SECRET` for legacy projects) on the API.
Users sign in by magic link; the API resolves their team from `team_members`. See IMPLEMENTATION.md P2.

## Views

Search (streaming, media chips, use-case selector, tier filter, source health strip) · asset drawer
(verdict matrix for all uses, attribution copy text/HTML, files, "Record + open file", add to collection)
· Collections · Ledger (project filter, ATTRIBUTION.md / HTML / CSV export) · License check · Sources.

## Design tokens

`web/src/styles.css` `:root`: `#0a0a0a` canvas, Ember `#e8440a`, Geist Sans + JetBrains Mono (self-hosted
via Fontsource, fittingly), OKLCH surfaces and tier colors. To reskin with Machined Light, replace the
`:root` block with the Machined Light tokens and adjust `.card`, `.panel`, `.input` to its raised/inset
surfaces. Class names are stable.

## Notes

- Some hosts block hotlinked previews (AIC's IIIF host from some networks, SMK occasionally). Cards
  show "preview blocked" instead of a broken image. The source page link always works.
- SSE is parsed over `fetch` because `EventSource` can't send the Authorization header.
