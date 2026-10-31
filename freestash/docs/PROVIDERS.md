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
| internet_archive | Internet Archive | video, audio, image | – | live | uploader | Uploader-asserted licenses. Prelinger/FedFlix collections → curated. |
| polyhaven | Poly Haven | texture, HDRI, 3D | – | live | curated | All CC0. Catalog cached 24h, ranked locally. `/files/{id}` for maps. |
| ambientcg | ambientCG | texture, HDRI, 3D | – | live | curated | All CC0. Zip downloads per resolution. |
| fontsource | Fontsource | font | – | live | curated/community | OFL mostly. Woff2 via jsDelivr. Catalog cached 24h. |
| iconify | Iconify | icon | – | live | community | ~255 sets, license per set (MIT/Apache/CC-BY mostly; some GPL/NC get flagged). |
| freesound | Freesound | audio | yes | docs | uploader | Previews only without OAuth2; originals need user login. |
| unsplash | Unsplash | image | yes | docs | community | Must hotlink URLs + ping `download_location` (done in `on_download`). 50 req/h in demo mode. |
| pexels | Pexels | image, video | yes | docs | community | Credit Pexels + photographer. |
| pixabay | Pixabay | image, video | yes | docs | community | No hotlinking; cache results 24h. |

## Adding a provider

1. `src/freestash/providers/<group>.py`: a pure `parse_*` function + a `Provider` subclass with `info`,
   `search()`, and `get()` if search results are incomplete.
2. Record a trimmed real response into `tests/fixtures/<id>_search.json`.
3. Parser test in `tests/test_providers.py`.
4. Add the class to `PROVIDERS` in `providers/__init__.py`.
5. Add a row here. If it duplicates an Openverse source, add it to `NATIVE_DUPES` in `openverse.py`.
6. Set the right default trust. When in doubt: uploader.
