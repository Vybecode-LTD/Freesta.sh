"""The provider-key catalog: one entry per credential the engine can use, with where to get it.

This is the single source of truth for the "how do I get this key?" help under every key field. The web app
reads it from `GET /api/keys/catalog`; the desktop app reads the same endpoint and falls back to
`shared/provider-keys.json`, which `scripts/export_shared.py` writes from this list (a test fails if they drift).
Step text is checked against each provider's own signup page; re-check it when a provider changes its flow.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from freestash.config import Settings


@dataclass(frozen=True)
class KeySpec:
    name: str  # env var the engine reads; also the key's id in the account API
    setting: str  # Settings attribute
    provider: str  # provider id
    provider_name: str
    label: str  # what the provider calls the value
    url: str  # the page to open first
    url_label: str  # the same URL, short enough to print under an input
    steps: tuple[str, ...]  # what to do there, in order
    limits: str | None = None  # free-tier limits as the provider states them
    unlocks: str = ""  # one line on what the key adds to search
    optional: bool = False  # the provider works without it
    notice: str | None = None  # a current problem with getting this key, shown as a warning
    action: str | None = None  # an in-app helper instead of a sign-up page ("openverse_register")

    def as_json(self) -> dict:
        d = asdict(self)
        d["steps"] = list(self.steps)
        return d


KEY_CATALOG: list[KeySpec] = [
    KeySpec(
        name="SMITHSONIAN_API_KEY", setting="smithsonian_api_key", provider="smithsonian",
        provider_name="Smithsonian Open Access", label="api.data.gov key",
        url="https://api.data.gov/signup/", url_label="api.data.gov/signup",
        steps=("Enter your first name, last name and email, then submit the form.",
               "api.data.gov emails you the key. Copy it from that email and paste it here."),
        limits="1,000 requests an hour",
        unlocks="About 5 million CC0 images from the Smithsonian's museums.",
    ),
    KeySpec(
        name="UNSPLASH_ACCESS_KEY", setting="unsplash_access_key", provider="unsplash",
        provider_name="Unsplash", label="Access Key",
        url="https://unsplash.com/oauth/applications", url_label="unsplash.com/oauth/applications",
        steps=("Join or log in to Unsplash; the link opens Your apps.",
               "Click New Application, accept the API guidelines and fill in the app's details.",
               "On the app's page, copy the Access Key (not the Secret key)."),
        limits="50 requests an hour in demo mode; more once Unsplash approves the app for production",
        unlocks="Unsplash photos. Fine for demos and client mockups; Freesta.sh marks them red for bundled use.",
    ),
    KeySpec(
        name="PEXELS_API_KEY", setting="pexels_api_key", provider="pexels",
        provider_name="Pexels", label="API key",
        url="https://www.pexels.com/api/key/", url_label="pexels.com/api/key",
        steps=("If you already have a key, log in and copy it from this page.",
               "When sign-ups reopen: log in at pexels.com/api, click Get Started, and the key appears straight away."),
        limits="200 requests an hour, 20,000 a month",
        unlocks="Pexels photos and video for demo and client work.",
        notice="Pexels has paused new API keys (checked 31 Oct 2026). Existing keys still work.",
    ),
    KeySpec(
        name="PIXABAY_API_KEY", setting="pixabay_api_key", provider="pixabay",
        provider_name="Pixabay", label="API key",
        url="https://pixabay.com/api/docs/", url_label="pixabay.com/api/docs",
        steps=("Log in or sign up with the links beside the key row on that page.",
               "Back on the docs page, under Search Images → Parameters, copy the value in the \"key (required)\" row."),
        limits="100 requests a minute",
        unlocks="Pixabay photos, illustrations and video. Pixabay forbids hotlinking, so download files instead.",
    ),
    KeySpec(
        name="FREESOUND_API_KEY", setting="freesound_api_key", provider="freesound",
        provider_name="Freesound", label="API key",
        url="https://freesound.org/apiv2/apply/", url_label="freesound.org/apiv2/apply",
        steps=("Log in, or click Join now to create a Freesound account.",
               "On the apply page, request a new API credential with a name and a short description.",
               "Copy the \"Client secret/Api key\" value from the table, not the Client id."),
        limits="60 requests a minute, 2,000 a day",
        unlocks="Sound effects and field recordings; filter to CC0 for factory libraries.",
    ),
    KeySpec(
        name="EUROPEANA_API_KEY", setting="europeana_api_key", provider="europeana",
        provider_name="Europeana", label="Personal API key",
        url="https://www.europeana.eu/en/create-and-use-a-europeana-account", url_label="europeana.eu → your account",
        steps=("Create or sign in to a Europeana account.",
               "In the menu under your nickname (top right), choose Manage API keys.",
               "Accept the API key terms, click Request a Personal API key, and copy the key it shows."),
        unlocks="Raises the limits of the shared demo key that Europeana searches use without one.",
        optional=True,
    ),
    KeySpec(
        name="WIKIMEDIA_ACCESS_TOKEN", setting="wikimedia_access_token", provider="wikimedia",
        provider_name="Wikimedia Commons", label="Owner-only access token",
        url="https://meta.wikimedia.org/wiki/Special:OAuthConsumerRegistration/propose/oauth2",
        url_label="meta.wikimedia.org → propose OAuth 2.0 consumer",
        steps=("Log in to Wikimedia, then give the consumer a name and description.",
               "Tick \"This consumer is for use only by <your username>\" and submit.",
               "Copy the access token shown straight away; it isn't shown again."),
        limits="200 requests a minute for new accounts (anonymous: 10)",
        unlocks="Lifts the heavy rate limits on anonymous Commons searches.",
        optional=True,
    ),
    KeySpec(
        name="OPENVERSE_CLIENT_ID", setting="openverse_client_id", provider="openverse",
        provider_name="Openverse", label="Client ID",
        url="https://api.openverse.org/v1/#tag/auth", url_label="api.openverse.org (no sign-up page)",
        steps=("Openverse has no sign-up page. Press Register and Freesta.sh asks Openverse for credentials in your name.",
               "Click the verification link Openverse emails you; until then the keys work at anonymous limits."),
        unlocks="Raises the anonymous cap of 20 results a page and 240 per query.",
        optional=True,
        action="openverse_register",
    ),
    KeySpec(
        name="OPENVERSE_CLIENT_SECRET", setting="openverse_client_secret", provider="openverse",
        provider_name="Openverse", label="Client secret",
        url="https://api.openverse.org/v1/#tag/auth", url_label="api.openverse.org (no sign-up page)",
        steps=("Filled in together with the Client ID when you press Register.",),
        unlocks="Pairs with the Client ID.",
        optional=True,
    ),
]

KEY_NAMES: frozenset[str] = frozenset(k.name for k in KEY_CATALOG)
_BY_NAME = {k.name: k for k in KEY_CATALOG}


def key_spec(name: str) -> KeySpec | None:
    return _BY_NAME.get(name)


def settings_with_keys(base: Settings, keys: dict[str, str], *, share_server_keys: bool) -> Settings:
    """The engine settings for one user: their own keys, plus the server's only if sharing is on."""
    update = {}
    for spec in KEY_CATALOG:
        own = (keys.get(spec.name) or "").strip()
        update[spec.setting] = own or (getattr(base, spec.setting) if share_server_keys else None)
    return base.model_copy(update=update)
