# dev plans — Freesta.sh

| File | What it is | Published |
|---|---|---|
| `design-directions.html` | The three-direction board (A Provenance, B Aperture, C Index) the owner picked from: **B · Aperture** | local only |
| `assets/` | Public-domain images the board uses (Cleveland, SMK, Met, V&A, LoC) | — |
| `renders/direction-01…06.png` | The board's frames: 01/02 = A (screen, key row), 03/04 = B, 05/06 = C | — |
| `renders/web/` | Rendered web screens after the build (dark, Frost, phone) + `desktop-account-on-web.png` (sync proof) | — |
| `contracts/accounts-sync.md` | The approved contract for accounts, synced keys and prefs | — |
| `2026-11-01-packs-web-admin-plan.md` | Proposal for the owner's five asks: bulk packs, web search, admin-held keys, grouped results, brushes and game assets. Accepted 2026-11-01 (decision 0003) | local only |
| `contracts/web-cookie-session.md` | Contract for PR #5: the website signs in with an HttpOnly cookie, plus the CSRF Origin check (done) | — |
| `contracts/admin-shared-keys.md` | Contract for PR #6: the admin screen, the site's shared keys, caps, usage meter, users and audit log (done) | — |
| `contracts/grouped-results.md` | Contract for PR #7: `shared/categories.json`, query words read in the engine (`GET /api/search/parse`, chips), results grouped by category in both apps (done) | — |
| `NEXT_SESSION_PROMPT.md` | The starting prompt for the next session | — |

Desktop screenshots live with the app: `../freestash-desktop/docs/screenshots/`.
