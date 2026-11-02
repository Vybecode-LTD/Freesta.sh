# Web app

## Local

```bash
python -m freestash serve --reload          # API :8787
cd web && npm install && npm run dev     # UI :5173 (proxies /api)
```

Or build once (`npm run build`) and the API serves `web/dist` at http://127.0.0.1:8787.

## Accounts mode (the hosted app)

`FREESTASH_AUTH_MODE=accounts` on the API (`scripts/dev_accounts.py` runs it locally on a throwaway database). The
website signs in with an **HttpOnly cookie**: its auth calls send `X-Freestash-Session: cookie`, the server sets
`freestash_session` (`SameSite=Lax`, `Path=/api`, `Secure` except on loopback) and the body carries no token.
`lib/session.ts` keeps only the signed-in user in localStorage. Cookie-signed writes need the site's own `Origin`.
The desktop keeps `Authorization: Bearer`. Contract: `../../dev plans/contracts/web-cookie-session.md`.

**Site administration** (`#/admin`, web only; contract `../../dev plans/contracts/admin-shared-keys.md`): an admin
sees "Site administration" in Settings → Account. The first admin is granted on the server, never by an email address
(sign-up doesn't prove an address is yours): `railway ssh -s freestash -- python -m freestash admin grant <email>`
(`revoke`, `list`); more admins are made on the screen. It holds the
site's provider keys (every member searches on them unless they add their own), the per-member hourly search cap,
sign-up open or closed, sources on or off, the shared-quota meter, users (make admin, disable) and the audit log.
It isn't in the nav, so the web and desktop navs stay the same. On the dev server, sign up and then run
`python scripts/dev_accounts.py --grant-admin <email>`.

## Views

Search (streaming, media chips, use-case selector, tier filter, source health strip; query words such as "sfx" pick
the media and show as "Read as" chips; several media group into sections with a jump bar) · asset drawer
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
- SSE is parsed over `fetch` (with the session cookie), so an aborted search cancels its stream.
