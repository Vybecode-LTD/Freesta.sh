"""The web app and the desktop app are one product. shared/parity.json is the map; this keeps it true."""

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PARITY = json.loads((REPO / "shared" / "parity.json").read_text(encoding="utf-8"))


def test_every_feature_exists_on_both_sides_or_says_why_not():
    problems = []
    for f in PARITY["features"]:
        for side in ("web", "desktop"):
            path = f.get(side)
            if path is None:
                if not (f.get("why") or "").strip():
                    problems.append(f"{f['id']}: no {side} file and no 'why'")
            elif not (REPO / path).exists():
                problems.append(f"{f['id']}: {side} file missing: {path}")
    assert not problems, "\n".join(problems)


def test_both_apps_list_the_same_screens_in_the_same_order():
    web = (REPO / "freestash/web/src/App.tsx").read_text(encoding="utf-8")
    desktop = (REPO / "freestash-desktop/src/Freestash.Desktop/ViewModels/MainWindowViewModel.cs").read_text(encoding="utf-8")
    web_nav = re.findall(r'\{ id: "\w+", label: "([^"]+)"', web)
    desktop_nav = re.findall(r'new NavItem\("([^"]+)"', desktop)
    assert len(web_nav) >= 7, f"couldn't read the web nav: {web_nav}"  # never pass on two empty lists
    assert web_nav == desktop_nav, f"web nav {web_nav} != desktop nav {desktop_nav}"
