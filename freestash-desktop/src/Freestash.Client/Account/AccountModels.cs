namespace Freestash.Client.Account;

/// <summary>The signed-in account. The same account signs in on freesta.sh (web) and here.</summary>
public sealed record SessionUser(string Id, string? Email, string? DisplayName, string? CreatedAt);

public sealed record AuthResponse(string AccessToken, SessionUser User);

/// <summary>A signed-in account. <paramref name="Server"/> is the origin that issued the token: it is never sent anywhere else.</summary>
public sealed record Session(string Token, SessionUser User, string? Server = null);

/// <summary>Mirrors freestash.providers.keys.KeySpec: where to get one provider credential, step by step.</summary>
public sealed record KeySpec(
    string Name, string Setting, string Provider, string ProviderName, string Label, string Url, string UrlLabel,
    List<string> Steps, string? Limits, string Unlocks, bool Optional, string? Notice, string? Action);

public sealed record KeyState(string Name, bool Set, string? Hint, string? UpdatedAt);

public sealed record KeysResponse(List<KeyState> Keys);

public sealed record RevealResponse(string Name, string? Value);

public sealed record OpenverseRegistration(Dictionary<string, string> Values, string Email, string Next);

/// <summary>Mirrors freestash.accounts.UserPrefs: what follows the account between the web and the desktop.</summary>
public sealed record UserPrefs(
    UseCase DefaultUseCase, Tier DefaultMaxTier, List<MediaType> DefaultMedia, int ResultsPerSource, string Theme, string Accent)
{
    public static UserPrefs Default => new(UseCase.Demo, Tier.Yellow, [MediaType.Image], 12, "dark", "sodium");
}

public sealed record PrefsEnvelope(UserPrefs Data, string? UpdatedAt);
