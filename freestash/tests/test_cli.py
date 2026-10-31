"""CLI file output. Regression: Windows' default codepage (cp1252) can't encode most non-Latin titles."""

from typer.testing import CliRunner

from freestash.cli import app
from freestash.config import get_settings
from freestash.licenses import evaluate
from freestash.models import ScoredAsset, UseCase
from freestash.store import Store, entry_from_scored

from .conftest import make_asset


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
