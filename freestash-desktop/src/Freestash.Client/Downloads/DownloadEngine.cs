using System.Diagnostics;
using System.Net;
using System.Security.Cryptography;

namespace Freestash.Client.Downloads;

public sealed class DownloadEngineOptions
{
    public int MaxConcurrent { get; set; } = 3;
    public bool WriteSidecars { get; set; } = true;
    public long MaxBytes { get; set; } = 2L * 1024 * 1024 * 1024;
    public string UserAgent { get; set; } = "FreestashDesktop/0.1 (+https://freesta.sh; internal asset finder)";
}

/// <summary>
/// Download queue: bounded concurrency, pause/resume via HTTP Range, retry, SHA-256 while streaming,
/// atomic .part → final rename, .license.json sidecars for Freestash assets.
///
/// Hosts that refuse automated downloads (401/403/429) become <see cref="DownloadStatus.Blocked"/>; the UI
/// offers "Open in browser". The engine never retries those with a different identity. That's a hard rule.
/// </summary>
public sealed class DownloadEngine : IDisposable
{
    private readonly HttpClient _http;
    private readonly DownloadEngineOptions _options;
    private readonly List<DownloadJob> _jobs = [];
    private readonly object _gate = new();
    private SemaphoreSlim _slots;

    public DownloadEngine(DownloadEngineOptions? options = null, HttpMessageHandler? handler = null)
    {
        _options = options ?? new DownloadEngineOptions();
        _slots = new SemaphoreSlim(_options.MaxConcurrent);
        _http = handler is null ? new HttpClient(new SocketsHttpHandler { AutomaticDecompression = DecompressionMethods.None })
                                : new HttpClient(handler);
        _http.Timeout = Timeout.InfiniteTimeSpan;
        _http.DefaultRequestHeaders.UserAgent.ParseAdd(_options.UserAgent);
    }

    /// <summary>Raised on the engine's thread when a job is added.</summary>
    public event Action<DownloadJob>? JobAdded;

    /// <summary>Raised when a Freestash-asset job completes, so the app can record it in the ledger.</summary>
    public event Func<DownloadJob, Task>? AssetCompleted;

    public IReadOnlyList<DownloadJob> Jobs { get { lock (_gate) return _jobs.ToList(); } }

    public int MaxConcurrent
    {
        get => _options.MaxConcurrent;
        set
        {
            if (value < 1 || value == _options.MaxConcurrent) return;
            _options.MaxConcurrent = value;
            _slots = new SemaphoreSlim(value); // applies to jobs started from now on
        }
    }

    public bool WriteSidecars { get => _options.WriteSidecars; set => _options.WriteSidecars = value; }

    public DownloadJob Enqueue(DownloadJob job)
    {
        lock (_gate) _jobs.Add(job);
        JobAdded?.Invoke(job);
        Start(job);
        return job;
    }

    public void Pause(DownloadJob job)
    {
        if (!job.CanPause) return;
        job.PauseRequested = true;
        job.Cts?.Cancel();
        if (job.Status == DownloadStatus.Queued) job.Status = DownloadStatus.Paused;
    }

    public void Resume(DownloadJob job)
    {
        if (!job.CanResume) return;
        Start(job);
    }

    public void Retry(DownloadJob job)
    {
        if (!job.CanRetry) return;
        job.Error = null;
        Start(job);
    }

    public void Cancel(DownloadJob job)
    {
        job.PauseRequested = false;
        job.Cts?.Cancel();
        if (job.Status is DownloadStatus.Queued or DownloadStatus.Paused) MarkCanceled(job);
    }

    public void Remove(DownloadJob job)
    {
        Cancel(job);
        lock (_gate) _jobs.Remove(job);
    }

    public void ClearFinished()
    {
        lock (_gate) _jobs.RemoveAll(j => j.Status is DownloadStatus.Completed or DownloadStatus.Canceled);
    }

    private void Start(DownloadJob job)
    {
        job.PauseRequested = false;
        job.Cts = new CancellationTokenSource();
        job.Status = DownloadStatus.Queued;
        _ = Task.Run(() => RunAsync(job, job.Cts.Token));
    }

    private static void MarkCanceled(DownloadJob job)
    {
        job.Status = DownloadStatus.Canceled;
        var part = PartPath(job);
        if (part is not null) TryDelete(part);
    }

    private static string? PartPath(DownloadJob job) =>
        string.IsNullOrEmpty(job.FileName) ? null : Path.Combine(job.DestinationDirectory, job.FileName + ".part");

    private async Task RunAsync(DownloadJob job, CancellationToken ct)
    {
        var slots = _slots;
        try
        {
            await slots.WaitAsync(ct);
        }
        catch (OperationCanceledException)
        {
            if (job.PauseRequested) job.Status = DownloadStatus.Paused; else MarkCanceled(job);
            return;
        }

        try
        {
            job.Status = DownloadStatus.Downloading;
            Directory.CreateDirectory(job.DestinationDirectory);
            await DownloadAsync(job, ct);
        }
        catch (OperationCanceledException)
        {
            if (job.PauseRequested) job.Status = DownloadStatus.Paused; else MarkCanceled(job);
        }
        catch (BlockedException ex)
        {
            job.Error = ex.Message;
            job.Status = DownloadStatus.Blocked;
        }
        catch (Exception ex)
        {
            job.Error = ex.Message;
            job.Status = DownloadStatus.Failed;
        }
        finally
        {
            job.SpeedBytesPerSecond = 0;
            slots.Release();
        }
    }

    private async Task DownloadAsync(DownloadJob job, CancellationToken ct)
    {
        var part = PartPath(job)!;
        long existing = File.Exists(part) ? new FileInfo(part).Length : 0;

        using var req = new HttpRequestMessage(HttpMethod.Get, job.Url);
        req.Headers.Accept.ParseAdd("*/*");
        if (existing > 0) req.Headers.Range = new System.Net.Http.Headers.RangeHeaderValue(existing, null);

        using var res = await _http.SendAsync(req, HttpCompletionOption.ResponseHeadersRead, ct);
        if (res.StatusCode is HttpStatusCode.Unauthorized or HttpStatusCode.Forbidden or HttpStatusCode.TooManyRequests)
            throw new BlockedException($"{job.Url.Host} refused the download (HTTP {(int)res.StatusCode}). Open it in your browser instead.");
        if (res.StatusCode == HttpStatusCode.RequestedRangeNotSatisfiable && existing > 0)
        {
            TryDelete(part);
            throw new IOException("Server rejected resume; retry to start over.");
        }
        res.EnsureSuccessStatusCode();

        // First response decides the final file name (Content-Disposition beats URL guessing).
        if (existing == 0 && res.Content.Headers.ContentDisposition is { } cd &&
            FileNames.Sanitize(cd.FileNameStar ?? cd.FileName?.Trim('"')) is { Length: > 0 } dispName && !job.IsFreestashAsset)
        {
            job.FileName = dispName;
            part = PartPath(job)!;
        }
        else if (existing == 0 && Path.GetExtension(job.FileName) is "" && res.Content.Headers.ContentType?.MediaType is { } mime)
        {
            job.FileName += FileNames.ExtensionForMime(mime);
            part = PartPath(job)!;
        }

        bool resumed = existing > 0 && res.StatusCode == HttpStatusCode.PartialContent;
        if (!resumed) existing = 0;
        long? length = res.Content.Headers.ContentLength;
        job.TotalBytes = length is null ? null : length + existing;
        if (job.TotalBytes > _options.MaxBytes)
            throw new IOException($"File is {Formatting.Bytes(job.TotalBytes)}, above the {Formatting.Bytes(_options.MaxBytes)} limit.");

        await using (var input = await res.Content.ReadAsStreamAsync(ct))
        await using (var output = new FileStream(part, resumed ? FileMode.Append : FileMode.Create, FileAccess.Write, FileShare.None, 1 << 16, useAsync: true))
        {
            var buffer = new byte[1 << 16];
            long received = existing;
            var clock = Stopwatch.StartNew();
            long windowBytes = 0;
            int read;
            while ((read = await input.ReadAsync(buffer, ct)) > 0)
            {
                await output.WriteAsync(buffer.AsMemory(0, read), ct);
                received += read;
                windowBytes += read;
                if (received > _options.MaxBytes) throw new IOException("Download exceeded the size limit.");
                if (clock.ElapsedMilliseconds >= 250)
                {
                    job.SpeedBytesPerSecond = windowBytes / clock.Elapsed.TotalSeconds;
                    job.BytesReceived = received;
                    windowBytes = 0;
                    clock.Restart();
                }
            }
            job.BytesReceived = received;
        }

        var final = FileNames.Unique(Path.Combine(job.DestinationDirectory, job.FileName));
        File.Move(part, final);
        job.FileName = Path.GetFileName(final);
        job.LocalPath = final;
        job.Sha256 = await HashFileAsync(final, ct);

        if (job.Asset is not null && _options.WriteSidecars)
            job.SidecarPath = await Sidecar.WriteAsync(job, ct);

        job.Status = DownloadStatus.Completed;

        if (job.Asset is not null && AssetCompleted is { } handler)
        {
            try { await handler(job); } catch { /* recording failures surface in the UI via the handler */ }
        }
    }

    internal static async Task<string> HashFileAsync(string path, CancellationToken ct)
    {
        await using var fs = File.OpenRead(path);
        var hash = await SHA256.HashDataAsync(fs, ct);
        return Convert.ToHexStringLower(hash);
    }

    private static void TryDelete(string path)
    {
        try { File.Delete(path); } catch (IOException) { } catch (UnauthorizedAccessException) { }
    }

    public void Dispose()
    {
        foreach (var j in Jobs) j.Cts?.Cancel();
        _http.Dispose();
    }

    private sealed class BlockedException(string message) : Exception(message);
}
