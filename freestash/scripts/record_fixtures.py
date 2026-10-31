"""Re-record provider fixtures from real API responses (IMPLEMENTATION.md P1).

    python scripts/record_fixtures.py smithsonian freesound pexels pixabay unsplash wikimedia

Needs the matching keys in .env. Responses are trimmed to a few items so fixtures stay small.
Review the diff before committing: fixtures must not contain your keys (they're query params for some APIs,
which never appear in response bodies, but check anyway).
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from freestash.config import get_settings
from freestash.http import HttpClient

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
Q = "lighthouse"


def trim(data, list_keys=("results", "rows", "photos", "hits", "items", "pages")):
    if isinstance(data, dict):
        out = {}
        for k, v in data.items():
            out[k] = v[:3] if k in list_keys and isinstance(v, list) else trim(v, list_keys)
        return out
    return data


async def main(names: list[str]) -> None:
    s = get_settings()
    async with HttpClient(s) as http:
        jobs = {
            "smithsonian": lambda: http.get_json("https://api.si.edu/openaccess/api/v1.0/search", params={
                "q": f"{Q} AND online_media_type:Images", "rows": 3, "api_key": s.smithsonian_api_key}, cache_ttl=0),
            "freesound": lambda: http.get_json("https://freesound.org/apiv2/search/text/", params={
                "query": "rain", "token": s.freesound_api_key, "page_size": 3,
                "fields": "id,name,username,license,previews,duration,tags,url,type,samplerate,channels,filesize,created,description"}, cache_ttl=0),
            "pexels": lambda: http.get_json("https://api.pexels.com/v1/search", params={"query": Q, "per_page": 3},
                                            headers={"Authorization": s.pexels_api_key or ""}, cache_ttl=0),
            "pixabay": lambda: http.get_json("https://pixabay.com/api/", params={"key": s.pixabay_api_key, "q": Q, "per_page": 3}, cache_ttl=0),
            "unsplash": lambda: http.get_json("https://api.unsplash.com/search/photos", params={"query": Q, "per_page": 3},
                                              headers={"Authorization": f"Client-ID {s.unsplash_access_key}"}, cache_ttl=0),
            "wikimedia": lambda: http.get_json("https://commons.wikimedia.org/w/api.php", params={
                "action": "query", "format": "json", "formatversion": "2", "generator": "search",
                "gsrsearch": f"{Q} filetype:bitmap", "gsrnamespace": "6", "gsrlimit": "3", "prop": "imageinfo",
                "iiprop": "url|size|mime|extmetadata", "iiurlwidth": "640"},
                headers={"Authorization": f"Bearer {s.wikimedia_access_token}"} if s.wikimedia_access_token else None, cache_ttl=0),
        }
        for name in names:
            if name not in jobs:
                print(f"skip {name}: no recorder")
                continue
            try:
                data = trim(await jobs[name]())
            except Exception as exc:  # noqa: BLE001
                print(f"FAIL {name}: {exc}")
                continue
            path = FIXTURES / f"{name}_search.json"
            path.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
            print(f"wrote {path.name}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:] or ["smithsonian", "freesound", "pexels", "pixabay", "unsplash", "wikimedia"]))
