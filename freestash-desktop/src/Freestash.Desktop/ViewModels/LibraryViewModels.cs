using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Freestash.Client;
using Freestash.Client.Downloads;
using Freestash.Desktop.Services;

namespace Freestash.Desktop.ViewModels;

// ============================================================================= Collections
public sealed partial class CollectionsViewModel(AppServices services) : ViewModelBase
{
    public ObservableCollection<Collection> List { get; } = [];
    public ObservableCollection<AssetCardViewModel> Items { get; } = [];
    public IReadOnlyList<UseCase> UseCases { get; } = Enum.GetValues<UseCase>();

    [ObservableProperty] public partial Collection? Selected { get; set; }
    [ObservableProperty] public partial string NewName { get; set; } = "";
    [ObservableProperty] public partial UseCase NewUseCase { get; set; } = UseCase.Demo;
    [ObservableProperty] public partial AssetDetailViewModel? Detail { get; set; }
    [ObservableProperty] public partial string? Error { get; set; }

    public bool HasSelection => Selected is not null;
    public bool HasDetail => Detail is not null;
    public bool IsEmpty => List.Count == 0;
    public string SelectedSummary => Selected is null ? "" : $"Scored for {Selected.UseCase.ToString().ToLowerInvariant()} · {Items.Count} item(s)";

    partial void OnDetailChanged(AssetDetailViewModel? value) => OnPropertyChanged(nameof(HasDetail));

    partial void OnSelectedChanged(Collection? value)
    {
        OnPropertyChanged(nameof(HasSelection));
        _ = LoadItemsAsync(value);
    }

    public override async Task OnShownAsync() => await RefreshAsync();

    [RelayCommand]
    private async Task RefreshAsync()
    {
        try
        {
            Error = null;
            var keep = Selected?.Id;
            var list = await services.Api.Current.CollectionsAsync();
            List.Clear();
            foreach (var c in list) List.Add(c);
            Selected = List.FirstOrDefault(c => c.Id == keep) ?? List.FirstOrDefault();
        }
        catch (Exception ex) { Error = ex.Message; }
        OnPropertyChanged(nameof(IsEmpty));
    }

    private async Task LoadItemsAsync(Collection? c)
    {
        Items.Clear();
        Detail = null;
        if (c is null) return;
        try
        {
            var full = await services.Api.Current.CollectionAsync(c.Id);
            foreach (var i in full.Items ?? []) Items.Add(new AssetCardViewModel(new ScoredAsset(i.Uid, i.Asset, i.Verdict)));
        }
        catch (Exception ex) { Error = ex.Message; }
        OnPropertyChanged(nameof(SelectedSummary));
    }

    [RelayCommand]
    private async Task CreateAsync()
    {
        if (string.IsNullOrWhiteSpace(NewName)) return;
        try
        {
            var created = await services.Api.Current.CreateCollectionAsync(NewName.Trim(), NewUseCase);
            NewName = "";
            await RefreshAsync();
            Selected = List.FirstOrDefault(x => x.Id == created.Id);
        }
        catch (Exception ex) { services.Toasts.Show(ex.Message); }
    }

    [RelayCommand]
    private async Task DeleteAsync()
    {
        if (Selected is null) return;
        await services.Api.Current.DeleteCollectionAsync(Selected.Id);
        Selected = null;
        await RefreshAsync();
    }

    [RelayCommand]
    private async Task OpenAsync(AssetCardViewModel card)
    {
        Detail = new AssetDetailViewModel(services, card.Scored, Selected?.UseCase ?? UseCase.Demo, null, List.ToList()) { OnClose = () => Detail = null };
        await Detail.LoadAsync();
    }

    [RelayCommand] private void CloseDetail() => Detail = null;

    [RelayCommand]
    private async Task RemoveAsync(AssetCardViewModel card)
    {
        if (Selected is null) return;
        await services.Api.Current.RemoveFromCollectionAsync(Selected.Id, card.Uid);
        Items.Remove(card);
        OnPropertyChanged(nameof(SelectedSummary));
    }

    [RelayCommand]
    private async Task CopyCreditsAsync()
    {
        if (Selected is null) return;
        var lines = Items.Select(i => $"- {i.Scored.Verdict.Attribution ?? i.Title}");
        await services.Platform.CopyTextAsync($"# Credits — {Selected.Name}\n\n{string.Join("\n", lines)}\n");
        services.Toasts.Show("Credits copied");
    }

    /// <summary>Pull the whole board: fetch each item's files and queue the best rendition into one project folder.</summary>
    [RelayCommand]
    private async Task DownloadAllAsync()
    {
        if (Selected is null) return;
        var project = FileNames.Sanitize(Selected.Name) ?? "collection";
        int queued = 0, skipped = 0;
        foreach (var card in Items.ToList())
        {
            if (card.Tier == Tier.Red) { skipped++; continue; }
            try
            {
                var detail = await services.Api.Current.AssetAsync(card.Uid, Selected.UseCase);
                var best = AssetDetailViewModel.PickBest(detail.Asset.Renditions);
                if (best is null) { skipped++; continue; }
                services.Downloads.Enqueue(new DownloadJob(new Uri(best.Url), services.Settings.DirectoryFor(project), FileNames.ForAsset(detail.Asset, best))
                {
                    Asset = new ScoredAsset(detail.Uid, detail.Asset, detail.Verdict), Rendition = best, UseCase = Selected.UseCase, Project = project,
                });
                queued++;
            }
            catch { skipped++; }
        }
        services.Toasts.Show($"Queued {queued} file(s) into “{project}”" + (skipped > 0 ? $" · {skipped} skipped (red or no files)" : ""));
    }
}

// ============================================================================= Ledger
public sealed partial class LedgerViewModel(AppServices services) : ViewModelBase
{
    public ObservableCollection<LedgerEntry> Entries { get; } = [];
    public ObservableCollection<string> Projects { get; } = [];

    [ObservableProperty] public partial string? SelectedProject { get; set; }
    [ObservableProperty] public partial string? Error { get; set; }

    public bool IsEmpty => Entries.Count == 0;
    public const string AllProjects = "All projects";

    partial void OnSelectedProjectChanged(string? value) => _ = LoadAsync();

    public override async Task OnShownAsync()
    {
        try
        {
            var projects = await services.Api.Current.ProjectsAsync();
            var keep = SelectedProject;
            Projects.Clear();
            Projects.Add(AllProjects);
            foreach (var p in projects) Projects.Add(p);
            SelectedProject = keep is not null && Projects.Contains(keep) ? keep : AllProjects;
        }
        catch (Exception ex) { Error = ex.Message; }
        await LoadAsync();
    }

    private string? Filter => SelectedProject is null or AllProjects ? null : SelectedProject;

    private async Task LoadAsync()
    {
        try
        {
            Error = null;
            var list = await services.Api.Current.LedgerAsync(Filter);
            Entries.Clear();
            foreach (var e in list) Entries.Add(e);
        }
        catch (Exception ex) { Error = ex.Message; }
        OnPropertyChanged(nameof(IsEmpty));
    }

    [RelayCommand]
    private async Task ExportAsync(string format)
    {
        try
        {
            var body = await services.Api.Current.ExportLedgerAsync(format, Filter);
            var (name, ext) = format switch { "html" => ("credits.html", "html"), "csv" => ("freestash-ledger.csv", "csv"), _ => ("ATTRIBUTION.md", "md") };
            if (Filter is not null) name = $"{FileNames.Slug(Filter, 40)}-{name}";
            if (await services.Platform.SaveTextAsync(name, body, ext)) services.Toasts.Show($"Saved {name}");
        }
        catch (Exception ex) { services.Toasts.Show(ex.Message); }
    }

    [RelayCommand] private async Task OpenUrlAsync(string? url) => await services.Platform.OpenUrlAsync(url);
}

// ============================================================================= License check
public sealed partial class LicenseCheckViewModel(AppServices services) : ViewModelBase
{
    public IReadOnlyList<Trust> TrustChoices { get; } = Enum.GetValues<Trust>();
    public IReadOnlyList<MediaType> MediaChoices { get; } = Enum.GetValues<MediaType>();
    public ObservableCollection<VerdictRowViewModel> Rows { get; } = [];

    [ObservableProperty] public partial string LicenseText { get; set; } = "";
    [ObservableProperty] public partial Trust Trust { get; set; } = Trust.Unknown;
    [ObservableProperty] public partial MediaType Media { get; set; } = MediaType.Image;
    [ObservableProperty] public partial decimal? Year { get; set; }
    [ObservableProperty] public partial string? Recognized { get; set; }
    [ObservableProperty] public partial string? CutoffText { get; set; }

    public bool HasResult => Rows.Count > 0;

    public override async Task OnShownAsync()
    {
        try
        {
            var c = await services.Api.Current.PdCutoffAsync();
            CutoffText = $"US public domain today: works from {c.Works} and earlier · sound recordings from {c.SoundRecordings} and earlier.";
        }
        catch { CutoffText = null; }
    }

    [RelayCommand]
    private async Task CheckAsync()
    {
        if (string.IsNullOrWhiteSpace(LicenseText)) return;
        try
        {
            var r = await services.Api.Current.CheckLicenseAsync(LicenseText.Trim(), Trust, Media, Year is null ? null : (int)Year);
            Recognized = $"{r.RecognizedAs.Label}  ·  {r.RecognizedAs.Id}";
            Rows.Clear();
            foreach (var (use, label) in new[] { ("reference", "Reference"), ("demo", "Demo"), ("client", "Client"), ("bundled", "Bundled"), ("merch", "Merch") })
                if (r.Verdicts.TryGetValue(use, out var v)) Rows.Add(new VerdictRowViewModel(label, v, false));
            OnPropertyChanged(nameof(HasResult));
        }
        catch (Exception ex) { services.Toasts.Show(ex.Message); }
    }
}

// ============================================================================= Sources
public sealed class SourceRowViewModel(ProviderInfo p)
{
    public ProviderInfo Info { get; } = p;
    public string Name => Info.Name;
    public string Id => Info.Id;
    public string Media => string.Join(" · ", Info.MediaTypes);
    public bool Enabled => Info.Enabled;
    public string StatusText => Info.Enabled ? "ON" : "NEEDS KEY";
    public string VerifiedText => Info.VerifiedLive ? "live-verified" : "built from docs";
    public string Notes => string.Join(" ", Info.Notes);
    public bool NeedsKey => !Info.Enabled && Info.KeySignupUrl is not null;
    public string? SignupUrl => Info.KeySignupUrl;
    public string Homepage => Info.Homepage;
}

public sealed partial class SourcesViewModel(AppServices services, Action openSettings) : ViewModelBase
{
    public ObservableCollection<SourceRowViewModel> Rows { get; } = [];

    [ObservableProperty] public partial string? Error { get; set; }
    [ObservableProperty] public partial string Summary { get; set; } = "";

    public override async Task OnShownAsync()
    {
        try
        {
            Error = null;
            var list = await services.Api.Current.ProvidersAsync();
            Rows.Clear();
            foreach (var p in list.OrderByDescending(p => p.Enabled)) Rows.Add(new SourceRowViewModel(p));
            Summary = $"{list.Count(p => p.Enabled)} of {list.Count} sources enabled";
        }
        catch (Exception ex) { Error = ex.Message; }
    }

    [RelayCommand] private void OpenSettings() => openSettings();
    [RelayCommand] private async Task OpenUrlAsync(string? url) => await services.Platform.OpenUrlAsync(url);
}

public static class LedgerConv
{
    public static readonly Avalonia.Data.Converters.FuncValueConverter<Tier, bool> IsGreen = new(t => t == Tier.Green);
    public static readonly Avalonia.Data.Converters.FuncValueConverter<Tier, bool> IsYellow = new(t => t == Tier.Yellow);
    public static readonly Avalonia.Data.Converters.FuncValueConverter<Tier, bool> IsRed = new(t => t == Tier.Red);
    public static readonly Avalonia.Data.Converters.FuncValueConverter<string?, string> Date = new(s => s is { Length: >= 10 } ? s[..10] : s ?? "");
}
