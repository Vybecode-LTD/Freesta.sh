"""Run the API + built web UI locally in accounts mode, the way Railway runs it, against a throwaway SQLite DB.

    python scripts/dev_accounts.py [--port 8787]

Keeps its data and generated secrets in %LOCALAPPDATA%/Freestash/dev (never in the repo or OneDrive),
so accounts and saved keys survive restarts. Delete that folder to start over.
"""

from __future__ import annotations

import json
import os
import secrets
import sys
from pathlib import Path

from cryptography.fernet import Fernet


def main() -> None:
    port = sys.argv[sys.argv.index("--port") + 1] if "--port" in sys.argv else "8787"
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share") / "Freestash" / "dev"
    if "onedrive" in str(base).lower():
        raise SystemExit(f"refusing to write into a OneDrive folder: {base}")
    base.mkdir(parents=True, exist_ok=True)
    secrets_file = base / "dev-secrets.json"
    if not secrets_file.exists():
        secrets_file.write_text(json.dumps({"secret_key": secrets.token_urlsafe(48),
                                            "secrets_key": Fernet.generate_key().decode()}), encoding="utf-8")
    s = json.loads(secrets_file.read_text(encoding="utf-8"))
    os.environ.update({
        "FREESTASH_AUTH_MODE": "accounts", "FREESTASH_SECRET_KEY": s["secret_key"], "FREESTASH_SECRETS_KEY": s["secrets_key"],
        "FREESTASH_DATA_DIR": str(base), "FREESTASH_PUBLIC_URL": f"http://127.0.0.1:{port}",
    })
    os.environ.setdefault("FREESTASH_CONTACT_EMAIL", "dev@freesta.sh")
    import uvicorn

    uvicorn.run("freestash.api.app:app", host="127.0.0.1", port=int(port))


if __name__ == "__main__":
    main()
