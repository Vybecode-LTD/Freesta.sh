using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Runtime.CompilerServices;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Freestash.Client;

public static class FreestashJson
{
    public static readonly JsonSerializerOptions Options = new(JsonSerializerDefaults.Web)
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        DictionaryKeyPolicy = null,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        Converters = { new JsonStringEnumConverter(JsonNamingPolicy.SnakeCaseLower) },
    };
}

public sealed class FreestashApiException(int status, string message) : Exception(message)
{
    public int Status { get; } = status;
}

/// <summary>Everything the desktop app needs from a Freestash server (local sidecar or hosted team instance).</summary>
public interface IFreestashApi
{
    Uri BaseUri { get; }
    Task<HealthInfo> HealthAsync(CancellationToken ct = default);
    Task<List<ProviderInfo>> ProvidersAsync(CancellationToken ct = default);
    Task<PdCutoff> PdCutoffAsync(CancellationToken ct = default);
    IAsyncEnumerable<StreamBatch> SearchStreamAsync(SearchRequest request, CancellationToken ct = default);
    Task<AssetDetail> AssetAsync(string uid, UseCase use, CancellationToken ct = default);
    Task<LicenseCheckResult> CheckLicenseAsync(string license, Trust trust, MediaType media, int? year, CancellationToken ct = default);
    Task<List<Collection>> CollectionsAsync(CancellationToken ct = default);
    Task<Collection> CollectionAsync(string id, CancellationToken ct = default);
    Task<Collection> CreateCollectionAsync(string name, UseCase use, string? description = null, CancellationToken ct = default);
    Task DeleteCollectionAsync(string id, CancellationToken ct = default);
    Task<Collection> AddToCollectionAsync(string collectionId, Asset asset, string? note = null, CancellationToken ct = default);
    Task RemoveFromCollectionAsync(string collectionId, string uid, CancellationToken ct = default);
    Task<List<LedgerEntry>> LedgerAsync(string? project = null, CancellationToken ct = default);
    Task<List<string>> ProjectsAsync(CancellationToken ct = default);
    Task<LedgerEntry> RecordAsync(Asset asset, UseCase use, string? project, string? fileUrl, CancellationToken ct = default);
    Task<string> ExportLedgerAsync(string format, string? project = null, CancellationToken ct = default);
}

public sealed class FreestashApiClient : IFreestashApi, IDisposable
{
    private readonly HttpClient _http;
    private readonly Func<string?> _token;

    public FreestashApiClient(Uri baseUri, Func<string?>? accessToken = null, HttpMessageHandler? handler = null)
    {
        BaseUri = baseUri;
        _token = accessToken ?? (() => null);
        _http = handler is null ? new HttpClient() : new HttpClient(handler);
        _http.BaseAddress = baseUri;
        _http.Timeout = Timeout.InfiniteTimeSpan; // SSE streams; per-call timeouts use CancellationTokens
        _http.DefaultRequestHeaders.UserAgent.ParseAdd("FreestashDesktop/0.1 (+https://freesta.sh)");
    }

    public Uri BaseUri { get; }

    public void Dispose() => _http.Dispose();

    private HttpRequestMessage Req(HttpMethod method, string path, object? body = null)
    {
        var msg = new HttpRequestMessage(method, path);
        if (_token() is { Length: > 0 } t) msg.Headers.Authorization = new AuthenticationHeaderValue("Bearer", t);
        if (body is not null) msg.Content = JsonContent.Create(body, options: FreestashJson.Options);
        return msg;
    }

    private static async Task Ensure(HttpResponseMessage res, CancellationToken ct)
    {
        if (res.IsSuccessStatusCode) return;
        var text = await res.Content.ReadAsStringAsync(ct);
        string message = text;
        try
        {
            using var doc = JsonDocument.Parse(text);
            if (doc.RootElement.TryGetProperty("detail", out var d))
                message = d.ValueKind == JsonValueKind.String ? d.GetString()! :
                    d.TryGetProperty("message", out var m) ? m.GetString()! : d.ToString();
        }
        catch (JsonException) { }
        throw new FreestashApiException((int)res.StatusCode, string.IsNullOrWhiteSpace(message) ? res.ReasonPhrase ?? "error" : message);
    }

    private async Task<T> Send<T>(HttpMethod method, string path, object? body, CancellationToken ct, TimeSpan? timeout = null)
    {
        using var cts = CancellationTokenSource.CreateLinkedTokenSource(ct);
        cts.CancelAfter(timeout ?? TimeSpan.FromSeconds(60));
        using var res = await _http.SendAsync(Req(method, path, body), cts.Token);
        await Ensure(res, cts.Token);
        return (await res.Content.ReadFromJsonAsync<T>(FreestashJson.Options, cts.Token))!;
    }

    private async Task SendNoContent(HttpMethod method, string path, CancellationToken ct)
    {
        using var res = await _http.SendAsync(Req(method, path), ct);
        await Ensure(res, ct);
    }

    private static string Q(string s) => Uri.EscapeDataString(s);

    public Task<HealthInfo> HealthAsync(CancellationToken ct = default) =>
        Send<HealthInfo>(HttpMethod.Get, "/api/health", null, ct, TimeSpan.FromSeconds(4));

    public Task<List<ProviderInfo>> ProvidersAsync(CancellationToken ct = default) => Send<List<ProviderInfo>>(HttpMethod.Get, "/api/providers", null, ct);

    public Task<PdCutoff> PdCutoffAsync(CancellationToken ct = default) => Send<PdCutoff>(HttpMethod.Get, "/api/pd-cutoff", null, ct);

    public static string BuildSearchQuery(SearchRequest r)
    {
        var sb = new StringBuilder($"/api/search/stream?q={Q(r.Query)}&use={r.Use.Wire()}&max_tier={r.MaxTier.Wire()}&limit={r.Limit}&page={r.Page}");
        foreach (var m in r.Media) sb.Append("&media=").Append(m.Wire());
        foreach (var p in r.Providers ?? []) sb.Append("&providers=").Append(Q(p));
        return sb.ToString();
    }

    public async IAsyncEnumerable<StreamBatch> SearchStreamAsync(SearchRequest request, [EnumeratorCancellation] CancellationToken ct = default)
    {
        using var msg = Req(HttpMethod.Get, BuildSearchQuery(request));
        msg.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("text/event-stream"));
        using var res = await _http.SendAsync(msg, HttpCompletionOption.ResponseHeadersRead, ct);
        await Ensure(res, ct);
        await using var stream = await res.Content.ReadAsStreamAsync(ct);
        await foreach (var ev in Sse.ReadAsync(stream, ct))
        {
            if (ev.Event == "done") yield break;
            if (ev.Event == "batch" && JsonSerializer.Deserialize<StreamBatch>(ev.Data, FreestashJson.Options) is { } batch)
                yield return batch;
        }
    }

    public Task<AssetDetail> AssetAsync(string uid, UseCase use, CancellationToken ct = default) =>
        Send<AssetDetail>(HttpMethod.Get, $"/api/assets/{Q(uid)}?use={use.Wire()}", null, ct, TimeSpan.FromSeconds(45));

    public Task<LicenseCheckResult> CheckLicenseAsync(string license, Trust trust, MediaType media, int? year, CancellationToken ct = default) =>
        Send<LicenseCheckResult>(HttpMethod.Post, "/api/license/check", new { license, trust, media_type = media, year }, ct);

    public Task<List<Collection>> CollectionsAsync(CancellationToken ct = default) => Send<List<Collection>>(HttpMethod.Get, "/api/collections", null, ct);

    public Task<Collection> CollectionAsync(string id, CancellationToken ct = default) => Send<Collection>(HttpMethod.Get, $"/api/collections/{Q(id)}", null, ct);

    public Task<Collection> CreateCollectionAsync(string name, UseCase use, string? description = null, CancellationToken ct = default) =>
        Send<Collection>(HttpMethod.Post, "/api/collections", new { name, use_case = use, description }, ct);

    public Task DeleteCollectionAsync(string id, CancellationToken ct = default) => SendNoContent(HttpMethod.Delete, $"/api/collections/{Q(id)}", ct);

    public Task<Collection> AddToCollectionAsync(string collectionId, Asset asset, string? note = null, CancellationToken ct = default) =>
        Send<Collection>(HttpMethod.Post, $"/api/collections/{Q(collectionId)}/items", new { uid = asset.Uid, asset, note }, ct);

    public Task RemoveFromCollectionAsync(string collectionId, string uid, CancellationToken ct = default) =>
        SendNoContent(HttpMethod.Delete, $"/api/collections/{Q(collectionId)}/items/{Q(uid)}", ct);

    public Task<List<LedgerEntry>> LedgerAsync(string? project = null, CancellationToken ct = default) =>
        Send<List<LedgerEntry>>(HttpMethod.Get, project is null ? "/api/ledger" : $"/api/ledger?project={Q(project)}", null, ct);

    public Task<List<string>> ProjectsAsync(CancellationToken ct = default) => Send<List<string>>(HttpMethod.Get, "/api/ledger/projects", null, ct);

    public Task<LedgerEntry> RecordAsync(Asset asset, UseCase use, string? project, string? fileUrl, CancellationToken ct = default) =>
        Send<LedgerEntry>(HttpMethod.Post, "/api/ledger", new { uid = asset.Uid, asset, use_case = use, project, file_url = fileUrl }, ct);

    public async Task<string> ExportLedgerAsync(string format, string? project = null, CancellationToken ct = default)
    {
        var path = $"/api/ledger/export?format={Q(format)}" + (project is null ? "" : $"&project={Q(project)}");
        using var res = await _http.SendAsync(Req(HttpMethod.Get, path), ct);
        await Ensure(res, ct);
        return await res.Content.ReadAsStringAsync(ct);
    }
}
