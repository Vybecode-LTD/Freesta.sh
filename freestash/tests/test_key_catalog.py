"""Shared definitions: the key catalog (where to get each key) and the design tokens, used by both apps."""

import importlib.util
from pathlib import Path

from freestash.config import Settings
from freestash.providers import PROVIDERS
from freestash.providers.keys import KEY_CATALOG

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "export_shared.py"


def _exporter():
    spec = importlib.util.spec_from_file_location("export_shared", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_every_keyed_provider_has_help():
    settings_fields = set(Settings.model_fields)
    by_setting = {k.setting: k for k in KEY_CATALOG}
    for cls in PROVIDERS:
        if cls.info.key_setting:
            assert cls.info.key_setting in by_setting, f"{cls.info.id} has a key but no KEY_CATALOG entry"
    for k in KEY_CATALOG:
        assert k.setting in settings_fields
        assert k.url.startswith("https://") and k.steps and all(s.strip() for s in k.steps)
        assert len(k.url_label) <= 60, "url_label is printed under an input; keep it short"


def test_generated_files_are_current():
    """Fails when keys.py or shared/design-tokens.json changed without `python scripts/export_shared.py`.

    The web app's tokens.css, the desktop's DesignTokens.g.cs and shared/provider-keys.json are generated,
    so a colour or a key's help text can't change in one app and not the other.
    """
    stale = [str(p) for p, body in _exporter().outputs().items()
             if not p.exists() or p.read_text(encoding="utf-8") != body]
    assert not stale, "run: python scripts/export_shared.py  (stale: " + ", ".join(stale) + ")"


def test_argb_conversion():
    exp = _exporter()
    assert exp._argb("#06090E") == "#FF06090E" and exp._argb("#96ACCC24") == "#2496ACCC"
