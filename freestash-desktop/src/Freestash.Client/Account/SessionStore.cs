using System.Text.Json;
using Freestash.Client.Settings;

namespace Freestash.Client.Account;

/// <summary>
/// Keeps the account session in <see cref="SecretStore"/> (DPAPI on Windows), never in settings.json,
/// the way Seeq'r's desktop keeps its JWT. Restored on launch, re-checked against /api/auth/me.
/// </summary>
public sealed class SessionStore(SecretStore secrets)
{
    public const string SecretName = "FREESTASH_SESSION";

    public event Action? Changed;

    public Session? Current
    {
        get
        {
            var raw = secrets.Get(SecretName);
            if (raw is null) return null;
            try { return JsonSerializer.Deserialize<Session>(raw, FreestashJson.Options); }
            catch (JsonException) { return null; }
        }
    }

    /// <summary>The session, but only for the server that issued it: pointing the app elsewhere never leaks the token.</summary>
    public Session? CurrentFor(Uri server) => Current is { } s && s.Server == Origin(server) ? s : null;

    public string? TokenFor(Uri server) => CurrentFor(server)?.Token;

    /// <summary>scheme://host[:port], lower-case: the part of a URL that decides who receives a request.</summary>
    public static string Origin(Uri server) => server.GetLeftPart(UriPartial.Authority).ToLowerInvariant();

    public void Set(Session? session)
    {
        secrets.Set(SecretName, session is null ? null : JsonSerializer.Serialize(session, FreestashJson.Options));
        secrets.Save();
        Changed?.Invoke();
    }

    public void UpdateUser(SessionUser user)
    {
        if (Current is { } s) Set(s with { User = user });
    }
}
