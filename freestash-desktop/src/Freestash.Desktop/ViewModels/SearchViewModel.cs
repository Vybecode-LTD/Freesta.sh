using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Freestash.Client;
using Freestash.Client.Settings;
using Freestash.Desktop.Services;

namespace Freestash.Desktop.ViewModels;

/// <summary>Non-generic base so XAML can template it (x:DataType can't name generic types).</summary>
public abstract partial class OptionBase(string label, string hint) : ObservableObject
{
    public string Label { get; } = label;
    public string Hint { get; } = hint;
    [ObservableProperty] public partial bool IsSelected { get; set; }
}

public sealed class Option<T>(T value, string label, string hint = "") : OptionBase(label, hint)
{
    public T Value { get; } = value;
}

/// <summary>One column of the source spectrum under the lens: how long a source took, relative to the slowest.</summary>
public sealed partial class SourceStatusViewModel(ProviderStatus? status, string provider) : ObservableObject
{
    public const double BarMax = 76;
    public string Provider { get; } = provider.Replace('_', ' ');
    public bool Ok { get; } = status?.Ok ?? true;
    public bool Failed => status is { Ok: false };
    public bool IsPending => status is null;
    public long ElapsedMs { get; } = status?.ElapsedMs ?? 0;
    public string CountText { get; } = status is null ? "" : status.Ok ? status.Count.ToString() : "✕";
    public string Tooltip { get; } = status is null ? $"{provider}: waiting" : status.Ok
        ? $"{provider}: {status.Count} shown · {status.Total?.ToString("N0") ?? "?"} total · {status.ElapsedMs / 1000.0:0.0} s" : $"{provider}: {status.Error ?? "failed"}";
    [ObservableProperty] public partial double BarWidth { get; set; } = BarMax * 0.4;
}

public sealed class AssetCardViewModel(ScoredAsset scored)
{
    public ScoredAsset Scored { get; } = scored;
    public Asset Asset => Scored.Asset;
    public string Uid => Scored.Uid;
    public string Title => Asset.Title;
    public string SourceText => Asset.SourceName ?? Asset.Provider;
    public string MetaText => string.Join(" · ", new[] { Asset.Year?.ToString(), Asset.MediaType.ToString().ToLowerInvariant() }.Where(x => x is not null));
    public string LicenseText => Asset.License.Label;
    public string CardMeta => string.Join(" · ", new[] { SourceText, Asset.Year?.ToString() ?? Asset.Date }.Where(x => !string.IsNullOrEmpty(x)));
    public Tier Tier => Scored.Verdict.Tier;
    public string TierText => VerdictWords.Of(Tier);
    public bool IsGreen => Tier == Tier.Green;
    public bool IsYellow => Tier == Tier.Yellow;
    public bool IsRed => Tier == Tier.Red;
    /// <summary>Openverse's /thumb/ proxy is often 20s+; the direct CDN file decodes to the same size much faster.</summary>
    public string? ThumbnailUrl => Asset.ThumbnailUrl is { } t && t.Contains("api.openverse.org", StringComparison.Ordinal) && Asset.PreviewUrl is { } p
        ? p : Asset.ThumbnailUrl ?? Asset.PreviewUrl;
    public bool IsIcon => Asset.MediaType == MediaType.Icon;
    public bool IsFont => Asset.MediaType == MediaType.Font;
    public bool IsAudio => Asset.MediaType == MediaType.Audio && ThumbnailUrl is null;
    public bool ShowImage => !IsFont && !IsAudio && !IsIcon && ThumbnailUrl is not null;
    public string MediaText => Asset.MediaType.ToString();
    public string FontSample => "Aa";
    public string MediaIcon => Asset.MediaType switch
    {
        MediaType.Audio => "IconWave", MediaType.Video => "IconVideo", MediaType.Model => "IconCube",
        MediaType.Font => "IconType", MediaType.Texture or MediaType.Hdri => "IconSparkle", _ => "IconImage",
    };
    public string TopReason => Scored.Verdict.Reasons.FirstOrDefault() ?? "";
}

public sealed partial class SearchViewModel : ViewModelBase
{
    private readonly AppServices _services;
    private CancellationTokenSource? _cts;
    private readonly Dictionary<string, List<AssetCardViewModel>> _byProvider = new();

    public SearchViewModel(AppServices services)
    {
        _services = services;
        var s = services.Settings;
        Media =
        [
            new(MediaType.Image, "Images") { IsSelected = true }, new(MediaType.Audio, "Audio"), new(MediaType.Video, "Video"),
            new(MediaType.Texture, "Textures"), new(MediaType.Hdri, "HDRIs"), new(MediaType.Model, "3D"),
            new(MediaType.Font, "Fonts"), new(MediaType.Icon, "Icons"),
        ];
        UseCases =
        [
            new(UseCase.Reference, "Reference", "Mood boards and internal reference. Never shipped or shown."),
            new(UseCase.Demo, "Demo", "Demo and preview sites, mockups. Files aren't handed to customers."),
            new(UseCase.Client, "Client", "A commercial client deliverable or production website."),
            new(UseCase.Bundled, "Bundled", "Ships inside a product: template download, factory library, app."),
            new(UseCase.Merch, "Merch", "Printed or pressed onto goods for sale."),
        ];
        Tiers = [new(Tier.Green, "Clear", "Only results that are clear for this use"), new(Tier.Yellow, "+ Check", "Also results to check before you use them"),
                 new(Tier.Red, "All", "Everything, including blocked results")];

        ApplyDefaults(s);
        services.PrefsChanged += () => Avalonia.Threading.Dispatcher.UIThread.Post(() => { if (!HasSearched) ApplyDefaults(_services.Settings); });
        foreach (var o in UseCases.Cast<ObservableObject>().Concat(Tiers).Concat(Media))
            o.PropertyChanged += (sender, e) =>
            {
                if (e.PropertyName != "IsSelected") return;
                OnPropertyChanged(nameof(UseHint));
                OnPropertyChanged(nameof(SelectedUseCase));
                OnPropertyChanged(nameof(ResultsHeading));
                if (HasSearched && sender is Option<UseCase> { IsSelected: true } or Option<Tier> { IsSelected: true } or Option<MediaType>)
                    _ = SearchAsync();
            };
        Project = s.LastProject;
    }

    /// <summary>A new search starts from the account's defaults (synced with the website).</summary>
    private void ApplyDefaults(AppSettings s)
    {
        foreach (var u in UseCases) u.IsSelected = u.Value == s.DefaultUseCase;
        foreach (var t in Tiers) t.IsSelected = t.Value == s.DefaultMaxTier;
        foreach (var m in Media) m.IsSelected = s.DefaultMedia.Contains(m.Value);
        if (!Media.Any(m => m.IsSelected)) Media[0].IsSelected = true;
    }

    public event Action? QueuedDownload;

    public ObservableCollection<Option<MediaType>> Media { get; }
    public ObservableCollection<Option<UseCase>> UseCases { get; }
    public ObservableCollection<Option<Tier>> Tiers { get; }
    public ObservableCollection<AssetCardViewModel> Results { get; } = [];
    public IReadOnlyList<string> Suggestions { get; } =
        ["art deco poster", "weathered concrete", "rain on a tin roof", "botanical illustration", "nebula", "monospace", "arrow"];
    public ObservableCollection<SourceStatusViewModel> SourceStatuses { get; } = [];

    [ObservableProperty] public partial string Query { get; set; } = "";
    [ObservableProperty] public partial bool IsSearching { get; set; }
    [ObservableProperty] public partial bool HasSearched { get; set; }
    [ObservableProperty] public partial int HiddenCount { get; set; }
    [ObservableProperty] public partial string? Error { get; set; }
    [ObservableProperty] public partial AssetDetailViewModel? Detail { get; set; }
    [ObservableProperty] public partial string Project { get; set; } = "";
    [ObservableProperty] public partial int TotalSources { get; set; }
    [ObservableProperty] public partial int ReportedSources { get; set; }
    [ObservableProperty] public partial int FailedSources { get; set; }
    [ObservableProperty] public partial double ElapsedSeconds { get; set; }

    /// <summary>The line under the query, as on the web: progress while streaming, totals after.</summary>
    public string LensMeta => !HasSearched ? "SEARCH 20 OPEN COLLECTIONS AT ONCE · CTRL K"
        : $"{ReportedSources} OF {TotalSources} SOURCES REPORTED · {Results.Count} RESULTS" + (ElapsedSeconds > 0 ? $" · {ElapsedSeconds:0.0} S" : "");
    public string ResultsHeading => (SelectedMaxTier switch { Tier.Green => "Clear", Tier.Yellow => "Clear or worth checking", _ => "Everything" })
        + $" for {SelectedUseCase.ToString().ToLowerInvariant()} use";

    public UseCase SelectedUseCase => UseCases.FirstOrDefault(u => u.IsSelected)?.Value ?? UseCase.Demo;
    public Tier SelectedMaxTier => Tiers.FirstOrDefault(t => t.IsSelected)?.Value ?? Tier.Yellow;
    public string UseHint => UseCases.FirstOrDefault(u => u.IsSelected)?.Hint ?? "";
    public bool ShowEmptyHero => !HasSearched;
    public bool ShowNoResults => HasSearched && !IsSearching && Results.Count == 0;
    public bool HasDetail => Detail is not null;
    public string ResultSummary => Results.Count == 0 ? "" : $"{Results.Count} results" + (HiddenCount > 0 ? $" · {HiddenCount} hidden by filter" : "");

    partial void OnHasSearchedChanged(bool value) { OnPropertyChanged(nameof(ShowEmptyHero)); OnPropertyChanged(nameof(ShowNoResults)); OnPropertyChanged(nameof(LensMeta)); }
    partial void OnTotalSourcesChanged(int value) => OnPropertyChanged(nameof(LensMeta)); // "0 OF 20" shows at once, as on the web
    partial void OnIsSearchingChanged(bool value) => OnPropertyChanged(nameof(ShowNoResults));
    partial void OnDetailChanged(AssetDetailViewModel? value) => OnPropertyChanged(nameof(HasDetail));
    partial void OnHiddenCountChanged(int value) => OnPropertyChanged(nameof(ResultSummary));
    partial void OnReportedSourcesChanged(int value) => OnPropertyChanged(nameof(LensMeta));
    partial void OnElapsedSecondsChanged(double value) => OnPropertyChanged(nameof(LensMeta));

    [RelayCommand]
    public async Task SearchAsync()
    {
        var q = Query.Trim();
        if (q.Length == 0) return;
        _cts?.Cancel();
        var cts = _cts = new CancellationTokenSource();
        var media = Media.Where(m => m.IsSelected).Select(m => m.Value).ToList();
        if (media.Count == 0) { Media[0].IsSelected = true; media.Add(MediaType.Image); }

        Results.Clear();
        SourceStatuses.Clear();
        _byProvider.Clear();
        HiddenCount = 0;
        ReportedSources = 0;
        FailedSources = 0;
        ElapsedSeconds = 0;
        var started = System.Diagnostics.Stopwatch.StartNew();
        var wanted = media.Select(m => m.ToString().ToLowerInvariant()).ToHashSet();
        List<string> asked;
        try { asked = (await _services.Api.Current.ProvidersAsync(cts.Token)).Where(p => p.Enabled && p.MediaTypes.Any(wanted.Contains)).Select(p => p.Id).ToList(); }
        catch (Exception) { asked = []; }
        TotalSources = asked.Count;
        foreach (var id in asked) SourceStatuses.Add(new SourceStatusViewModel(null, id));
        Error = null;
        HasSearched = true;
        IsSearching = true;
        Detail = null;
        try
        {
            var req = new SearchRequest(q, media, SelectedUseCase, SelectedMaxTier, Limit: _services.Settings.ResultsPerSource);
            await foreach (var batch in _services.Api.Current.SearchStreamAsync(req, cts.Token))
            {
                if (cts.IsCancellationRequested) break;
                _byProvider[batch.Status.Provider] = batch.Results.Select(r => new AssetCardViewModel(r)).ToList();
                var pending = SourceStatuses.FirstOrDefault(x => x.IsPending && x.Provider == batch.Status.Provider.Replace('_', ' '));
                if (pending is not null) SourceStatuses.Remove(pending);
                SourceStatuses.Insert(SourceStatuses.Count(x => !x.IsPending), new SourceStatusViewModel(batch.Status, batch.Status.Provider));
                ReportedSources++;
                if (!batch.Status.Ok) FailedSources++;
                if (TotalSources < ReportedSources) TotalSources = ReportedSources;
                var slowest = Math.Max(1, SourceStatuses.Max(x => x.ElapsedMs));
                foreach (var x in SourceStatuses.Where(x => !x.IsPending)) x.BarWidth = SourceStatusViewModel.BarMax * Math.Max(0.06, x.ElapsedMs / (double)slowest);
                HiddenCount += batch.Hidden;
                ElapsedSeconds = started.Elapsed.TotalSeconds;
                Rebuild();
            }
        }
        catch (OperationCanceledException) { }
        catch (Exception ex) when (!cts.IsCancellationRequested)
        {
            Error = _services.Engine.State == Client.Engine.EngineState.Online
                ? ex.Message
                : "The Freestash engine isn't reachable. Check the status pill up top, or Settings → Engine.";
        }
        finally
        {
            if (ReferenceEquals(cts, _cts))
            {
                IsSearching = false;
                ElapsedSeconds = started.Elapsed.TotalSeconds;
                foreach (var x in SourceStatuses.Where(x => x.IsPending).ToList()) SourceStatuses.Remove(x);
                OnPropertyChanged(nameof(ResultsHeading));
            }
        }
    }

    /// <summary>Round-robin across providers so one chatty source can't bury the rest; greens first.</summary>
    private void Rebuild()
    {
        var ordered = new List<AssetCardViewModel>();
        foreach (var tier in new[] { Tier.Green, Tier.Yellow, Tier.Red })
        {
            var queues = _byProvider.Values.Select(l => new Queue<AssetCardViewModel>(l.Where(c => c.Tier == tier))).ToList();
            while (queues.Any(q => q.Count > 0))
                foreach (var q in queues)
                    if (q.TryDequeue(out var c)) ordered.Add(c);
        }
        // Append-only when possible so already-visible cards don't jump around while streaming.
        var existing = Results.Select(r => r.Uid).ToHashSet();
        if (ordered.Take(Results.Count).Select(r => r.Uid).SequenceEqual(Results.Select(r => r.Uid)))
        {
            foreach (var c in ordered.Skip(Results.Count)) Results.Add(c);
        }
        else
        {
            Results.Clear();
            foreach (var c in ordered) Results.Add(c);
        }
        _ = existing;
        OnPropertyChanged(nameof(ShowNoResults));
        OnPropertyChanged(nameof(ResultSummary));
        OnPropertyChanged(nameof(LensMeta));
    }

    [RelayCommand]
    private async Task OpenAsync(AssetCardViewModel card)
    {
        var collections = await _services.Api.Current.CollectionsAsync().ContinueWith(t => t.IsCompletedSuccessfully ? t.Result : []);
        Detail = new AssetDetailViewModel(_services, card.Scored, SelectedUseCase, this, collections) { OnClose = () => Detail = null };
        await Detail.LoadAsync();
    }

    [RelayCommand]
    private void CloseDetail() => Detail = null;

    [RelayCommand]
    private async Task SuggestAsync(string query)
    {
        Query = query;
        if (query is "monospace") { foreach (var m in Media) m.IsSelected = m.Value == MediaType.Font; }
        else if (query is "arrow") { foreach (var m in Media) m.IsSelected = m.Value == MediaType.Icon; }
        else if (query.Contains("rain")) { foreach (var m in Media) m.IsSelected = m.Value == MediaType.Audio; }
        else if (query.Contains("concrete")) { foreach (var m in Media) m.IsSelected = m.Value is MediaType.Texture or MediaType.Image; }
        await SearchAsync();
    }

    internal void NotifyQueued() => QueuedDownload?.Invoke();

    internal void RememberProject(string project)
    {
        Project = project;
        if (_services.Settings.LastProject == project) return;
        _services.Settings.LastProject = project;
        _services.SettingsStore.Save(_services.Settings);
    }
}

/// <summary>The verdict words both apps use (web: TIER_WORD in lib/types.ts). GREEN/YELLOW/RED stay the engine's names.</summary>
public static class VerdictWords
{
    public static string Of(Tier tier) => tier switch { Tier.Green => "CLEAR", Tier.Yellow => "CHECK", _ => "BLOCKED" };
}
