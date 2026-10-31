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

    public string? Token => Current?.Token;

    public bool IsSignedIn => Current is not null;

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
