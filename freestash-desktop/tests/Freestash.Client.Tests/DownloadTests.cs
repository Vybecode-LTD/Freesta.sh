using System.Net;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text.Json;
using Freestash.Client.Downloads;

namespace Freestash.Client.Tests;

public class DownloadTests : IDisposable
{
    private readonly string _dir = Path.Combine(Path.GetTempPath(), "freestash-dl-" + Guid.NewGuid().ToString("N"));

    public void Dispose()
    {
        try { Directory.Delete(_dir, true); } catch (DirectoryNotFoundException) { }
    }

    private static async Task WaitFor(DownloadJob job, Func<DownloadJob, bool> done, int ms = 10_000)
    {
        var sw = System.Diagnostics.Stopwatch.StartNew();
        while (!done(job))
        {
            if (sw.ElapsedMilliseconds > ms) throw new TimeoutException($"job stuck in {job.Status}: {job.Error}");
            await Task.Delay(20);
        }
    }

    [Fact]
    public async Task Plain_link_downloads_with_content_disposition_name_and_hash()
    {
        var payload = RandomNumberGenerator.GetBytes(300_000);
        var handler = new StubHandler(_ =>
        {
            var res = new HttpResponseMessage(HttpStatusCode.OK) { Content = new ByteArrayContent(payload) };
            res.Content.Headers.ContentDisposition = new ContentDispositionHeaderValue("attachment") { FileName = "\"Grand Piano C4.wav\"" };
            res.Content.Headers.ContentType = new MediaTypeHeaderValue("audio/wav");
            return res;
        });
        using var engine = new DownloadEngine(handler: handler);
        var job = engine.Enqueue(new DownloadJob(new Uri("https://example.org/get?id=42"), _dir));
        await WaitFor(job, j => j.Status is DownloadStatus.Completed or DownloadStatus.Failed);

        Assert.Equal(DownloadStatus.Completed, job.Status);
        Assert.Equal("Grand Piano C4.wav", job.FileName);
        Assert.Equal(payload, await File.ReadAllBytesAsync(job.LocalPath!, TestContext.Current.CancellationToken));
        Assert.Equal(Convert.ToHexStringLower(SHA256.HashData(payload)), job.Sha256);
        Assert.Null(job.SidecarPath); // plain links get no sidecar
        Assert.False(File.Exists(job.LocalPath + ".part"));
    }

    [Theory]
    [InlineData(HttpStatusCode.Forbidden)]
    [InlineData(HttpStatusCode.TooManyRequests)]
    public async Task Refused_downloads_become_blocked_not_failed(HttpStatusCode code)
    {
        using var engine = new DownloadEngine(handler: new StubHandler(_ => new HttpResponseMessage(code)));
        var job = engine.Enqueue(new DownloadJob(new Uri("https://www.artic.edu/iiif/2/x/full/843,/0/default.jpg"), _dir));
        await WaitFor(job, j => j.Status is DownloadStatus.Blocked or DownloadStatus.Failed);
        Assert.Equal(DownloadStatus.Blocked, job.Status);
        Assert.Contains("browser", job.Error);
        Assert.True(job.CanRetry);
    }

    [Fact]
    public async Task Freestash_asset_gets_sidecar_and_ledger_callback()
    {
        var detail = JsonSerializer.Deserialize<AssetDetail>(
            File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "Samples", "asset_detail.json")), FreestashJson.Options)!;
        var rendition = detail.Asset.Renditions[0];
        var handler = new StubHandler(_ => new HttpResponseMessage(HttpStatusCode.OK) { Content = new ByteArrayContent([0xFF, 0xD8, 1, 2, 3]) });
        using var engine = new DownloadEngine(handler: handler);
        DownloadJob? recorded = null;
        engine.AssetCompleted += j => { recorded = j; return Task.CompletedTask; };

        var job = engine.Enqueue(new DownloadJob(new Uri(rendition.Url), _dir, FileNames.ForAsset(detail.Asset, rendition))
        {
            Asset = new ScoredAsset(detail.Uid, detail.Asset, detail.Verdict), Rendition = rendition,
            UseCase = UseCase.Bundled, Project = "aurora",
        });
        await WaitFor(job, j => j.Status is DownloadStatus.Completed or DownloadStatus.Failed);

        Assert.Equal(DownloadStatus.Completed, job.Status);
        Assert.Same(job, recorded);
        Assert.StartsWith("lighthouse-village", job.FileName);
        var side = JsonDocument.Parse(await File.ReadAllTextAsync(job.SidecarPath!, TestContext.Current.CancellationToken)).RootElement;
        Assert.Equal(1, side.GetProperty("freestash_sidecar").GetInt32());
        Assert.Equal("CC0-1.0", side.GetProperty("license").GetProperty("id").GetString());
        Assert.Equal("bundled", side.GetProperty("use_case").GetString());
        Assert.Equal(job.Sha256, side.GetProperty("sha256").GetString());
        Assert.Equal(1, side.GetProperty("asset").GetProperty("renditions").GetArrayLength());
    }

    [Fact]
    public async Task Pause_then_resume_uses_range_request()
    {
        var payload = RandomNumberGenerator.GetBytes(64 * 1024 * 8);
        var gate = new SemaphoreSlim(0);
        var handler = new StubHandler(req =>
        {
            var from = req.Headers.Range?.Ranges.First().From ?? 0;
            var body = payload[(int)from..];
            HttpContent content = from == 0 ? new StreamContent(new SlowStream(body, gate)) : new ByteArrayContent(body);
            var res = new HttpResponseMessage(from == 0 ? HttpStatusCode.OK : HttpStatusCode.PartialContent) { Content = content };
            res.Content.Headers.ContentLength = body.Length;
            return res;
        });
        using var engine = new DownloadEngine(handler: handler);
        var job = engine.Enqueue(new DownloadJob(new Uri("https://example.org/big.bin"), _dir));
        await WaitFor(job, j => j.Status == DownloadStatus.Downloading);
        gate.Release(2); // let two chunks through
        await Task.Delay(150, TestContext.Current.CancellationToken);
        engine.Pause(job);
        await WaitFor(job, j => j.Status == DownloadStatus.Paused);
        var partial = new FileInfo(Path.Combine(_dir, "big.bin.part")).Length;
        Assert.InRange(partial, 1, payload.Length - 1);

        engine.Resume(job);
        await WaitFor(job, j => j.Status is DownloadStatus.Completed or DownloadStatus.Failed);
        Assert.Equal(DownloadStatus.Completed, job.Status);
        Assert.Equal(payload, await File.ReadAllBytesAsync(job.LocalPath!, TestContext.Current.CancellationToken));
        Assert.Contains(handler.Requests, r => r.Headers.Range is not null);
    }

    [Fact]
    public void Link_parser_handles_messy_paste()
    {
        var text = """
            Here you go: https://ambientcg.com/get?file=Wood096_1K-JPG.zip,
            [poster](https://example.org/a%20b.png) and <https://example.org/x.jpg>.
            dupe https://ambientcg.com/get?file=Wood096_1K-JPG.zip
            ftp://nope.example/file and (https://en.wikipedia.org/wiki/Lighthouse_(disambiguation))
            """;
        var links = LinkParser.Extract(text).Select(u => u.AbsoluteUri).ToList();
        Assert.Equal(
        [
            "https://ambientcg.com/get?file=Wood096_1K-JPG.zip",
            "https://example.org/a%20b.png",
            "https://example.org/x.jpg",
            "https://en.wikipedia.org/wiki/Lighthouse_(disambiguation)",
        ], links);
    }

    [Theory]
    [InlineData("https://ambientcg.com/get?file=Wood096_1K-JPG.zip", "Wood096_1K-JPG.zip")]
    [InlineData("https://example.org/path/My%20Track.wav", "My Track.wav")]
    [InlineData("https://example.org/CON.txt", "_CON.txt")]
    public void File_names_are_safe(string url, string expected) => Assert.Equal(expected, FileNames.FromUrl(new Uri(url)));

    [Fact]
    public void Unique_appends_counter()
    {
        Directory.CreateDirectory(_dir);
        var p = Path.Combine(_dir, "a.jpg");
        File.WriteAllText(p, "x");
        Assert.Equal(Path.Combine(_dir, "a (2).jpg"), FileNames.Unique(p));
    }
}

/// <summary>Yields one 64 KB chunk per gate release so a test can pause mid-stream.</summary>
internal sealed class SlowStream(byte[] data, SemaphoreSlim gate) : Stream
{
    private int _pos;
    public override async ValueTask<int> ReadAsync(Memory<byte> buffer, CancellationToken ct = default)
    {
        if (_pos >= data.Length) return 0;
        await gate.WaitAsync(ct);
        var n = Math.Min(Math.Min(buffer.Length, 64 * 1024), data.Length - _pos);
        data.AsMemory(_pos, n).CopyTo(buffer);
        _pos += n;
        return n;
    }
    public override int Read(byte[] buffer, int offset, int count) => ReadAsync(buffer.AsMemory(offset, count)).AsTask().GetAwaiter().GetResult();
    public override bool CanRead => true;
    public override bool CanSeek => false;
    public override bool CanWrite => false;
    public override long Length => data.Length;
    public override long Position { get => _pos; set => throw new NotSupportedException(); }
    public override void Flush() { }
    public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
    public override void SetLength(long value) => throw new NotSupportedException();
    public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();
}
