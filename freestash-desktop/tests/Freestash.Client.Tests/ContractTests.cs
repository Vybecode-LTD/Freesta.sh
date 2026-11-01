using System.Net;
using System.Text;
using System.Text.Json;

namespace Freestash.Client.Tests;

/// <summary>Samples/ were produced by the real Python API (FastAPI TestClient + recorded fixtures). Regenerate them when the contract changes.</summary>
public class ContractTests
{
    private static string Sample(string name) => File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "Samples", name));

    [Fact]
    public async Task Sse_stream_parses_batches_and_done()
    {
        await using var stream = new MemoryStream(Encoding.UTF8.GetBytes(Sample("search_stream.txt")));
        var events = new List<SseEvent>();
        await foreach (var e in Sse.ReadAsync(stream, TestContext.Current.CancellationToken)) events.Add(e);
        Assert.Contains(events, e => e.Event == "done");
        var batches = events.Where(e => e.Event == "batch").Select(e => JsonSerializer.Deserialize<StreamBatch>(e.Data, FreestashJson.Options)!).ToList();
        Assert.Equal(2, batches.Count);
        var first = batches.SelectMany(b => b.Results).First();
        Assert.Equal(Tier.Green, first.Verdict.Tier);
        Assert.Equal(UseCase.Bundled, first.Verdict.UseCase);
        Assert.Equal(Trust.Institution, first.Asset.Trust);
        Assert.Equal(MediaType.Image, first.Asset.MediaType);
        Assert.NotEmpty(first.Asset.Renditions);
    }

    [Fact]
    public void Sse_handles_multiline_data_comments_and_crlf()
    {
        var raw = ": keep-alive\r\nevent: batch\r\ndata: {\"a\":\r\ndata: 1}\r\n\r\nevent: done\r\ndata: {}\r\n\r\n";
        var events = Sse.ReadAsync(new MemoryStream(Encoding.UTF8.GetBytes(raw)), TestContext.Current.CancellationToken).ToBlockingEnumerable(TestContext.Current.CancellationToken).ToList();
        Assert.Equal("batch", events[0].Event);
        Assert.Equal("{\"a\":\n1}", events[0].Data);
        Assert.Equal("done", events[1].Event);
    }

    [Fact]
    public void Asset_detail_has_all_five_verdicts()
    {
        var d = JsonSerializer.Deserialize<AssetDetail>(Sample("asset_detail.json"), FreestashJson.Options)!;
        Assert.Equal(5, d.Verdicts.Count);
        Assert.Contains("bundled", d.Verdicts.Keys);
        Assert.StartsWith("&ldquo;", d.AttributionHtml);
        Assert.Equal(d.Uid, d.Asset.Uid);
    }

    [Fact]
    public void Providers_collection_ledger_license_and_health_deserialize()
    {
        var providers = JsonSerializer.Deserialize<List<ProviderInfo>>(Sample("providers.json"), FreestashJson.Options)!;
        Assert.Contains(providers, p => p.Id == "polyhaven" && p.MediaTypes.Contains("hdri"));
        Assert.Contains(providers, p => p.Id == "unsplash" && p.KeySetting == "unsplash_access_key");

        var coll = JsonSerializer.Deserialize<Collection>(Sample("collection.json"), FreestashJson.Options)!;
        Assert.Equal(UseCase.Bundled, coll.UseCase);
        Assert.Single(coll.Items!);

        var ledger = JsonSerializer.Deserialize<List<LedgerEntry>>(Sample("ledger.json"), FreestashJson.Options)!;
        Assert.Equal("aurora", ledger[0].Project);

        var check = JsonSerializer.Deserialize<LicenseCheckResult>(Sample("license_check.json"), FreestashJson.Options)!;
        Assert.Equal("UNSPLASH", check.RecognizedAs.Id);
        Assert.Equal(Tier.Red, check.Verdicts["bundled"].Tier);

        var health = JsonSerializer.Deserialize<HealthInfo>(Sample("health.json"), FreestashJson.Options)!;
        Assert.True(health.Ok);
        Assert.Equal("none", health.AuthMode);
    }

    [Fact]
    public void Search_query_string_matches_the_api()
    {
        var q = FreestashApiClient.BuildSearchQuery(new SearchRequest("brutalist concrete", [MediaType.Image, MediaType.Hdri], UseCase.Bundled, Tier.Green, ["met", "polyhaven"], 8));
        Assert.Equal("/api/search/stream?q=brutalist%20concrete&use=bundled&max_tier=green&limit=8&page=1&media=image&media=hdri&providers=met&providers=polyhaven", q);
    }

    [Fact]
    public async Task Ledger_pages_past_the_first_page_with_the_servers_cursor()
    {
        // The ledger stopped at the newest 500 entries (PR #1 review); the web pages it the same way (ledgerPages.ts).
        Assert.Equal("/api/ledger?limit=100", FreestashApiClient.BuildLedgerPath(null, null));
        Assert.Equal("/api/ledger?project=tpl%2001&before=e99&limit=100", FreestashApiClient.BuildLedgerPath("tpl 01", "e99"));

        var page = Enumerable.Range(0, LedgerPages.Size).Select(i => Entry($"e{i}")).ToList();
        Assert.Equal($"e{LedgerPages.Size - 1}", LedgerPages.NextCursor(page));
        Assert.Null(LedgerPages.NextCursor(page[..^1]));

        var handler = new StubHandler(_ => new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent("[]", Encoding.UTF8, "application/json") });
        using var api = new FreestashApiClient(new Uri("http://localhost:8787"), () => "t0ken", handler);
        Assert.Empty(await api.LedgerAsync("p", "e99", ct: TestContext.Current.CancellationToken));
        Assert.Equal("/api/ledger?project=p&before=e99&limit=100", Assert.Single(handler.Requests).RequestUri!.PathAndQuery);
    }

    private static LedgerEntry Entry(string id) => new(id, "met:1", "met", "Title", null, null, null, "CC0-1.0", "CC0 1.0", null,
                                                        Trust.Institution, UseCase.Demo, Tier.Green, null, null, "2026-11-01T00:00:00Z");

    [Fact]
    public async Task Client_sends_bearer_token_and_surfaces_api_errors()
    {
        var handler = new StubHandler(req =>
        {
            Assert.Equal("Bearer t0ken", req.Headers.Authorization?.ToString());
            return new HttpResponseMessage(HttpStatusCode.Conflict)
            {
                Content = new StringContent("{\"detail\":{\"message\":\"RED for this use case\",\"reasons\":[\"x\"]}}", Encoding.UTF8, "application/json"),
            };
        });
        using var api = new FreestashApiClient(new Uri("http://localhost:8787"), () => "t0ken", handler);
        var asset = JsonSerializer.Deserialize<AssetDetail>(Sample("asset_detail.json"), FreestashJson.Options)!.Asset;
        var ex = await Assert.ThrowsAsync<FreestashApiException>(() => api.RecordAsync(asset, UseCase.Bundled, "p", null, TestContext.Current.CancellationToken));
        Assert.Equal(409, ex.Status);
        Assert.Equal("RED for this use case", ex.Message);
    }
}

internal sealed class StubHandler(Func<HttpRequestMessage, HttpResponseMessage> respond) : HttpMessageHandler
{
    public List<HttpRequestMessage> Requests { get; } = [];

    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        Requests.Add(request);
        return Task.FromResult(respond(request));
    }
}
