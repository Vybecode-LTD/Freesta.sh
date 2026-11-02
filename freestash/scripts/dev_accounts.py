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
from collections.abc import MutableMapping
from pathlib import Path

from cryptography.fernet import Fernet


def prepare_environment(port: str, base: Path, environ: MutableMapping[str, str]) -> None:
    """Accounts mode against base/freestash.db, always: an inherited DATABASE_URL must never point this server,
    with its own fresh encryption key, at a real database."""
    base.mkdir(parents=True, exist_ok=True)
    secrets_file = base / "dev-secrets.json"
    if not secrets_file.exists():
        # 0600 from the start: the file holds the session-signing key and the key that decrypts saved provider keys
        fd = os.open(secrets_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"secret_key": secrets.token_urlsafe(48), "secrets_key": Fernet.generate_key().decode()}, f)
    os.chmod(secrets_file, 0o600)  # also tightens a file an older version created world-readable
    s = json.loads(secrets_file.read_text(encoding="utf-8"))
    environ.pop("DATABASE_URL", None)
    environ.update({
        "FREESTASH_AUTH_MODE": "accounts", "FREESTASH_SECRET_KEY": s["secret_key"], "FREESTASH_SECRETS_KEY": s["secrets_key"],
        "FREESTASH_DATA_DIR": str(base), "FREESTASH_DATABASE_URL": f"sqlite:///{base / 'freestash.db'}",
        "FREESTASH_PUBLIC_URL": f"http://127.0.0.1:{port}", "FREESTASH_LOG_EMAILS": "true",  # reset links in the console
    })
    environ.setdefault("FREESTASH_CONTACT_EMAIL", "dev@freesta.sh")
    environ.setdefault("FREESTASH_ADMIN_EMAILS", "admin@example.test")  # sign up as this to reach #/admin locally


def main() -> None:
    port = sys.argv[sys.argv.index("--port") + 1] if "--port" in sys.argv else "8787"
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share") / "Freestash" / "dev"
    if "onedrive" in str(base).lower():
        raise SystemExit(f"refusing to write into a OneDrive folder: {base}")
    prepare_environment(port, base, os.environ)
    import uvicorn

    uvicorn.run("freestash.api.app:app", host="127.0.0.1", port=int(port))


if __name__ == "__main__":
    main()
