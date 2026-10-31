namespace Freestash.Client.Settings;

/// <summary>One credential the Freestash engine can use. EnvVar is what the Python engine reads.</summary>
public sealed record ProviderKey(string EnvVar, string Provider, string Label, string SignupUrl, string Hint, bool Optional);

public static class ProviderKeys
{
    public const string RemoteToken = "FREESTASH_REMOTE_TOKEN"; // team server access token (not passed to the engine)

    /// <summary>Keep in sync with freestash/.env.example and freestash/src/freestash/config.py.</summary>
    public static readonly IReadOnlyList<ProviderKey> All =
    [
        new("SMITHSONIAN_API_KEY", "Smithsonian Open Access", "api.data.gov key", "https://api.data.gov/signup/",
            "Free, instant. Unlocks ~5M CC0 Smithsonian images natively.", Optional: false),
        new("UNSPLASH_ACCESS_KEY", "Unsplash", "Access key", "https://unsplash.com/developers",
            "Great for demo sites; Freestash marks it red for bundled use. 50 requests/hour until approved.", Optional: false),
        new("PEXELS_API_KEY", "Pexels", "API key", "https://www.pexels.com/api/",
            "Photos and video. Demo/client friendly, never bundled.", Optional: false),
        new("PIXABAY_API_KEY", "Pixabay", "API key", "https://pixabay.com/api/docs/",
            "Photos and video. No hotlinking, so downloads are the way.", Optional: false),
        new("FREESOUND_API_KEY", "Freesound", "API key", "https://freesound.org/apiv2/apply/",
            "Sound effects and field recordings. Filter to CC0 for factory libraries.", Optional: false),
        new("EUROPEANA_API_KEY", "Europeana", "API key", "https://pro.europeana.eu/pages/get-api",
            "Optional: works on a shared demo key, with low limits.", Optional: true),
        new("WIKIMEDIA_ACCESS_TOKEN", "Wikimedia Commons", "OAuth 2.0 owner-only token",
            "https://meta.wikimedia.org/wiki/Special:OAuthConsumerRegistration/propose/oauth2",
            "Optional but recommended: anonymous requests are heavily rate limited since 2026.", Optional: true),
        new("OPENVERSE_CLIENT_ID", "Openverse", "Client ID", "https://api.openverse.org/v1/#tag/auth/operation/register",
            "Optional: raises the 20-per-page / 240-result anonymous cap.", Optional: true),
        new("OPENVERSE_CLIENT_SECRET", "Openverse", "Client secret", "https://api.openverse.org/v1/#tag/auth/operation/register",
            "Pairs with the client ID.", Optional: true),
    ];
}
