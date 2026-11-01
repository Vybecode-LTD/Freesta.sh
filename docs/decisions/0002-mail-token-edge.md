# 0002 — Reset email over Spacemail SMTP, CSP then a cookie, Railway's edge only

Date: 2026-11-01 · Decided by: the owner (answers in session) · Status: accepted

| Question | Chosen | Lost, and why |
|---|---|---|
| Who sends password-reset email | **Our own SMTP sender, through a Spacemail mailbox** (`mail.spacemail.com:465`, implicit TLS, the full address as the login) | Resend: the owner would rather not add another vendor |
| Where the web keeps its sign-in token | **A strict CSP now (PR #2), then an HttpOnly cookie in its own PR.** The desktop keeps its bearer token | localStorage with no CSP: one XSS could read the token. Cookie only: a bigger change, and it leaves script injection open |
| Cloudflare in front of freesta.sh | **No: Railway's edge only.** `FREESTASH_TRUST_CF_CONNECTING_IP` stays false | Cloudflare proxy: the client-IP trust changes, and Railway's certificates get harder, for caching nobody needs yet |
| Extras | **Google sign-in on both apps; `www.freesta.sh` redirects to the root** | A contact email in the User-Agent: not set for now |

Consequences:
- **Railway allows outbound SMTP only on the Pro plan and above** (the owner is on Pro, confirmed 2026-11-01) (docs.railway.com → Outbound Networking → Email
  delivery). On Free, Trial or Hobby the sender can't connect, and reset email still doesn't work.
- The owner creates the mailbox (e.g. `hello@freesta.sh`) and its DNS records (MX, SPF, DKIM) at Spaceship. Then
  the owner sets `FREESTASH_SMTP_USERNAME` and pipes `FREESTASH_SMTP_PASSWORD` in through `railway variable set --stdin`.
- The CSP allows scripts only from the site itself plus the hash of the inline prefs script. Images may come from any
  `https:` host (results come from about 20 providers). `connect-src` is `'self'`.
- The cookie PR must keep the bearer header working for the desktop and add CSRF protection to the web.
