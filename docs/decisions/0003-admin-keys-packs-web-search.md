# 0003 — Admin-held keys, grouped results, packs, new kinds, web search

Date: 2026-11-01 · Decided by: the owner ("Yes, as proposed" to the plan's §7) · Status: accepted
Plan: `dev plans/2026-11-01-packs-web-admin-plan.md`

| Question | Chosen | Lost, and why |
|---|---|---|
| Whose provider keys search uses | **The admin's keys, for everyone.** A member's own key is an optional extra that raises their limits. Order: the member's key, then the admin's, then env. **Supersedes decision 0001's key row** | Each member brings their own keys (0001): nobody can search well until they've signed up at several providers |
| Fair use of the shared keys | **Per-user caps the admin can change: 60 searches an hour, 20 web searches a day to start**, plus a usage meter per provider | No caps: one member can burn the whole site's quota (Unsplash demo mode is 50 requests an hour for everyone) |
| Web search | **Brave Search API with the admin's key.** The owner signs up and sets the monthly budget | Google Custom Search: closed to new customers, ends 2027-01-01. Bing: retired August 2025 |
| Where the admin screen lives | **Web only** (`parity.json` row with the reason) | Both apps: the desktop is a member client; one owner runs the site from the website |
| How web results are cleared | **Always CHECK**, with a "web" badge and the site's known note. Never CLEAR | A fourth state: new words in both apps and the policy engine for no gain |
| Order of work | **1 session cookie (PR #5) · 2 admin + shared keys · 3 grouped results · 4 packs and brush/shape/sprite · 5 GitHub + curated packs · 6 web search** | Grouped results first: quicker to see, but the admin console makes a stolen session worth more, so the cookie goes first |

Consequences:
- Before keys are shared, the owner applies for Unsplash production (5,000 requests an hour) and decides Wikimedia: a
  normal OAuth consumer, or drop the owner-only token.
- Pixabay requires caching results for 24 hours; the shared-key PR ships that with the caps.
- Brave's terms on caching and display are read before the web-search PR is built.
- OpenGameArt and itch.io are reached through web search only (ground rule 2: no scraping).
