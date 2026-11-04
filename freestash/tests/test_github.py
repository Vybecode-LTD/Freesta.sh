"""GitHub game-asset repositories as packs (contract github-and-curated-packs), against recorded responses."""

import pytest

from freestash.http import ProviderHTTPError
from freestash.models import MediaType, Trust
from freestash.providers.base import SearchHints
from freestash.providers.github import NOTE, GitHubProvider, kind_of, parse_github_repo, parse_github_tree

from .test_providers import FakeHttp

ALL_KINDS = set(GitHubProvider.info.media_types)


def _repos(fixture) -> dict[str, dict]:
    return {i["full_name"]: i for i in fixture("github_search")["items"]}


def test_a_repository_is_one_pack_under_its_license_file(fixture):
    repos = _repos(fixture)
    mit = parse_github_repo(repos["kweezl/spacecraft-resources"])
    assert (mit.uid, mit.title, mit.license.id, mit.trust) == (
        "github:repo:kweezl/spacecraft-resources", "spacecraft resources", "MIT", Trust.UPLOADER)
    assert mit.license.raw == "MIT (GitHub's reading of the repository's license file)"
    assert mit.is_pack and mit.members_checked is None and mit.item_count is None and mit.detail_required
    assert [(r.url, r.label) for r in mit.renditions] == [(
        "https://github.com/kweezl/spacecraft-resources/archive/refs/heads/main.zip",
        "spacecraft-resources-main.zip (whole repository)")]
    # the owner's avatar: GitHub's social images are drawn on request and throttled per IP
    assert mit.thumbnail_url == mit.preview_url == "https://avatars.githubusercontent.com/u/20753596?v=4&s=240"
    assert mit.landing_url == "https://github.com/kweezl/spacecraft-resources" and mit.creator == "kweezl"
    assert mit.source_name == "GitHub"  # the drawer's Source row, as both apps print it
    assert NOTE in mit.notes and "game-assets" in mit.tags and mit.year and mit.date
    assert mit.tips[0].startswith("About 748 KB on GitHub.")

    other = parse_github_repo(repos["KayKit-Game-Assets/KayKit-Space-Base-Bits-1.0"])
    assert other.license.id == "RIGHTS-UNKNOWN"
    assert other.license.raw == "Other (GitHub couldn't identify the repository's license file)"
    assert other.tips[0].startswith("About 5 MB on GitHub.")
    none = parse_github_repo(repos["RhysBoxGameStudios/space-station-assets"])
    assert (none.license.id, none.license.raw) == ("RIGHTS-UNKNOWN", "No license file in the repository")
    assert parse_github_repo({**repos["kweezl/spacecraft-resources"], "private": True}) is None


def test_the_kind_comes_from_topics_then_name_then_description(fixture):
    assert kind_of(["3d-models", "game-assets"], "retro-sfx", None) == MediaType.MODEL  # topics first
    assert kind_of(["game-assets"], "retro-sfx-pack", "pixel art") == MediaType.AUDIO  # then the name
    assert kind_of([], "space", "Low poly 3D models with PBR textures") == MediaType.MODEL  # model before texture
    assert kind_of([], "space", None) == MediaType.SPRITE  # most game-asset repos are 2D art
    repos = _repos(fixture)
    assert parse_github_repo(repos["HalfIsOnline/waste-no-space"]).media_type == MediaType.SPRITE  # "pixel-art theme"


def test_the_tree_counts_asset_files_and_their_formats(fixture):
    tree = fixture("github_tree")
    assert parse_github_tree(tree) == (5, ["png", "webp"])  # README, Credits.txt, .json/.xml metadata aren't counted
    assert parse_github_tree({**tree, "truncated": True}) == (None, ["png", "webp"])
    assert parse_github_tree({"tree": [{"path": ".gitignore", "type": "blob"}, {"path": "art", "type": "tree"}]}) == (0, [])


async def test_search_asks_for_game_assets_with_the_token_and_only_for_packs(fixture, settings):
    settings.github_access_token = "tok"
    http = FakeHttp([("/search/repositories", fixture("github_search"))])
    provider = GitHubProvider(http, settings)
    assert (await provider.search("space", ALL_KINDS, 4, 1, SearchHints())).assets == [] and http.calls == []

    page = await provider.search("space-ship: ships", ALL_KINDS, 4, 2, SearchHints(packs=True))
    url, params = http.calls[0]
    assert url == "https://api.github.com/search/repositories"
    # words only, no qualifiers; GitHub's pages are the same size as ours (PR #9 review, Codex P2: asking for 3x and
    # keeping 4 meant page 2 started at repo 13, so repos 5-12 were never reachable)
    assert params == {"q": "space ship ships topic:game-assets", "per_page": 4, "page": 2}
    assert http.headers[0]["Authorization"] == "Bearer tok" and http.headers[0]["Accept"] == "application/vnd.github+json"
    assert len(page.assets) == 4 and all(a.is_pack for a in page.assets) and page.total == 12

    icons = await provider.search("space", {MediaType.ICON}, 4, 1, SearchHints(packs=True))
    assert [a.source_id for a in icons.assets] == ["repo:kweezl/spacecraft-resources"]  # "recolored icons"


async def test_the_search_budget_stops_calls_before_github_does(fixture, settings):
    http = FakeHttp([("/search/repositories", fixture("github_search"))])
    provider = GitHubProvider(http, settings)  # no token: 8 a minute (GitHub allows 10)
    for _ in range(8):
        await provider.search("space", ALL_KINDS, 4, 1, SearchHints(packs=True))
    with pytest.raises(RuntimeError, match="used up"):
        await provider.search("space", ALL_KINDS, 4, 1, SearchHints(packs=True))
    assert len(http.calls) == 8
    settings.github_access_token = "tok"  # a token has its own budget
    await GitHubProvider(http, settings).search("space", ALL_KINDS, 4, 1, SearchHints(packs=True))
    assert len(http.calls) == 9


async def test_a_403_or_429_makes_that_token_wait_a_minute(settings):
    url = "https://api.github.com/search/repositories"
    http = FakeHttp([("/search/repositories", ProviderHTTPError(403, url, "rate limit exceeded"))])
    provider = GitHubProvider(http, settings)
    with pytest.raises(ProviderHTTPError):
        await provider.search("space", ALL_KINDS, 4, 1, SearchHints(packs=True))
    with pytest.raises(RuntimeError, match="slow down"):
        await provider.search("space", ALL_KINDS, 4, 1, SearchHints(packs=True))
    assert len(http.calls) == 1  # waited, not retried


async def test_detail_reads_the_repository_and_its_tree(fixture, settings):
    http = FakeHttp([("/git/trees/", fixture("github_tree")), ("/repos/fccm2/spaceships-drawn", fixture("github_repo"))])
    pack = await GitHubProvider(http, settings).get("repo:fccm2/spaceships-drawn")
    assert (pack.item_count, pack.formats, pack.detail_required) == (5, ["png", "webp"], False)
    assert [u for u, _ in http.calls] == ["https://api.github.com/repos/fccm2/spaceships-drawn",
                                          "https://api.github.com/repos/fccm2/spaceships-drawn/git/trees/master"]
    assert http.calls[1][1] == {"recursive": "1"}
    assert pack.renditions[0].url.endswith("/archive/refs/heads/master.zip")

    empty = FakeHttp([("/git/trees/", ProviderHTTPError(409, "u", "Git Repository is empty.")),
                      ("/repos/fccm2/spaceships-drawn", fixture("github_repo"))])
    pack = await GitHubProvider(empty, settings).get("repo:fccm2/spaceships-drawn")
    assert pack.item_count is None and "aren't counted" in pack.tips[-1]


@pytest.mark.parametrize("source_id", ["repo:../../user", "repo:a/b/c", "repo:owner/..", "pack:owner/name", "repo:"])
async def test_detail_refuses_anything_but_owner_slash_name(settings, source_id):
    http = FakeHttp([])
    with pytest.raises(LookupError):
        await GitHubProvider(http, settings).get(source_id)
    assert http.calls == []
