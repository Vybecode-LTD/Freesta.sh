"""The key catalog is the one source for "where do I get this key?" on the web and the desktop."""

import json
from pathlib import Path

from freestash.config import Settings
from freestash.providers import PROVIDERS
from freestash.providers.keys import KEY_CATALOG

SHARED = Path(__file__).resolve().parents[2] / "shared" / "provider-keys.json"


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


def test_shared_copy_is_current():
    """Fails when KEY_CATALOG changed without `python scripts/export_shared.py` (the desktop reads the copy)."""
    assert SHARED.exists(), "run: python scripts/export_shared.py"
    assert json.loads(SHARED.read_text(encoding="utf-8")) == [k.as_json() for k in KEY_CATALOG]
