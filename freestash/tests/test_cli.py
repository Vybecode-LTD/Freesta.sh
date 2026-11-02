"""CLI file output. Regression: Windows' default codepage (cp1252) can't encode most non-Latin titles."""

from typer.testing import CliRunner

from freestash.cli import app
from freestash.config import get_settings
from freestash.licenses import evaluate
from freestash.models import ScoredAsset, UseCase
from freestash.store import Store, entry_from_scored

from .conftest import make_asset


def _search_cli(monkeypatch, tmp_path, args):
    """Run `freestash search` with the engine stubbed out; return (output, the SearchQuery it ran)."""
    from datetime import UTC, datetime

    from freestash import search as search_module
    from freestash.models import SearchResponse

    monkeypatch.setenv("FREESTASH_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    seen = []

    async def fake_search(self, query, settings=None):
        seen.append(query)
        return SearchResponse(query=query, results=[], providers=[], generated_at=datetime.now(UTC))

    monkeypatch.setattr(search_module.Freestash, "search", fake_search)
    try:
        result = CliRunner().invoke(app, ["search", *args])
    finally:
        get_settings.cache_clear()
    assert result.exit_code == 0, result.output
    return result.output, seen[0]


def test_search_reads_query_words_and_says_so(tmp_path, monkeypatch):
    out, query = _search_cli(monkeypatch, tmp_path, ["rain sfx"])
    assert (query.q, [m.value for m in query.media_types]) == ("rain", ["audio"])
    assert 'Read "sfx" as Audio' in out and 'searching "rain"' in out and "--literal" in out


def test_search_literal_or_explicit_media_keeps_every_word(tmp_path, monkeypatch):
    _, literal = _search_cli(monkeypatch, tmp_path, ["rain sfx", "--literal"])
    assert (literal.q, [m.value for m in literal.media_types]) == ("rain sfx", ["image"])
    out, explicit = _search_cli(monkeypatch, tmp_path, ["rain sfx", "-m", "video"])
    assert (explicit.q, [m.value for m in explicit.media_types]) == ("rain sfx", ["video"])
    assert "Read " not in out


def test_ledger_export_writes_utf8(tmp_path, monkeypatch):
    monkeypatch.setenv("FREESTASH_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    try:
        asset = make_asset("CC0-1.0").model_copy(update={"title": "神奈川沖浪裏 · Ψ", "creator": "葛飾北斎"})
        Store().add_entry(entry_from_scored(ScoredAsset(uid=asset.uid, asset=asset, verdict=evaluate(asset, UseCase.DEMO))))
        out = tmp_path / "ATTRIBUTION.md"

        result = CliRunner().invoke(app, ["ledger", "export", "-o", str(out)])

        assert result.exit_code == 0, result.output
        assert "神奈川沖浪裏" in out.read_text(encoding="utf-8")
    finally:
        get_settings.cache_clear()
