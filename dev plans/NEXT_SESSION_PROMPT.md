# Next session — Freesta.sh

## 1. What and where
Open-media search with per-use clearance. One product, two apps, one account: the website (`freestash/`, live at
https://freesta.sh on Railway) and the Windows desktop app (`freestash-desktop/`). Monorepo `C:\DEV\Freesta.sh`, GitHub
`Vybecode-LTD/Freesta.sh`. Read the root `CLAUDE.md`, then `docs/HANDOFF.md`.

## 2. Rules that override defaults
- **Parity is binding:** every user-facing change lands in both apps in one PR (`shared/parity.json`).
- No Supabase. Never print Railway variables.
- **Needs the owner's OK:** committing/pushing/merging, DNS, production accounts, deleting Railway resources, computer-use,
  admin grants. No email address makes an admin: grants go only through `python -m freestash admin grant`.

## 3. State (verified 2026-11-02, end of session)
- `main` = `origin/main` = **f1737d6** (PR #7), live. No open PRs; highest PR number 7, no issues.
- The checkout is `feat/pr8-packs` at 12af9d0 (no upstream). **PR #8's whole build is in the working tree, uncommitted** (engine,
  web, desktop, tests, fixtures, docs, the contract `dev plans/contracts/packs-and-new-kinds.md`, screenshots 09e/09f).
  All gates were green on it: pytest 203, ruff, export check, vitest 47, web build, dotnet 0 warnings / 61 tests, contrast 0 failing.
- Nothing deployed from it. The owner hasn't yet said to commit or push.

## 4. First job, then the order
1. **Re-run the gates on the working tree, then ask the owner** to commit and push PR #8 (one push, branch + docs + status rows,
   `git push -u origin feat/pr8-packs:feat/pr8-packs`; PR number 8). `git add` by path: check the staged diff for secrets.
2. Then **PR #9: GitHub source and curated packs** (plan `dev plans/2026-11-01-packs-web-admin-plan.md` §3·1). Contract first.
   Needs a GitHub token on `#/admin` (ask the owner) and the curated-pack list (Kenney, Quaternius: admin-recorded licences).
3. Then web or AI search (decision 0003's order).

## 5. Open owner decisions (ask, don't decide)
- AI Search (plan §2b) instead of Brave web search.
- The Unsplash production application; Wikimedia (a normal OAuth consumer, or drop the token).
- The infrastructure items in `docs/HANDOFF.md` → Next 4.

## 6. Environment that worked
- **Python:** `cd freestash; .venv/Scripts/python.exe -m pytest` (203, ~75 s) · `ruff check src tests scripts` ·
  `python scripts/export_shared.py --check`.
- **Web and desktop:** `cd freestash/web; npm test` (47) · `npm run build`. `cd freestash-desktop; dotnet build
  Freestash.Desktop.sln; dotnet test --project tests/Freestash.Client.Tests` (61).
- **Servers:** `preview_start freestash-accounts` (:8790) · `freestash-local` (:8791, for `dotnet run --project
  tools/Freestash.Desktop.Snapshots -- http://127.0.0.1:8791 docs/screenshots`; restore the shots a change doesn't touch with
  `git checkout`). Run the snapshot twice if the first Iconify pack search times out cold.
- **Contrast gate on a signed-in page:** register a throwaway `*@example.test` with `X-Freestash-Session: cookie`, set
  `localStorage["freestash.session"]`, write script-free snapshots per `data-theme` into `web/dist`, run
  `rendered_contrast.mjs --schemes dark` on each (positive control first), then delete them. A page with an open drawer: strip
  `.scrim` and the results first, or axe reads everything under it as undecided.
- **Traps:**
  - Bash heredocs with quotes and `\n` break: patch with the Edit tool or a script file.
  - `gh` sometimes hits TLS timeouts: retry.
  - A heredoc python through a relative `../` path can miss: use the full path to `.venv/Scripts/python.exe`.

## 7. Evidence and IDs
- Decisions `docs/decisions/0001–0003` (next 0004). Contracts `dev plans/contracts/{accounts-sync,web-cookie-session,
  admin-shared-keys,grouped-results,packs-and-new-kinds}.md`. Next PR #9.
- Recorded fixtures: `iconify_collections.json`, `ia_packs.json`; **synthetic** (no key yet): `freesound_packs_synthetic.json`.

## 8. Promotion candidates (owner approves)
- **A WaitFor that only watches an "is busy" flag passes before the work starts:** wait on the result you assert (the snapshot
  tool's packs step failed twice on it; its `WaitFor` also only logs a timeout, so check for "timed out" in the log).
- **An open drawer or modal makes the page under it "undecided" in the contrast gate:** snapshot the drawer without the page.
- **A pack licensed file by file is judged by its strictest member, and by read-fraction:** fewer files read than it holds caps
  it at Check (`licenses/policy.py::_pack_rules`).
- Earlier candidates: a parse-then-search UI keys its re-run on the last *started* search; contrast-gating a signed-in SPA.
