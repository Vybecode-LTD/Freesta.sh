"""GitHub: repositories tagged `game-assets`, one pack each (contract github-and-curated-packs).

Search is GitHub's REST repository search, which allows 30 requests a minute with a token and 10 without (per token,
or per IP). The budget below stays under that within this process, and after a 403 or 429 the token waits a minute
instead of retrying (ground rule 2). Only `game-assets` is searched: `sprites`, `sound-effects` and the brush topics
mostly tag tools and painting apps (probe, 2026-11-04). The license is GitHub's reading of the repo's license file,
asserted by whoever owns the repo, so packs from here are uploader trust.
"""

from __future__ import annotations

import hashlib
import re
import time
from collections import Counter
from urllib.parse import quote

from freestash.http import RETRY_STATUS, ProviderHTTPError
from freestash.licenses.normalize import normalize_license
from freestash.models import Asset, LicenseInfo, MediaType, Rendition, Trust
from freestash.providers.base import Provider, ProviderInfo, ProviderPage, SearchHints, extract_year, tokens
from freestash.ratelimit import RateLimiter

API = "https://api.github.com"
TOPIC = "game-assets"
SEARCH_PER_MINUTE = {True: 25, False: 8}  # with a token, without one (GitHub allows 30 and 10)
COOL_DOWN_SECONDS = 60.0
NOTE = "GitHub reads the repository's license file; art inside can carry its own terms, so check the README."

_budget = RateLimiter()
_cool_down: dict[str, float] = {}  # bucket -> monotonic time it may call GitHub again
_FULL_NAME = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9._-]{1,100}")

# Words in a repo's topics, name or description that say what it holds. Topics are read first, then the name, then the
# description; within one, the first kind listed wins (a 3D pack's description mentions its textures).
_KINDS: list[tuple[MediaType, frozenset[str]]] = [
    (MediaType.MODEL, frozenset({"3d", "3d-models", "3d-assets", "low-poly", "lowpoly", "gltf", "glb", "fbx", "blender",
                                 "models", "voxel"})),
    (MediaType.SPRITE, frozenset({"sprite", "sprites", "spritesheet", "sprite-sheet", "pixel", "pixel-art", "pixelart",
                                  "tileset", "tilesets", "tilemap", "ui-kit"})),
    (MediaType.AUDIO, frozenset({"audio", "sound", "sounds", "sfx", "sound-effects", "music", "soundtrack", "chiptune"})),
    (MediaType.TEXTURE, frozenset({"texture", "textures", "pbr", "materials"})),
    (MediaType.ICON, frozenset({"icon", "icons", "icon-pack", "iconset"})),
]

# Extensions counted as the pack's files (code, docs and sprite-sheet metadata aren't).
ASSET_EXTENSIONS = frozenset({
    "png", "jpg", "jpeg", "gif", "webp", "svg", "bmp", "tga", "tif", "tiff", "psd", "kra", "aseprite", "ase", "xcf",
    "dds", "exr", "hdr", "ktx2", "wav", "ogg", "mp3", "flac", "aif", "aiff", "m4a", "opus", "glb", "gltf", "fbx", "obj",
    "mtl", "blend", "dae", "stl", "3ds", "ply", "usdz", "vox", "ttf", "otf", "woff", "woff2", "tmx", "tsx", "abr",
})


def kind_of(topics: list[str], name: str | None, description: str | None) -> MediaType:
    """Sprite when nothing says otherwise: most `game-assets` repos are 2D art."""
    for words in ({w for t in topics for w in (t.lower(), *t.lower().split("-"))}, set(tokens(name or "")),
                  set(tokens(description or ""))):
        for kind, vocabulary in _KINDS:
            if words & vocabulary:
                return kind
    return MediaType.SPRITE


def _license(spdx: str | None) -> LicenseInfo:
    if not spdx:
        return normalize_license(None).model_copy(update={"raw": "No license file in the repository"})
    if spdx == "NOASSERTION":
        return normalize_license(None).model_copy(
            update={"raw": "Other (GitHub couldn't identify the repository's license file)"})
    return normalize_license(spdx).model_copy(update={"raw": f"{spdx} (GitHub's reading of the repository's license file)"})


def _size(kb: int) -> str:
    return f"{kb / 1024:,.0f} MB" if kb >= 1024 else f"{max(kb, 1):,} KB"


def parse_github_repo(item: dict) -> Asset | None:
    """One search hit or `/repos/<owner>/<name>` response as a pack. None for anything private or disabled."""
    full = item.get("full_name")
    if not full or item.get("private") or item.get("disabled"):
        return None
    name = item.get("name") or full.split("/")[-1]
    branch = item.get("default_branch") or "main"
    owner = item.get("owner") or {}
    topics = list(item.get("topics") or [])
    created = item.get("created_at")
    stars, size = item.get("stargazers_count"), item.get("size")
    tips = []
    if size is not None:
        tips.append(f"About {_size(size)} on GitHub. The zip holds the whole repository, code and docs included.")
    if stars:
        tips.append(f"Starred {stars:,} time{'s' if stars != 1 else ''} on GitHub.")
    if item.get("archived"):
        tips.append("Archived by its owner: it isn't updated any more.")
    # The owner's avatar, from GitHub's CDN. Not the repo's social image: GitHub draws those on request and throttles
    # them per IP (a grid of them, then every one, answered 429 on 2026-11-04).
    avatar = owner.get("avatar_url")
    image = f"{avatar}{'&' if '?' in avatar else '?'}s=240" if avatar else None
    return Asset(
        provider="github", source_id=f"repo:{full}", title=name.replace("-", " ").replace("_", " ").strip() or name,
        media_type=kind_of(topics, name, item.get("description")), license=_license((item.get("license") or {}).get("spdx_id")),
        trust=Trust.UPLOADER, landing_url=item.get("html_url") or f"https://github.com/{full}", source_name="GitHub",
        creator=owner.get("login"), creator_url=owner.get("html_url"), thumbnail_url=image, preview_url=image,
        renditions=[Rendition(url=f"https://github.com/{full}/archive/refs/heads/{branch}.zip",
                              label=f"{name}-{branch.replace('/', '-')}.zip (whole repository)", mime="application/zip")],
        date=created[:10] if created else None, year=extract_year(created), tags=topics,
        description=item.get("description"), notes=[NOTE], tips=tips, detail_required=True, is_pack=True,
        extra={"stars": stars, "size_kb": size, "default_branch": branch, "pushed_at": item.get("pushed_at")}, raw=item,
    )


def parse_github_tree(tree: dict) -> tuple[int | None, list[str]]:
    """(asset files, their formats by how common). The count is None when GitHub truncated the listing."""
    counts: Counter[str] = Counter()
    for entry in tree.get("tree") or []:
        leaf = (entry.get("path") or "").rsplit("/", 1)[-1]
        if entry.get("type") == "blob" and "." in leaf.lstrip("."):
            ext = leaf.rsplit(".", 1)[-1].lower()
            if ext in ASSET_EXTENSIONS:
                counts[ext] += 1
    formats = [ext for ext, _ in counts.most_common(8)]
    return (None if tree.get("truncated") else sum(counts.values())), formats


class GitHubProvider(Provider):
    info = ProviderInfo(
        id="github", name="GitHub", homepage="https://github.com",
        media_types=frozenset({MediaType.SPRITE, MediaType.MODEL, MediaType.TEXTURE, MediaType.AUDIO, MediaType.ICON}),
        default_trust=Trust.UPLOADER, key_setting="github_access_token", key_optional=True,
        key_signup_url="https://github.com/settings/personal-access-tokens/new",
        docs_url="https://docs.github.com/en/rest/search/search#search-repositories",
        terms_url="https://docs.github.com/en/site-policy/github-terms/github-terms-of-service",
        packs_only=True,
        notes=("Searched only with Packs on: repositories tagged game-assets, one pack each.",
               "The license is GitHub's reading of the repository's license file, asserted by its owner."),
    )

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if token := self.key():
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _bucket(self, kind: str) -> str:
        token = self.key()
        return f"github:{kind}:" + (hashlib.sha256(token.encode()).hexdigest()[:16] if token else "anonymous")

    async def _get(self, path: str, params: dict | None = None, *, kind: str = "core") -> dict:
        bucket = self._bucket(kind)
        if _cool_down.get(bucket, 0.0) > time.monotonic():
            raise RuntimeError("GitHub asked Freesta.sh to slow down: it's searched again in a minute.")
        if kind == "search" and not _budget.allow(bucket, SEARCH_PER_MINUTE[bool(self.key())], 60):
            raise RuntimeError("GitHub's search limit for this minute is used up: try again in a minute.")
        try:
            return await self.http.get_json(f"{API}{path}", params=params, headers=self._headers(),
                                            retry_on=RETRY_STATUS - {429})
        except ProviderHTTPError as exc:
            if exc.status in (403, 429):
                _cool_down[bucket] = time.monotonic() + COOL_DOWN_SECONDS
            raise

    async def search(self, q: str, media_types: set[MediaType], limit: int, page: int,
                     hints: SearchHints) -> ProviderPage:
        if not hints.packs:  # the registry skips this source without packs; this keeps a direct call honest too
            return ProviderPage(assets=[])
        query = f"{' '.join(tokens(q))} topic:{TOPIC}".strip()
        # GitHub's page is the same size as ours: a bigger one cut down to `limit` would skip what was cut on page 2
        data = await self._get("/search/repositories", {"q": query, "per_page": limit, "page": page}, kind="search")
        assets = [a for item in data.get("items") or [] if (a := parse_github_repo(item)) and a.media_type in media_types]
        return ProviderPage(assets=assets[:limit], total=data.get("total_count"))

    async def get(self, source_id: str) -> Asset:
        kind, _, full = source_id.partition(":")
        if kind != "repo" or not _FULL_NAME.fullmatch(full) or full.split("/")[1] in (".", ".."):
            raise LookupError(f"Not a GitHub repository id: {source_id}")
        asset = parse_github_repo(await self._get(f"/repos/{full}"))
        if asset is None:
            raise LookupError(f"github:{source_id} isn't public")
        tips = list(asset.tips)
        try:
            tree = await self._get(f"/repos/{full}/git/trees/{quote(asset.extra['default_branch'], safe='')}",
                                   {"recursive": "1"})
            count, formats = parse_github_tree(tree)
        except ProviderHTTPError:  # an empty repository answers 409; the pack is still worth showing
            count, formats = None, []
            tips.append("GitHub didn't list this repository's files, so they aren't counted.")
        else:
            if count is None:
                tips.append("GitHub listed only part of this repository's files, so they aren't counted.")
        return asset.model_copy(update={"item_count": count, "formats": formats, "tips": tips, "detail_required": False})
