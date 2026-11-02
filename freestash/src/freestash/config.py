"""Runtime settings. Everything is env-driven so CLI, MCP, and API share one config."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _key(name: str) -> Field:  # type: ignore[valid-type]
    """API keys accept either FREESTASH_<NAME> or the bare <NAME> env var."""
    return Field(default=None, validation_alias=AliasChoices(f"FREESTASH_{name}", name))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FREESTASH_", env_file=".env", extra="ignore")

    # --- identity -------------------------------------------------------
    # Several providers (Wikimedia, Poly Haven, AIC, Met) block or throttle generic
    # user agents. Always send something identifiable with a contact address.
    user_agent: str = "Freestash/0.1 (+https://freesta.sh; internal asset finder)"
    contact_email: str | None = None

    # --- storage --------------------------------------------------------
    data_dir: Path = Path.home() / ".freestash"
    database_url: str | None = None  # default: sqlite:///<data_dir>/freestash.db
    download_dir: Path | None = None  # default: <data_dir>/downloads

    # --- behaviour ------------------------------------------------------
    http_timeout: float = 20.0
    provider_timeout: float = 30.0  # hard ceiling per provider inside a federated search
    http_retries: int = 2
    cache_ttl_seconds: int = 3600
    max_download_mb: int = 250
    disabled_providers: list[str] = Field(default_factory=list)

    # --- provider credentials (all optional; providers without keys are skipped) ---
    smithsonian_api_key: str | None = _key("SMITHSONIAN_API_KEY")  # api.data.gov key
    europeana_api_key: str | None = _key("EUROPEANA_API_KEY")
    freesound_api_key: str | None = _key("FREESOUND_API_KEY")
    pexels_api_key: str | None = _key("PEXELS_API_KEY")
    pixabay_api_key: str | None = _key("PIXABAY_API_KEY")
    unsplash_access_key: str | None = _key("UNSPLASH_ACCESS_KEY")
    wikimedia_access_token: str | None = _key("WIKIMEDIA_ACCESS_TOKEN")  # OAuth 2.0 owner-only token
    openverse_client_id: str | None = _key("OPENVERSE_CLIENT_ID")
    openverse_client_secret: str | None = _key("OPENVERSE_CLIENT_SECRET")

    # --- web API / accounts ----------------------------------------------
    # "none" (local, single user) | "accounts" (sign-up + JWT, the hosted app). Anything else fails at startup:
    # every guard checks != "accounts", so a typo would otherwise serve everyone as one anonymous user.
    auth_mode: Literal["none", "accounts"] = "none"
    secret_key: str | None = None  # signs session tokens; required in accounts mode (>= 32 chars)
    secrets_key: str | None = None  # Fernet key that encrypts users' provider keys at rest
    token_days: int = 30
    signup_open: bool = True
    # Comma-separated. These accounts are always admins (decision 0003); the admin screen can't demote them.
    admin_emails: str = ""
    public_url: str = "https://freesta.sh"  # used in password-reset links
    trust_cf_connecting_ip: bool = False  # True only when Cloudflare proxies the domain: otherwise clients can forge it
    # Reset email over SMTP from a Spacemail mailbox (decision 0002). Sends only once both login fields are set.
    # Railway allows outbound SMTP only on the Pro plan; elsewhere the connection times out.
    smtp_host: str = "mail.spacemail.com"
    smtp_port: int = 465  # implicit TLS; 587 upgrades with STARTTLS
    smtp_username: str | None = None  # the mailbox's full address
    smtp_password: str | None = None
    email_from: str = "Freesta.sh <hello@freesta.sh>"  # must be the mailbox (or one of its aliases)
    log_emails: bool = False  # dev only (scripts/dev_accounts.py): log unsent emails, reset links included
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    @property
    def full_user_agent(self) -> str:
        return f"{self.user_agent}; {self.contact_email}" if self.contact_email else self.user_agent

    @property
    def admin_email_set(self) -> frozenset[str]:
        return frozenset(e.strip().lower() for e in self.admin_emails.split(",") if e.strip())

    @property
    def database_configured(self) -> bool:
        """A database URL was given. Railway leaves DATABASE_URL empty when its Postgres service is deleted."""
        return bool(self.database_url or os.environ.get("DATABASE_URL"))

    @property
    def resolved_database_url(self) -> str:
        """FREESTASH_DATABASE_URL, else Railway's DATABASE_URL, else a local SQLite file.

        Railway hands out `postgresql://…`; SQLAlchemy needs the psycopg 3 driver named explicitly.
        """
        url = self.database_url or os.environ.get("DATABASE_URL")
        if url:
            for prefix in ("postgres://", "postgresql://"):
                if url.startswith(prefix):
                    return "postgresql+psycopg://" + url[len(prefix):]
            return url
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{self.data_dir / 'freestash.db'}"

    @property
    def resolved_download_dir(self) -> Path:
        return self.download_dir or (self.data_dir / "downloads")


@lru_cache
def get_settings() -> Settings:
    return Settings()
