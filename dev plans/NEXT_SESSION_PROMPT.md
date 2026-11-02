# Next session — Freesta.sh

## 1. What and where
Open-media search with per-use clearance. One product, two apps, one account: the website (`freestash/`, live at
https://freesta.sh on Railway) and the Windows desktop app (`freestash-desktop/`). Monorepo `C:\DEV\Freesta.sh`, GitHub
`Vybecode-LTD/Freesta.sh`. Read the root `CLAUDE.md`, then `docs/HANDOFF.md`.

## 2. Rules that override defaults
- **Parity is binding:** every user-facing change lands in both apps in one PR (`shared/parity.json`).
- No Supabase. Never print Railway variables.
- **Needs the owner's OK:** merging, DNS, production accounts, deleting Railway resources, computer-use, admin grants.
- No email address makes an admin: grants go only through `python -m freestash admin grant` (PR #6 review).

## 3. State (verified 2026-11-02, end of session)
- `main` = `origin/main` = **2cfc414** (PR #6 merge), deployed as Railway `ac05d804`, SUCCESS. **No open PRs; next #7.**
- The checkout is `feat/pr7-grouped-results`: local docs commits, not pushed, no upstream. They go in with PR #7.
- Live and verified: the PR #5 cookie session; PR #6 `#/admin` + shared keys. The owner is the only admin.
  Production has 1 account.
- The owner hasn't stored provider keys on `#/admin` yet.

## 4. First job, then the order
1. **PR #7: grouped results + query words** (plan `dev plans/2026-11-01-packs-web-admin-plan.md` §3 ask 4).
   - Write the contract first (`C:\DEV\_templates\feature-CONTRACT.md`).
   - Add `shared/categories.json` (id, label, order, query words), exported by `scripts/export_shared.py`.
   - Both apps group results into sections (8 each, "Show all (n)", a jump bar). Query words become removable chips,
     parsed in the engine.
   - Tests first; rendered-contrast gate on the search page; parity rows.
2. Then packs + brush/shape/sprite (the model contract and policy rows, ground rule 1), then GitHub + curated packs,
   then web or AI search. That's the order in decision 0003.

## 5. Open owner decisions (ask, don't decide)
- AI Search (plan §2b) instead of Brave web search.
- The Unsplash production application; Wikimedia (a normal OAuth consumer, or drop the token).
- Postgres backups; the spare volume `postgres-volume-EFLf`; the `www` CNAME; the Google OAuth client; desktop signing.

## 6. Environment that worked
- **Python:** `cd freestash; .venv/Scripts/python.exe -m pytest` (140) · `ruff check src tests scripts` ·
  `python scripts/export_shared.py --check`.
- **Web and desktop:** `cd freestash/web; npm test` (27) · `npm run build`. Desktop: `dotnet test` from
  `freestash-desktop/tests/Freestash.Client.Tests` (41).
- **Dev server:** `preview_start freestash-accounts` (:8790). Sign up, then `python scripts/dev_accounts.py
  --grant-admin <email>`.
- **Contrast gate:** `node ~/.claude/skills/verify-real-pass/scripts/rendered_contrast.mjs URL --schemes dark`.
  - The app themes on `data-theme`, so snapshot each signed-in page per theme into `web/dist` (served same-origin),
    gate those, then delete them.
  - Force every status tone onto the snapshot, and add a positive control.
- **Traps:**
  - Bash heredocs with quotes break: write patch scripts to the scratchpad.
  - `gh` sometimes hits TLS timeouts: retry.
  - `railway ssh` needs `--project ba994460-f01e-4a4d-9e83-994f352b6634 --environment production --service …`.
  - A branch cut from `origin/main` tracks `main`: push with `git push -u origin <branch>:<branch>`.

## 7. Evidence and IDs
- Decisions `docs/decisions/0001–0003` (next 0004).
- Contracts `dev plans/contracts/{accounts-sync,web-cookie-session,admin-shared-keys}.md`.
- Next PR #7.

## 8. Promotion candidates (owner approves)
- **A bootstrap admin keyed on an email is a takeover when sign-up doesn't verify email.** Grant out of band.
- **A key "Test" must bypass the HTTP cache,** or a revoked key passes.
- **Contrast-gate a signed-in SPA** by snapshotting its rendered DOM into the build output; force the states.
- **Railway CLI unlinked:** pass `--project/--environment/--service` explicitly.
