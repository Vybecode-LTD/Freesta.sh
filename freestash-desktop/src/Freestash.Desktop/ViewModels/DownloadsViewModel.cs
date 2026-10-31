using System.Collections.ObjectModel;
using System.ComponentModel;
using Avalonia.Threading;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Freestash.Client;
using Freestash.Client.Downloads;
using Freestash.Desktop.Services;

namespace Freestash.Desktop.ViewModels;

/// <summary>UI-thread mirror of a DownloadJob (the engine updates jobs from worker threads).</summary>
public sealed class DownloadItemViewModel : ObservableObject
{
    public DownloadItemViewModel(DownloadJob job)
    {
        Job = job;
        job.PropertyChanged += OnJobChanged;
    }

    public DownloadJob Job { get; }

    public string FileName => Job.FileName;
    public string SourceLabel => Job.SourceLabel;
    public string Destination => Job.DestinationDirectory;
    public double Progress => Job.Progress * 100;
    public bool IsIndeterminate => Job.IsIndeterminate;
    public string ProgressText => Job.ProgressText;
    public string StatusText => Job.StatusText;
    public DownloadStatus Status => Job.Status;
    public bool CanPause => Job.CanPause;
    public bool CanResume => Job.CanResume;
    public bool CanRetry => Job.CanRetry;
    public bool IsDone => Job.IsDone;
    public bool IsBlocked => Job.Status == DownloadStatus.Blocked;
    public bool IsFailed => Job.Status == DownloadStatus.Failed;
    public bool IsActive => Job.IsActive;
    public bool ShowProgress => Job.Status is DownloadStatus.Downloading or DownloadStatus.Paused or DownloadStatus.Queued;
    public bool IsFreestashAsset => Job.IsFreestashAsset;
    public bool HasSidecar => Job.SidecarPath is not null;
    public bool Recorded => Job.Recorded;
    public string? BrowserUrl => Job.LandingUrl ?? Job.Url.AbsoluteUri;
    public string KindIcon => Path.GetExtension(Job.FileName).ToLowerInvariant() switch
    {
        ".wav" or ".mp3" or ".flac" or ".ogg" or ".m4a" or ".aif" or ".aiff" => "IconWave",
        ".mp4" or ".mov" or ".webm" or ".mkv" => "IconVideo",
        ".zip" or ".blend" or ".gltf" or ".glb" or ".fbx" or ".exr" or ".hdr" => "IconCube",
        ".ttf" or ".otf" or ".woff" or ".woff2" => "IconType",
        ".jpg" or ".jpeg" or ".png" or ".webp" or ".gif" or ".tif" or ".tiff" or ".svg" => "IconImage",
        _ => "IconFile",
    };
    public string StatusClass => Job.Status switch
    {
        DownloadStatus.Completed => "green",
        DownloadStatus.Blocked or DownloadStatus.Paused => "yellow",
        DownloadStatus.Failed or DownloadStatus.Canceled => "red",
        _ => "",
    };
    public bool StatusGreen => StatusClass == "green";
    public bool StatusYellow => StatusClass == "yellow";
    public bool StatusRed => StatusClass == "red";

    private void OnJobChanged(object? sender, PropertyChangedEventArgs e) => Dispatcher.UIThread.Post(() =>
    {
        OnPropertyChanged(e.PropertyName);
        switch (e.PropertyName)
        {
            case nameof(DownloadJob.Progress): OnPropertyChanged(nameof(IsIndeterminate)); break;
            case nameof(DownloadJob.Status):
                foreach (var n in new[] { nameof(IsBlocked), nameof(IsFailed), nameof(ShowProgress), nameof(IsIndeterminate), nameof(StatusClass),
                                          nameof(StatusGreen), nameof(StatusYellow), nameof(StatusRed), nameof(HasSidecar), nameof(Progress) })
                    OnPropertyChanged(n);
                break;
            case nameof(DownloadJob.SidecarPath): OnPropertyChanged(nameof(HasSidecar)); break;
            case nameof(DownloadJob.FileName): OnPropertyChanged(nameof(KindIcon)); break;
        }
    });
}

public sealed partial class DownloadsViewModel : ViewModelBase
{
    private readonly AppServices _services;
    private readonly DispatcherTimer _clipboardTimer;
    private string? _lastClipboard;

    public DownloadsViewModel(AppServices services)
    {
        _services = services;
        Destination = services.Settings.DownloadDirectory;
        WatchClipboard = services.Settings.WatchClipboard;
        services.Downloads.JobAdded += job => Dispatcher.UIThread.Post(() =>
        {
            var item = new DownloadItemViewModel(job);
            item.PropertyChanged += (_, e) => { if (e.PropertyName == nameof(DownloadItemViewModel.Status)) Refresh(); };
            Items.Insert(0, item);
            Refresh();
        });
        _clipboardTimer = new DispatcherTimer(TimeSpan.FromSeconds(1.5), DispatcherPriority.Background, async (_, _) => await PollClipboardAsync());
        if (WatchClipboard) _clipboardTimer.Start();
    }

    public ObservableCollection<DownloadItemViewModel> Items { get; } = [];

    [ObservableProperty] public partial string PasteText { get; set; } = "";
    [ObservableProperty] public partial string Destination { get; set; }
    [ObservableProperty] public partial bool WatchClipboard { get; set; }
    [ObservableProperty] public partial string? ClipboardLink { get; set; }
    [ObservableProperty] public partial int ActiveCount { get; set; }
    [ObservableProperty] public partial int CompletedCount { get; set; }

    public int DetectedCount => LinkParser.Extract(PasteText).Count;
    public string AddLabel => DetectedCount switch { 0 => "Add links", 1 => "Download 1 link", var n => $"Download {n} links" };
    public bool CanAdd => DetectedCount > 0;
    public bool HasClipboardLink => ClipboardLink is not null;
    public bool IsEmpty => Items.Count == 0;
    public string Summary => Items.Count == 0 ? "Nothing queued yet" :
        $"{ActiveCount} active · {CompletedCount} done · {Items.Count(i => i.IsBlocked)} need a browser";

    partial void OnPasteTextChanged(string value)
    {
        OnPropertyChanged(nameof(DetectedCount));
        OnPropertyChanged(nameof(AddLabel));
        OnPropertyChanged(nameof(CanAdd));
    }

    partial void OnClipboardLinkChanged(string? value) => OnPropertyChanged(nameof(HasClipboardLink));

    partial void OnWatchClipboardChanged(bool value)
    {
        if (value) _clipboardTimer.Start(); else { _clipboardTimer.Stop(); ClipboardLink = null; }
        if (_services.Settings.WatchClipboard == value) return;
        _services.Settings.WatchClipboard = value;
        _services.SettingsStore.Save(_services.Settings);
    }

    private void Refresh()
    {
        ActiveCount = Items.Count(i => i.IsActive);
        CompletedCount = Items.Count(i => i.IsDone);
        OnPropertyChanged(nameof(IsEmpty));
        OnPropertyChanged(nameof(Summary));
    }

    /// <summary>Queue plain links (pasted, dropped, or from the clipboard) into the chosen folder.</summary>
    public int AddLinks(string text)
    {
        var links = LinkParser.Extract(text);
        foreach (var url in links) _services.Downloads.Enqueue(new DownloadJob(url, Destination));
        if (links.Count > 0) _services.Toasts.Show(links.Count == 1 ? "1 link queued" : $"{links.Count} links queued");
        return links.Count;
    }

    [RelayCommand]
    private void AddPasted()
    {
        if (AddLinks(PasteText) > 0) PasteText = "";
    }

    [RelayCommand]
    private async Task PasteFromClipboardAsync()
    {
        var text = await _services.Platform.ClipboardTextAsync();
        if (!string.IsNullOrWhiteSpace(text)) PasteText = string.IsNullOrWhiteSpace(PasteText) ? text : PasteText.TrimEnd() + Environment.NewLine + text;
    }

    [RelayCommand]
    private void AddClipboardLink()
    {
        if (ClipboardLink is null) return;
        AddLinks(ClipboardLink);
        ClipboardLink = null;
    }

    [RelayCommand]
    private void DismissClipboardLink() => ClipboardLink = null;

    [RelayCommand]
    private async Task BrowseAsync()
    {
        var picked = await _services.Platform.PickFolderAsync("Download links into…", Destination);
        if (picked is not null) Destination = picked;
    }

    [RelayCommand]
    private async Task OpenDestinationAsync() => await _services.Platform.OpenFolderAsync(Destination);

    [RelayCommand]
    private void ClearFinished()
    {
        _services.Downloads.ClearFinished();
        foreach (var done in Items.Where(i => i.Status is DownloadStatus.Completed or DownloadStatus.Canceled).ToList()) Items.Remove(done);
        Refresh();
    }

    [RelayCommand] private void Pause(DownloadItemViewModel item) => _services.Downloads.Pause(item.Job);
    [RelayCommand] private void Resume(DownloadItemViewModel item) => _services.Downloads.Resume(item.Job);
    [RelayCommand] private void Retry(DownloadItemViewModel item) => _services.Downloads.Retry(item.Job);
    [RelayCommand] private void Cancel(DownloadItemViewModel item) => _services.Downloads.Cancel(item.Job);

    [RelayCommand]
    private void Remove(DownloadItemViewModel item)
    {
        _services.Downloads.Remove(item.Job);
        Items.Remove(item);
        Refresh();
    }

    [RelayCommand] private async Task OpenFolderAsync(DownloadItemViewModel item) => await _services.Platform.OpenFolderAsync(item.Destination);
    [RelayCommand] private async Task OpenFileAsync(DownloadItemViewModel item) => await _services.Platform.OpenFileAsync(item.Job.LocalPath);
    [RelayCommand] private async Task OpenInBrowserAsync(DownloadItemViewModel item) => await _services.Platform.OpenUrlAsync(item.BrowserUrl);

    [RelayCommand]
    private async Task CopyLinkAsync(DownloadItemViewModel item)
    {
        await _services.Platform.CopyTextAsync(item.Job.Url.AbsoluteUri);
        _services.Toasts.Show("Link copied");
    }

    private async Task PollClipboardAsync()
    {
        var text = await _services.Platform.ClipboardTextAsync();
        if (text is null || text == _lastClipboard) return;
        _lastClipboard = text;
        var link = LinkParser.Extract(text).FirstOrDefault();
        if (link is not null && Items.All(i => i.Job.Url != link)) ClipboardLink = link.AbsoluteUri;
    }
}
