using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;

namespace Freestash.Client.Account;

/// <summary>
/// The account endpoints (freestash/src/freestash/api/auth.py + account.py): the same calls the web app makes,
/// so one account, one set of keys and one set of preferences work in both. A 401 raises <see cref="SessionExpired"/>.
/// </summary>
public sealed class AccountClient : IDisposable
{
    private readonly HttpClient _http;
    private readonly Func<string?> _token;

    public AccountClient(Uri baseUri, Func<string?> token, HttpMessageHandler? handler = null)
    {
        _token = token;
        _http = handler is null ? new HttpClient() : new HttpClient(handler, disposeHandler: false);
        _http.BaseAddress = baseUri;
        _http.Timeout = TimeSpan.FromSeconds(30);
        _http.DefaultRequestHeaders.UserAgent.ParseAdd("FreestashDesktop/0.1 (+https://freesta.sh)");
    }

    /// <summary>Raised (once per call) when the server says the session is no longer valid.</summary>
    public event Action? SessionExpired;

    public void Dispose() => _http.Dispose();

    public async Task<Session> LoginAsync(string email, string password, CancellationToken ct = default) =>
        ToSession(await Send<AuthResponse>(HttpMethod.Post, "/api/auth/login", new { email, password }, ct, auth: false));

    public async Task<Session> RegisterAsync(string email, string password, string? displayName, CancellationToken ct = default) =>
        ToSession(await Send<AuthResponse>(HttpMethod.Post, "/api/auth/register", new { email, password, display_name = displayName }, ct, auth: false));

    public Task ForgotAsync(string email, CancellationToken ct = default) =>
        Send<JsonElement>(HttpMethod.Post, "/api/auth/forgot", new { email }, ct, auth: false);

    public Task<SessionUser> MeAsync(CancellationToken ct = default) => Send<SessionUser>(HttpMethod.Get, "/api/auth/me", null, ct);

    public Task SignOutEverywhereAsync(CancellationToken ct = default) => Send<JsonElement?>(HttpMethod.Post, "/api/auth/logout-all", null, ct);

    public Task<PrefsEnvelope> PrefsAsync(CancellationToken ct = default) => Send<PrefsEnvelope>(HttpMethod.Get, "/api/me/settings", null, ct);

    public Task<PrefsEnvelope> SavePrefsAsync(UserPrefs prefs, CancellationToken ct = default) =>
        Send<PrefsEnvelope>(HttpMethod.Put, "/api/me/settings", new { data = prefs }, ct);

    public async Task<List<KeyState>> KeysAsync(CancellationToken ct = default) =>
        (await Send<KeysResponse>(HttpMethod.Get, "/api/me/keys", null, ct)).Keys;

    /// <summary>Save or remove keys: a null or empty value removes that key from the account.</summary>
    public async Task<List<KeyState>> SaveKeysAsync(IReadOnlyDictionary<string, string?> values, CancellationToken ct = default) =>
        (await Send<KeysResponse>(HttpMethod.Put, "/api/me/keys", new { values }, ct)).Keys;

    public async Task<string?> RevealKeyAsync(string name, CancellationToken ct = default) =>
        (await Send<RevealResponse>(HttpMethod.Get, $"/api/me/keys/{Uri.EscapeDataString(name)}", null, ct)).Value;

    public Task<List<KeySpec>> KeyCatalogAsync(CancellationToken ct = default) =>
        Send<List<KeySpec>>(HttpMethod.Get, "/api/keys/catalog", null, ct, auth: false);

    public Task<OpenverseRegistration> RegisterOpenverseAsync(string? email, CancellationToken ct = default) =>
        Send<OpenverseRegistration>(HttpMethod.Post, "/api/keys/openverse/register", new { email }, ct);

    private Session ToSession(AuthResponse r) => new(r.AccessToken, r.User, SessionStore.Origin(_http.BaseAddress!));

    private async Task<T> Send<T>(HttpMethod method, string path, object? body, CancellationToken ct, bool auth = true)
    {
        using var msg = new HttpRequestMessage(method, path);
        if (auth && _token() is { Length: > 0 } t) msg.Headers.Authorization = new AuthenticationHeaderValue("Bearer", t);
        if (body is not null) msg.Content = JsonContent.Create(body, options: FreestashJson.Options);
        using var res = await _http.SendAsync(msg, ct);
        if (!res.IsSuccessStatusCode)
        {
            var text = await res.Content.ReadAsStringAsync(ct);
            var message = text;
            try
            {
                using var doc = JsonDocument.Parse(text);
                if (doc.RootElement.TryGetProperty("detail", out var d)) message = d.ValueKind == JsonValueKind.String ? d.GetString()! : d.ToString();
            }
            catch (JsonException) { }
            if ((int)res.StatusCode == 401 && auth) SessionExpired?.Invoke();
            throw new FreestashApiException((int)res.StatusCode, string.IsNullOrWhiteSpace(message) ? res.ReasonPhrase ?? "error" : message);
        }
        if (res.StatusCode == System.Net.HttpStatusCode.NoContent || res.Content.Headers.ContentLength == 0) return default!;
        return (await res.Content.ReadFromJsonAsync<T>(FreestashJson.Options, ct))!;
    }
}
