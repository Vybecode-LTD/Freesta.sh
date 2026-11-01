# Handoff — Freesta.sh (2026-11-01, second session)

## State
- `main` = the merge of **PR #3** (bfdae9b). PRs #1–#3 are merged (#2 and #3 on the owner's OK), and **all are
  live**. PR #4 (the no-database guard) is open; the next is #5. Railway builds `main`.
- Verified on production after the deploys:
  - https://freesta.sh: the certificate is valid and health reports `auth_mode: accounts`.
  - Traversal and `%00` paths get the page on both hosts.
  - The CSP header is served, and in a browser the page shows no violations while an injected script is blocked.
- Every review thread on PR #1 is resolved.
- **Database incident (2026-11-01):** the Postgres service was deleted between 23:02 and 23:17 (not by an agent).
  `DATABASE_URL` resolved to an empty string, and the app quietly ran on a SQLite file inside the container that
  every deploy wiped. The owner's 22:59 account and ledger entry were lost. The orphaned `postgres-volume` was empty
  apart from `lost+found` (created 20:13), so nothing could be recovered.
  - Fixed: a new `Postgres` service on that volume, and `DATABASE_URL=${{Postgres.DATABASE_URL}}` on `freestash`.
    Verified: 9 tables created at 23:58, 0 users.
  - **PR #4** makes accounts mode refuse to start without a database URL.
- **Railway is on Pro** (the owner, 2026-11-01), so outbound SMTP is allowed. Reset email still waits on the
  mailbox and its variables (Next 1).
- **Desktop builds:**
  - CI publishes a self-contained single-file exe on every push to `main` (artifact `freestash-desktop-win-x64`).
  - There's a local Release build of `main` at `freestash-desktop/publish/Freestash.exe` (unsigned, ignored by git).
  - There's no installer, no signing and no GitHub Release yet.
- This checkout is on `feat/pr4-followups`, which is PR #4: the no-database guard plus these docs.

## Done this session
- Owner decisions (`docs/decisions/0002`): Spacemail SMTP instead of Resend; a CSP now, then an HttpOnly cookie;
  no Cloudflare. Google sign-in and `www.freesta.sh` are on the list.
- **PR #2:** found and fixed a path traversal that read the server's files, then two review fixes (the threadpool,
  and NUL paths on Linux).
- **PR #3:**
  - ledger paging on both apps (a keyset cursor, Load more);
  - a strict CSP (`api/csp.py`);
  - the SMTP mailer (`mailer.py`, `mail.spacemail.com:465`).
- PR #4 (open): accounts mode refuses to start without a database URL (regression test).
- Gates: pytest 122 · ruff · export check · vitest 15 · web build · dotnet 33 · 0 warnings.

## Next
0. Owner: merge PR #4 (the no-database guard). Sign up again on https://freesta.sh: earlier accounts are gone.
   Turn on scheduled backups for the Postgres volume (Railway → Postgres → Backups).
   The spare empty volume `postgres-volume-EFLf` can be deleted.
1. The SMTP variables are set (the owner, 2026-11-01). Once the owner has re-registered, request a reset and
   confirm the email arrives (check spam, SPF and DKIM). Set `FREESTASH_EMAIL_FROM` if the mailbox isn't `hello@`.
2. Owner: sign up on https://freesta.sh, run `freestash-desktop/publish/Freestash.exe` (default server
   freesta.sh), and sign in.
3. PR #5: the HttpOnly cookie for the web (decision 0002; the desktop keeps bearer, and CSRF protection is needed).
4. `www.freesta.sh`: the owner adds the CNAME; then a Railway domain and a redirect to the root. Then Google sign-in
   on both apps (Seeq'r's PKCE).
5. Live on-screen check of the desktop app (computer-use; ask first). An installer, signing and releases
   (`SOFTWARE_RELEASE.md`). Retire `railway.json` before 2026-12-01.

## Warnings
- Back up `FREESTASH_SECRETS_KEY` (Railway → Variables) in a password manager.
- The desktop "Load more" hasn't been seen on screen yet. The rendered-contrast gate wasn't re-run for it (it reuses `.btn`).
- The rate limiter is in-process: one replica only. Pexels has paused new API keys.
- The local dev database (`%LOCALAPPDATA%\Freestash\dev`) holds a throwaway test account with 140 ledger entries.
