# Providers

"Live" = adapter built against real responses recorded 2026-10-30 (fixtures in `tests/fixtures/`).
"Docs" = needs a key, built from the documented shape; fixture is marked `_synthetic` until P1.

| id | Source | Media | Key | Verified | Default trust | Notes |
|---|---|---|---|---|---|---|
| met | The Met | image | – | live | institution | v1 search retired 2026-10-01 → v1.1. N+1 object lookups. PD per object. |
| artic | Art Institute of Chicago | image | – | live | institution | Send `AIC-User-Agent`. IIIF 843px recommended. IIIF host 403s datacenter downloads. |
| cleveland | Cleveland Museum of Art | image | – | live | institution | `cc0=1` filter. `full` rendition is a huge TIFF. |
| smithsonian | Smithsonian Open Access | image | api.data.gov | docs | institution | `usage.access == "CC0"` per media item. Openverse covers ~25 SI units without a key. |
| smk | SMK (Denmark) | image | – | live | institution | `filters=[public_domain:true]`. PDM rights URIs. |
| vam | Victoria & Albert | image | – | live | institution | Non-commercial image terms → reference only. Skipped for commercial searches. |
| nasa | NASA Image & Video Library | image, audio, video | – | live | government | Audio/video files via `/asset/{nasa_id}`. Third-party credit lines → trust unknown. |
| loc | Library of Congress | image, audio, video | – | live | institution | Rights via per-item `rights_advisory` (N+1, max 10). "No known restrictions" → NKC. |
| europeana | Europeana | image, audio, video, 3D | optional | live | institution | Shared `api2demo` key works for testing. `reusability=open`. |
| wikimedia | Wikimedia Commons | image, audio, video | optional (OAuth2) | docs | community | 2026 global rate limits; anonymous cloud traffic gets 429. |
| openverse | Openverse | image, audio | optional | live | per source | 52 image sources + Freesound/Jamendo/Commons audio. Slow at times. Excludes sources covered natively. |
| internet_archive | Internet Archive | video, audio, image, brush, shape, sprite | – | live | uploader | Uploader-asserted licenses. Prelinger/FedFlix collections → curated. An item holding a ZIP, RAR or 7z is a **pack** (IA's own "VBR ZIP" bundles aren't); Packs adds a `format:` query for them. Brushes, shapes and sprites: one title/subject keyword query each, image and data items only, so expect misses. |
| polyhaven | Poly Haven | texture, HDRI, 3D | – | live | curated | All CC0. Catalog cached 24h, ranked locally. `/files/{id}` for maps. |
| ambientcg | ambientCG | texture, HDRI, 3D | – | live | curated | All CC0. Zip downloads per resolution. |
| fontsource | Fontsource | font | – | live | curated/community | OFL mostly. Woff2 via jsDelivr. Catalog cached 24h. |
| iconify | Iconify | icon | – | live | community | ~255 sets, license per set (MIT/Apache/CC-BY mostly; some GPL/NC get flagged). With Packs, whole **sets** from `/collections` (cached 24h, hidden sets skipped) lead; a set downloads as `@iconify-json/<prefix>/icons.json` via jsDelivr. |
| freesound | Freesound | audio | yes | docs | uploader | Previews only without OAuth2; originals need user login. With Packs: `group_by_pack=1`, then `/packs/<id>/` for up to 6 packs (cached 24h). A pack's verdict comes from its sounds' licenses: one read in search, up to 150 in the detail. Pack downloads need the user's own login. |
| unsplash | Unsplash | image | yes | docs | community | Must hotlink URLs + ping `download_location` (done in `on_download`). 50 req/h in demo mode. |
| pexels | Pexels | image, video | yes | docs | community | Credit Pexels + photographer. |
| pixabay | Pixabay | image, video | yes | docs | community | No hotlinking; cache results 24h. |
| github | GitHub | sprite, 3D, texture, audio, icon | optional (fine-grained token) | live | uploader | **Packs only** (`packs_only`): repo search `<words> topic:game-assets`, one pack per repo under the licence GitHub reads from its license file (`NOASSERTION` and no file → rights unknown). 30 searches a minute with a token, 10 without; in-process budget 25/8 and a 60 s wait after a 403/429, with no retry of the 429. Qualifiers can't be OR'd (0 results), and `sprites`/`sound-effects`/brush topics mostly tag tools, so only `game-assets`. Kind from topics, name, description (else sprite). Detail reads the git tree: asset files by extension and their formats. Thumbnail is the owner's avatar: the social images 429 per IP. Download = the default branch's zip. |
| curated | Curated packs | every kind | – | live | curated | Entries the site's admin records on `#/admin` (Kenney, Quaternius: the licence read on the publisher's page, and when). Nothing fetched; the API passes the list in `Settings.curated_packs`, so the CLI and MCP have none. Off until the first entry. Shown whenever it matches, Packs or not (no quota). |

## Adding a provider

1. `src/freestash/providers/<group>.py`: a pure `parse_*` function + a `Provider` subclass with `info`,
   `search()`, and `get()` if search results are incomplete.
2. Record a trimmed real response into `tests/fixtures/<id>_search.json`.
3. Parser test in `tests/test_providers.py`.
4. Add the class to `PROVIDERS` in `providers/__init__.py`.
5. Add a row here. If it duplicates an Openverse source, add it to `NATIVE_DUPES` in `openverse.py`.
6. Set the right default trust. When in doubt: uploader.
