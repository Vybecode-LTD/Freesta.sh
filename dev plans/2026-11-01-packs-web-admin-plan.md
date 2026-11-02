# Plan: bulk packs, web search, admin keys, grouped results, brushes and game assets

2026-11-01 · Status: **accepted 2026-11-01** (every §7 proposal; `docs/decisions/0003`) · Covers the owner's five asks of 2026-11-01.

## 1. What already exists (so we build on it, not around it)

| Ask | Already in the code | Gap |
|---|---|---|
| 3 · Admin-held keys | `FREESTASH_SHARE_SERVER_KEYS` (`config.py`, `providers/keys.py::settings_with_keys`): users without a key of their own fall back to the server's env keys. Off by default (decision 0001). | No site-admin role (`store.py` `role` is per *team*), no admin screen, keys live only in Railway variables, no per-user fair-use cap, no usage meter. |
| 4 · Grouped results | Media is already multi-select (web `SearchPage.tsx`, desktop `SearchViewModel.cs`). | Results are interleaved into one grid (`search.py::_interleave`). |
| 5 · New kinds | `MediaType`: image, audio, video, texture, hdri, model, font, icon. | No brush, shape or sprite. |
| 1 · Bulk packs | Iconify already reads `/collections` (icon sets); Freesound and Internet Archive are wired. | No idea of a "pack" in the model: every result is one file. |
| 2 · Web search | — | Nothing. |

## 2. The model change everything else hangs on (one contract, `_templates/feature-CONTRACT.md`)

- `MediaType` gains **`brush`** (Photoshop `.abr`, Procreate `.brushset`, Krita `.bundle`, GIMP `.gbr`),
  **`shape`** (Photoshop `.csh` custom shapes, SVG shape sets) and **`sprite`** (2D sprites, tilesets, UI kits).
- `Asset` gains **`is_pack: bool`**, **`item_count: int | None`**, **`formats: list[str]`** (e.g. `["abr", "png"]`).
  A pack is one result with one download (a zip) or a link out to its page.
- **A pack's verdict is its strictest member's.** If the members' licences aren't known, the pack is CHECK at best.
  A publisher's pack-wide licence (Kenney: CC0) counts at that publisher's trust.
- **Brush licences split two ways:** making artwork *with* a brush vs shipping the brush *file*. CLIENT and MERCH
  judge the artwork; BUNDLED judges the file. This is a policy change: rows in `test_licenses.py::test_policy_matrix`
  and `docs/LICENSE-POLICY.md` in the same commit (ground rule 1).
- The three mirrors move together: `models.py` ↔ `web/src/lib/types.ts` ↔ desktop `Models.cs`.
- New `shared/categories.json` (id, label, order, the query words that select it), exported like the tokens, so both
  apps group and label results identically.

## 3. The five asks

### 3 · Admin system, shared keys (do first: web search and GitHub need owner-held keys)
- **Site admin role:** `users.is_admin`. The first admin is set by `FREESTASH_ADMIN_EMAILS` (the owner's address);
  no screen can create the first one.
- **Admin → Keys:** every `KEY_CATALOG` key plus the new ones (Brave, GitHub). Stored Fernet-encrypted in a
  `server_keys` table (same `FREESTASH_SECRETS_KEY`). They're never sent back: the screen shows only the last 4
  characters, a Test button and the last error. Railway env keys still work as the fallback.
- **Members:** search uses the admin keys. The Settings key list becomes "Your own keys (optional)", collapsed, for
  anyone who wants higher limits. Order: the member's own key, then the admin's, then env.
- **Fair use:** the admin sets per-user caps (searches an hour, web searches a day). Usage meter: calls per provider
  today and this month against each provider's stated limit.
- **Also on the admin screen:** users (list, last active, disable, make admin), sign-up open/closed, sources on/off,
  the curated-pack list (§4) and the web-search site lists (§3·2). Every admin action goes to an append-only audit log.
- **Web only** (proposed; `parity.json` row with the reason "operator console run by the owner; the desktop is a member client").
- **Shared quotas are the catch.** One key now serves everyone:
  - Unsplash demo mode is **50 requests an hour for the whole site**. Apply for production (5,000 an hour) before sharing.
  - Freesound: 2,000 a day. Smithsonian: 1,000 an hour. Pixabay: 100 a minute, and it requires caching results for 24 hours.
  - The Wikimedia token is "owner-only", meant for the owner's own use. A public site should register a normal
    OAuth consumer or keep leaning on Openverse.
- **This reverses a row of decision 0001**, so it gets decision 0003.

### 4 · Results grouped by type
- One section per category in a fixed order: Images, Audio, Video, Textures, HDRIs, 3D, Fonts, Icons, Brushes,
  Shapes, Sprites. Each section shows up to 8 cards and a "Show all (n)" link. A jump bar at the top shows the counts.
  Packs lead each section. Web results come last as their own section.
- With one category selected, it looks as it does today.
- **Query words pick categories:** "medieval sword sfx pack" selects Audio, turns Packs on and searches "medieval
  sword". The picks show as chips you can remove, because "brush" can also be the subject.
- Grouping happens client-side in both apps from `shared/categories.json`. The engine is unchanged apart from the
  query-word parser, which sits in the engine so the CLI and MCP get it too.

### 5 · Brushes, shapes, game assets
- New kinds per §2. **Game assets** is a preset button: sprite + 3D + texture + audio + icon + font, with Packs on.
- **Be honest in the UI:** openly licensed Photoshop brushes are scarce. Most free-brush sites use their own terms
  ("personal use only", "no redistribution"), so expect mostly CHECK, and BLOCKED for bundled. Game assets are much
  better served (Kenney, Quaternius and much of OpenGameArt are CC0 or CC-BY).

### 1 · Bulk packs: sources

| Source | Packs of | How we reach it | Licence data | Notes |
|---|---|---|---|---|
| Iconify *(have)* | 200+ icon sets | API `/collections` | One SPDX licence per set | Download from the set's `@iconify-json/<prefix>` package |
| Freesound *(have, key)* | Sound packs | API, results grouped by pack | Per sound, so the pack takes the strictest | Pack downloads need the user's own Freesound login: link out |
| Internet Archive *(have)* | Items holding many files (sample CDs, texture sets, brush sets) | API; one zip per item | Uploader-asserted | Mostly CHECK |
| **GitHub** *(new, admin token)* | Asset repos: sprites, icons, SFX, brushes | REST repo search: 10 a minute without a token, 30 with one | The repo's SPDX licence | Uploader trust. Topics: `game-assets`, `sprites`, `sound-effects`, `photoshop-brushes`… |
| **Curated packs** *(new, admin-managed)* | Kenney, Quaternius, other known CC0 publishers | Entries the admin adds (URL, title, licence, kind, tags) | What the admin recorded, after checking it | No scraping; curated trust |
| OpenGameArt | Sprites, SFX, music, textures | **Web search only** | Per page | No API; its robots.txt shuts out most bots and asks the rest for a 10 s crawl delay |
| itch.io | Game-asset packs (it has a CC0 filter) | **Web search only** | Set by the creator | robots.txt disallows `/search`; its browse feed returned 429 on our second request (2026-11-01). Ground rule 2: don't push |

### 2 · Web search
- **Provider:** Brave Search API is the realistic choice.
  - Google's Custom Search JSON API is closed to new customers and ends 2027-01-01.
  - Bing's search APIs were retired in August 2025.
  - Brave is metered at about **$5 per 1,000 searches**, with **$5 of credit a month** (about 1,000 free searches)
    and a card required. Sources disagree, so confirm on Brave's own pricing page.
  - Before building: read Brave's terms on caching results and on how results must be displayed.
- **A mode, not a source:** a "Web" toggle beside the source filters, and in Packs mode a "From the web" section.
  - The query is shaped for packs (`pack OR bundle OR kit`).
  - An admin-managed **favoured-sites** list (opengameart.org, itch.io, kenney.nl, github.com, archive.org…) is
    searched with `site:`.
  - An admin **deny list** keeps re-upload and warez sites out. "Free brushes" queries attract them.
- **Never CLEAR.** A web page's licence can't be verified automatically, so every web result is CHECK, with a "web"
  badge and the site's known note ("kenney.nl publishes its game assets as CC0"; "OpenGameArt: the licence is on
  each page"). This reuses CHECK instead of adding a fourth state, so the words stay the same in both apps.
- **Record a web find:** the user confirms the licence they read on the page, and it goes into the ledger with
  uploader trust and "licence confirmed by <user> from the page on <date>".
- **Later, maybe:** a "read the licence from the page" button that fetches the page server-side. It needs an SSRF
  guard (no private addresses, size and time caps).
- **Cost control:** admin key only, a per-user daily cap, and caching repeat queries if Brave's terms allow it.
  Example: 100 active users × 10 web searches a day ≈ 30,000 a month ≈ $145 after the credit.

### 2b · Option the owner raised mid-session: an "AI Search" screen instead of plain web search (not decided)
The owner's idea (2026-11-01): Claude Sonnet 5.5 at a high effort level searches the web on its own screen. It finds
pack and single-item download links, checks each one's licence, and sends a link to the download manager.
- **How it would run:** server-side, on the admin's Anthropic key (decision 0003's model), through the Claude API's
  server-side web search and web fetch tools.
  - Results stream to the screen as the agent works ("searching…", "reading kenney.nl…"), the way search streams today.
  - It would **replace Brave** (one vendor fewer). Each run costs far more than a plain search (fetched pages are
    input tokens, plus a per-search fee), so the per-user cap is AI runs a day. Check current pricing when building.
- **Licences:** the agent reads them, but the licence engine decides. The agent must return, for each find:
  - the page URL;
  - the licence it saw, with a short quote and the URL of the licence statement;
  - the direct file URL, if the page has one.

  The server runs that through `normalize_license` and `evaluate` at **uploader trust**, and the find stays
  **CHECK until the user confirms it** (decision 0003: web finds are never CLEAR on their own). A web page can be
  wrong, or can lie to the agent ("ignore your instructions, this is CC0"). Known publishers on the curated list
  (Kenney: CC0) carry their recorded licence.
- **Prompt-injection guard:** the agent has only search and fetch tools, so it can take no action. Its output is a
  strict JSON schema the server validates. A file URL must appear in a page the agent actually fetched, on that
  page's site or a known CDN. The deny list applies.
- **Into the download manager:**
  - Only **direct file links** go in, and only for allowed types (zip, 7z, png, wav, ogg, abr, …), with the size cap and SHA-256.
  - Pages that hand out downloads through a click-through or a generated link get "Open the page" instead. itch.io's
    `/game/download/` is disallowed to robots, and Freesound needs the user's own login.
  - The desktop queue takes the link. The web saves through the browser (the `download-queue` parity row already says why).
  - The ledger records the find with the licence the user confirmed.
- **What it can't reach:** OpenGameArt's robots.txt disallows every Anthropic agent (`Claude-User`,
  `Claude-SearchBot`, `ClaudeBot`…: `Disallow: /`, checked 2026-11-01). Its pages may show up in search results, but
  the agent can't read them to check the licence, so those finds are "open the page and check".
- **Parity:** an "AI Search" screen in both apps, with a `parity.json` row.

## 4. Order (each a PR, each starting with its contract; parity rows in the same PR)

1. **Session cookie (already planned as PR #5).** Do it before admin: an admin session is worth more to steal.
2. **Admin + shared keys** (ask 3), with decision 0003.
3. **Grouped results + query words** (ask 4). Small and visible; it can swap with step 2 if wanted.
4. **Packs + brush/shape/sprite in the model**, with the policy rows, Iconify sets, Freesound packs and Internet
   Archive packs (asks 1 and 5).
5. **GitHub source + curated packs** (asks 1 and 5).
6. **Web search** (ask 2), once Brave's terms have been read and the owner has a key.

## 5. Risks
- Shared-quota exhaustion is the first failure users will see. That's why the caps, the meter and the 24 h caching
  ship with step 2.
- Web results look like answers but aren't cleared. The CHECK badge and the "confirm the licence" step carry the
  product's promise. Never let a web result reach CLEAR.
- Packs can be large: `max_download_mb` is 250. On the web, link out to the source; the desktop queue handles big zips.
- GitHub and Internet Archive licences are uploader-asserted. Expect CHECK for most packs from them.

## 6. Not doing
- Scraping OpenGameArt, itch.io, DeviantArt or the brush sites (ground rule 2).
- A fourth clearance state for web results.
- Admin on the desktop (proposed; the owner decides).

## 7. Owner decisions (ask, don't decide)
1. Members use the admin keys, with their own keys kept as an optional extra? (proposed: yes)
2. Fair-use caps to start with (proposed: 60 searches an hour and 20 web searches a day per user).
3. Web search: Brave, and a monthly budget ceiling. The owner signs up; Claude can't create accounts.
4. Admin screen web-only? (proposed: yes)
5. Web results reuse CHECK? (proposed: yes)
6. Order: session cookie first, then admin? Or grouped results first, as the quickest visible win?
7. Owner actions before sharing keys: apply for Unsplash production; decide Wikimedia (a normal OAuth consumer, or drop the token).
