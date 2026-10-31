"""Write the files both apps share from the engine's own definitions (run after changing them).

    python scripts/export_shared.py          # rewrite ../shared/*.json
    python scripts/export_shared.py --check  # exit 1 if they're out of date (CI)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from freestash.providers.keys import KEY_CATALOG

SHARED = Path(__file__).resolve().parents[2] / "shared"


def outputs() -> dict[Path, str]:
    keys = json.dumps([k.as_json() for k in KEY_CATALOG], indent=2, ensure_ascii=False) + "\n"
    return {SHARED / "provider-keys.json": keys}


def main() -> int:
    check = "--check" in sys.argv
    stale = []
    for path, body in outputs().items():
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current == body:
            continue
        stale.append(path)
        if not check:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8", newline="\n")
    for p in stale:
        print(("STALE " if check else "wrote ") + str(p))
    return 1 if check and stale else 0


if __name__ == "__main__":
    raise SystemExit(main())
