using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Freestash.Client;
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

public sealed partial class SourceStatusViewModel(ProviderStatus status) : ObservableObject
{
    public string Provider { get; } = status.Provider;
    public bool Ok { get; } = status.Ok;
    public string CountText { get; } = status.Ok ? status.Count.ToString() : "✕";
    public string Tooltip { get; } = status.Ok ? $"{status.Count} shown · {status.Total?.ToString("N0") ?? "?"} total · {status.ElapsedMs} ms" : status.Error ?? "failed";
    public bool IsPending { get; init; }
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
    public Tier Tier => Scored.Verdict.Tier;
    public string TierText => Tier.ToString().ToUpperInvariant();
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
        Tiers = [new(Tier.Green, "Green only"), new(Tier.Yellow, "+ Yellow"), new(Tier.Red, "Everything")];

        foreach (var u in UseCases) u.IsSelected = u.Value == s.DefaultUseCase;
        foreach (var t in Tiers) t.IsSelected = t.Value == s.DefaultMaxTier;
        foreach (var o in UseCases.Cast<ObservableObject>().Concat(Tiers).Concat(Media))
            o.PropertyChanged += (sender, e) =>
            {
                if (e.PropertyName != "IsSelected") return;
                OnPropertyChanged(nameof(UseHint));
                OnPropertyChanged(nameof(SelectedUseCase));
                if (HasSearched && sender is Option<UseCase> { IsSelected: true } or Option<Tier> { IsSelected: true } or Option<MediaType>)
                    _ = SearchAsync();
            };
        Project = s.LastProject;
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

    public UseCase SelectedUseCase => UseCases.FirstOrDefault(u => u.IsSelected)?.Value ?? UseCase.Demo;
    public Tier SelectedMaxTier => Tiers.FirstOrDefault(t => t.IsSelected)?.Value ?? Tier.Yellow;
    public string UseHint => UseCases.FirstOrDefault(u => u.IsSelected)?.Hint ?? "";
    public bool ShowEmptyHero => !HasSearched;
    public bool ShowNoResults => HasSearched && !IsSearching && Results.Count == 0;
    public bool HasDetail => Detail is not null;
    public string ResultSummary => Results.Count == 0 ? "" : $"{Results.Count} results" + (HiddenCount > 0 ? $" · {HiddenCount} hidden by filter" : "");

    partial void OnHasSearchedChanged(bool value) { OnPropertyChanged(nameof(ShowEmptyHero)); OnPropertyChanged(nameof(ShowNoResults)); }
    partial void OnIsSearchingChanged(bool value) => OnPropertyChanged(nameof(ShowNoResults));
    partial void OnDetailChanged(AssetDetailViewModel? value) => OnPropertyChanged(nameof(HasDetail));
    partial void OnHiddenCountChanged(int value) => OnPropertyChanged(nameof(ResultSummary));

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
                SourceStatuses.Add(new SourceStatusViewModel(batch.Status));
                HiddenCount += batch.Hidden;
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
            if (ReferenceEquals(cts, _cts)) IsSearching = false;
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
