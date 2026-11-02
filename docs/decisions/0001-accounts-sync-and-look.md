# 0001 — One account system, synced keys, hosted-first desktop, the Aperture look

Date: 2026-10-31 · Decided by: the owner (answers in session) · Status: accepted

| Question | Chosen | Lost, and why |
|---|---|---|
| Database / auth host | **Railway Postgres + app-level auth in FastAPI** (Seeq'r's 2026-06-02 model: bcrypt passwords, HS256 JWT) | Supabase Auth + RLS: the owner doesn't want Supabase on this project |
| Who can sign up | **Open sign-up** (email + password), rate-limited; password reset by email | Invite-only: nobody could try it without asking for a code |
| Where users' provider keys live | **In the account, Fernet-encrypted at rest** (key only in Railway env), synced to web and desktop | Per-device only: no sync, keys re-entered on every browser and device |
| What the desktop searches through | **The hosted engine at freesta.sh by default**, signed in; the local Python engine stays as an advanced setting | Local engine by default: every user would need Python installed, and results could drift from the web |
| The look of both apps | **B · Aperture** (cold glass strata, warm sodium accent, live source aperture). Board: `dev plans/design-directions.html` | A · Provenance (archival serif, clearance rail) and C · Index (Swiss editorial, light-first) |

Consequences:
- ~~Server env provider keys are **not** shared with users unless `FREESTASH_SHARE_SERVER_KEYS=true`, so one user can't burn the owner's quota.~~
  **Superseded by decision 0003 (2026-11-01):** the admin's keys serve every member, with per-member caps; the flag is retired.
- Web and desktop are one product: same API, same account data, same screens. Anything only one platform can do is listed in `shared/parity.json` with the reason.
- Supabase migrations and supabase-js are removed; the schema is created by SQLAlchemy at startup (Alembic before the first breaking schema change).
