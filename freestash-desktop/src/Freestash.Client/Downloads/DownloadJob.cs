using System.ComponentModel;
using System.Runtime.CompilerServices;

namespace Freestash.Client.Downloads;

public enum DownloadStatus { Queued, Downloading, Paused, Completed, Failed, Blocked, Canceled }

/// <summary>
/// One download. Observable so the UI can bind directly; all mutation happens through the engine.
/// A job either carries a Freestash asset (gets a .license.json sidecar + ledger entry) or is a plain pasted link.
/// </summary>
public sealed class DownloadJob : INotifyPropertyChanged
{
    public DownloadJob(Uri url, string destinationDirectory, string? fileName = null)
    {
        Url = url;
        DestinationDirectory = destinationDirectory;
        FileName = fileName ?? FileNames.FromUrl(url);
    }

    public Guid Id { get; } = Guid.NewGuid();
    public Uri Url { get; }
    public string DestinationDirectory { get; }
    public DateTimeOffset AddedAt { get; } = DateTimeOffset.Now;

    // Freestash metadata (null for pasted links)
    public ScoredAsset? Asset { get; init; }
    public Rendition? Rendition { get; init; }
    public UseCase UseCase { get; init; } = UseCase.Demo;
    public string? Project { get; init; }
    public bool IsFreestashAsset => Asset is not null;
    public string SourceLabel => Asset is null ? Url.Host : Asset.Asset.SourceName ?? Asset.Asset.Provider;
    public string? LandingUrl => Asset?.Asset.LandingUrl;

    public string FileName { get => _fileName; internal set => Set(ref _fileName, value); }
    public DownloadStatus Status
    {
        get => _status;
        internal set
        {
            if (!Set(ref _status, value)) return;
            OnChanged(nameof(IsActive)); OnChanged(nameof(CanPause)); OnChanged(nameof(CanResume));
            OnChanged(nameof(CanRetry)); OnChanged(nameof(IsDone)); OnChanged(nameof(StatusText));
            OnChanged(nameof(ProgressText)); OnChanged(nameof(IsIndeterminate));
        }
    }
    public long BytesReceived { get => _received; internal set { if (Set(ref _received, value)) { OnChanged(nameof(Progress)); OnChanged(nameof(ProgressText)); } } }
    public long? TotalBytes { get => _total; internal set { if (Set(ref _total, value)) { OnChanged(nameof(Progress)); OnChanged(nameof(ProgressText)); } } }
    public double SpeedBytesPerSecond { get => _speed; internal set { if (Set(ref _speed, value)) OnChanged(nameof(ProgressText)); } }
    public string? Error { get => _error; internal set { if (Set(ref _error, value)) OnChanged(nameof(StatusText)); } }
    public string? LocalPath { get => _localPath; internal set => Set(ref _localPath, value); }
    public string? SidecarPath { get => _sidecar; internal set => Set(ref _sidecar, value); }
    public string? Sha256 { get; internal set; }
    public bool Recorded { get => _recorded; internal set => Set(ref _recorded, value); }

    /// <summary>Called by the app after the ledger accepted this download.</summary>
    public void MarkRecorded() => Recorded = true;

    public double Progress => TotalBytes is > 0 ? Math.Clamp((double)BytesReceived / TotalBytes.Value, 0, 1) : 0;
    public bool IsIndeterminate => Status == DownloadStatus.Downloading && TotalBytes is null or 0;
    public bool IsActive => Status is DownloadStatus.Downloading or DownloadStatus.Queued;
    public bool IsDone => Status == DownloadStatus.Completed;
    public bool CanPause => Status is DownloadStatus.Downloading or DownloadStatus.Queued;
    public bool CanResume => Status == DownloadStatus.Paused;
    public bool CanRetry => Status is DownloadStatus.Failed or DownloadStatus.Canceled or DownloadStatus.Blocked;

    public string ProgressText => Status switch
    {
        DownloadStatus.Completed => Formatting.Bytes(BytesReceived),
        _ when TotalBytes is > 0 => $"{Formatting.Bytes(BytesReceived)} / {Formatting.Bytes(TotalBytes)}  {Formatting.Speed(SpeedBytesPerSecond)}",
        _ => $"{Formatting.Bytes(BytesReceived)}  {Formatting.Speed(SpeedBytesPerSecond)}",
    };

    public string StatusText => Status switch
    {
        DownloadStatus.Blocked => "Host blocked automated download",
        DownloadStatus.Failed => Error ?? "Failed",
        _ => Status.ToString(),
    };

    internal CancellationTokenSource? Cts;
    internal bool PauseRequested;

    private string _fileName = "";
    private DownloadStatus _status = DownloadStatus.Queued;
    private long _received;
    private long? _total;
    private double _speed;
    private string? _error;
    private string? _localPath;
    private string? _sidecar;
    private bool _recorded;

    public event PropertyChangedEventHandler? PropertyChanged;

    /// <summary>The engine raises change notifications on whatever thread it runs; the UI layer marshals.</summary>
    internal void OnChanged([CallerMemberName] string? name = null) => PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));

    private bool Set<T>(ref T field, T value, [CallerMemberName] string? name = null)
    {
        if (EqualityComparer<T>.Default.Equals(field, value)) return false;
        field = value;
        OnChanged(name);
        return true;
    }
}
