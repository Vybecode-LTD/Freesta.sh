using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Freestash.Client;
using Freestash.Client.Downloads;
using Freestash.Desktop.Services;

namespace Freestash.Desktop.ViewModels;

public sealed class VerdictRowViewModel(string label, Verdict verdict, bool isCurrent)
{
    public string Label { get; } = label;
    public Verdict Verdict { get; } = verdict;
    public bool IsCurrent { get; } = isCurrent;
    public string TierText => Verdict.Tier.ToString().ToUpperInvariant();
    public bool IsGreen => Verdict.Tier == Tier.Green;
    public bool IsYellow => Verdict.Tier == Tier.Yellow;
    public bool IsRed => Verdict.Tier == Tier.Red;
    public IReadOnlyList<string> Reasons => Verdict.Reasons;
    public IReadOnlyList<string> Obligations => Verdict.Obligations;
    public bool HasObligations => Verdict.Obligations.Count > 0;
}

public sealed class RenditionViewModel(Rendition rendition)
{
    public Rendition Rendition { get; } = rendition;
    public string Label => Rendition.Label;
    public string SizeText => Rendition.SizeText;
    public string Url => Rendition.Url;
}

public sealed partial class AssetDetailViewModel : ObservableObject
{
    private static readonly (UseCase Use, string Label)[] Uses =
        [(UseCase.Reference, "Reference"), (UseCase.Demo, "Demo"), (UseCase.Client, "Client"), (UseCase.Bundled, "Bundled"), (UseCase.Merch, "Merch")];

    private readonly AppServices _services;
    private readonly SearchViewModel? _owner;

    public AssetDetailViewModel(AppServices services, ScoredAsset scored, UseCase useCase, SearchViewModel? owner, IReadOnlyList<Collection> collections)
    {
        _services = services;
        _owner = owner;
        Scored = scored;
        UseCase = useCase;
        Project = owner?.Project ?? services.Settings.LastProject;
        Collections = new ObservableCollection<Collection>(collections.Where(c => c.UseCase == useCase).Concat(collections.Where(c => c.UseCase != useCase)));
        VerdictRows = [new VerdictRowViewModel(Uses.First(u => u.Use == useCase).Label, scored.Verdict, true)];
        Renditions = new ObservableCollection<RenditionViewModel>(scored.Asset.Renditions.Select(r => new RenditionViewModel(r)));
    }

    public ScoredAsset Scored { get; private set; }
    public Asset Asset => Scored.Asset;
    public Verdict Verdict => Scored.Verdict;
    public UseCase UseCase { get; }
    public ObservableCollection<VerdictRowViewModel> VerdictRows { get; private set; }
    public ObservableCollection<RenditionViewModel> Renditions { get; }
    public ObservableCollection<Collection> Collections { get; }

    public Action? OnClose { get; init; }

    [ObservableProperty] public partial bool IsLoading { get; set; }
    [ObservableProperty] public partial string Project { get; set; }
    [ObservableProperty] public partial string? AttributionHtml { get; set; }
    [ObservableProperty] public partial Collection? SelectedCollection { get; set; }

    public string Title => Asset.Title;
    public string Byline => string.Join(" · ", new[] { Asset.Creator, Asset.Date }.Where(x => !string.IsNullOrWhiteSpace(x))) is { Length: > 0 } b ? b : "Unknown creator";
    public string LicenseLabel => Asset.License.Label;
    public string? LicenseUrl => Asset.License.Url;
    public string TrustText => Asset.Trust.ToString().ToLowerInvariant();
    public string SourceText => Asset.SourceName ?? Asset.Provider;
    public string? PreviewUrl => Asset.PreviewUrl ?? Asset.ThumbnailUrl;
    public string TierText => Verdict.Tier.ToString().ToUpperInvariant();
    public bool IsGreen => Verdict.Tier == Tier.Green;
    public bool IsYellow => Verdict.Tier == Tier.Yellow;
    public bool IsRed => Verdict.Tier == Tier.Red;
    public bool CanDownload => !IsRed && Renditions.Count > 0;
    public string DownloadLabel => IsRed ? "Red for this use" : Renditions.Count == 0 ? (IsLoading ? "Fetching files…" : "No direct files") : "Download";
    public string? Attribution => Verdict.Attribution;
    public string? RawLicense => Asset.License.Raw;
    public bool HasRawLicense => !string.IsNullOrWhiteSpace(RawLicense);
    public string SizeText => Asset.Width is > 0 && Asset.Height is > 0 ? $"{Asset.Width} × {Asset.Height}" : "";
    public bool HasSize => SizeText.Length > 0;
    public IReadOnlyList<string> Tips => Asset.Tips;
    public bool HasTips => Asset.Tips.Count > 0;
    public string? Description => Asset.Description;
    public bool HasDescription => !string.IsNullOrWhiteSpace(Description);
    public bool IsIcon => Asset.MediaType == MediaType.Icon;
    public bool IsFont => Asset.MediaType == MediaType.Font;
    public bool HasCollections => Collections.Count > 0;
    public string UseCaseText => UseCase.ToString();

    partial void OnIsLoadingChanged(bool value) => OnPropertyChanged(nameof(DownloadLabel));

    public async Task LoadAsync()
    {
        IsLoading = true;
        try
        {
            var detail = await _services.Api.Current.AssetAsync(Scored.Uid, UseCase);
            Scored = new ScoredAsset(detail.Uid, detail.Asset, detail.Verdict);
            AttributionHtml = detail.AttributionHtml;
            VerdictRows = new ObservableCollection<VerdictRowViewModel>(Uses.Select(u =>
                new VerdictRowViewModel(u.Label, detail.Verdicts.TryGetValue(u.Use.Wire(), out var v) ? v : detail.Verdict, u.Use == UseCase)));
            Renditions.Clear();
            foreach (var r in detail.Asset.Renditions) Renditions.Add(new RenditionViewModel(r));
            OnPropertyChanged(string.Empty); // everything derived from Scored
        }
        catch (Exception ex)
        {
            _services.Toasts.Show($"Couldn't load full details: {ex.Message}");
        }
        finally
        {
            IsLoading = false;
        }
    }

    [RelayCommand]
    private void Close() => OnClose?.Invoke();

    [RelayCommand]
    private void DownloadBest()
    {
        var best = PickBest(Renditions.Select(r => r.Rendition).ToList());
        if (best is not null) Download(best);
    }

    [RelayCommand]
    private void DownloadRendition(RenditionViewModel rendition) => Download(rendition.Rendition);

    private void Download(Rendition rendition)
    {
        if (IsRed)
        {
            _services.Toasts.Show("This is RED for the selected use case, so it won't be downloaded.");
            return;
        }
        var project = string.IsNullOrWhiteSpace(Project) ? null : Project.Trim();
        if (project is not null) _owner?.RememberProject(project);
        var job = new DownloadJob(new Uri(rendition.Url), _services.Settings.DirectoryFor(project), FileNames.ForAsset(Asset, rendition))
        {
            Asset = Scored, Rendition = rendition, UseCase = UseCase, Project = project,
        };
        _services.Downloads.Enqueue(job);
        _owner?.NotifyQueued();
        _services.Toasts.Show($"Queued “{Truncate(Asset.Title, 42)}” → Downloads");
    }

    [RelayCommand]
    private async Task OpenSourceAsync() => await _services.Platform.OpenUrlAsync(Asset.LandingUrl ?? Asset.PreviewUrl);

    [RelayCommand]
    private async Task OpenUrlAsync(string? url) => await _services.Platform.OpenUrlAsync(url);

    [RelayCommand]
    private async Task CopyCreditAsync()
    {
        if (Attribution is null) return;
        await _services.Platform.CopyTextAsync(Attribution);
        _services.Toasts.Show("Credit line copied");
    }

    [RelayCommand]
    private async Task CopyHtmlAsync()
    {
        if (AttributionHtml is null) return;
        await _services.Platform.CopyTextAsync(AttributionHtml);
        _services.Toasts.Show("HTML credit copied");
    }

    [RelayCommand]
    private async Task AddToCollectionAsync()
    {
        if (SelectedCollection is null) return;
        try
        {
            await _services.Api.Current.AddToCollectionAsync(SelectedCollection.Id, Asset);
            _services.Toasts.Show($"Added to {SelectedCollection.Name}");
        }
        catch (Exception ex)
        {
            _services.Toasts.Show(ex.Message);
        }
    }

    /// <summary>Largest rendition that isn't a huge original (TIFFs, 8k maps): mirrors the CLI's "large" preference.</summary>
    public static Rendition? PickBest(IReadOnlyList<Rendition> renditions)
    {
        if (renditions.Count == 0) return null;
        static int Rank(Rendition r)
        {
            var l = r.Label.ToLowerInvariant();
            if (l.Contains("large") || l.Contains("print") || l.Contains("1686") || l.Contains("1600") || l.Contains("2k") || l.Contains("regular") || l.Contains("hq")) return 0;
            if (l.Contains("orig") || l.Contains("full") || l.Contains("max") || l.Contains("raw") || l.Contains("native")) return 1;
            return 2;
        }
        return renditions.Where(r => r.Bytes is null or < 250_000_000).OrderBy(Rank).ThenByDescending(r => r.Bytes ?? 0).FirstOrDefault() ?? renditions[0];
    }

    private static string Truncate(string s, int n) => s.Length <= n ? s : s[..(n - 1)] + "…";
}
