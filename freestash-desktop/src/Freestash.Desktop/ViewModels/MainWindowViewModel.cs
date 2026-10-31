using System.Collections.ObjectModel;
using Avalonia.Threading;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Freestash.Client.Engine;
using Freestash.Desktop.Services;

namespace Freestash.Desktop.ViewModels;

public abstract class ViewModelBase : ObservableObject
{
    /// <summary>Called when the page becomes visible (lazy loads, refreshes).</summary>
    public virtual Task OnShownAsync() => Task.CompletedTask;
}

public sealed partial class NavItem(string title, string icon, ViewModelBase page, string? section = null) : ObservableObject
{
    public string Title { get; } = title;
    public string Icon { get; } = icon;
    public ViewModelBase Page { get; } = page;
    public string? Section { get; } = section;
    public bool HasSection => Section is not null;

    [ObservableProperty] public partial bool IsSelected { get; set; }
    [ObservableProperty] public partial int Badge { get; set; }

    public bool HasBadge => Badge > 0;
    partial void OnBadgeChanged(int value) => OnPropertyChanged(nameof(HasBadge));
}

public sealed partial class MainWindowViewModel : ViewModelBase
{
    private readonly AppServices _services;

    public MainWindowViewModel(AppServices services)
    {
        _services = services;
        Downloads = new DownloadsViewModel(services);
        Search = new SearchViewModel(services);
        Collections = new CollectionsViewModel(services);
        Ledger = new LedgerViewModel(services);
        LicenseCheck = new LicenseCheckViewModel(services);
        Sources = new SourcesViewModel(services, () => Navigate(SettingsItem!)); // SettingsItem is assigned below; the lambda runs later
        Settings = new SettingsViewModel(services);
        SignIn = new SignInViewModel(services);

        NavItems =
        [
            new NavItem("Search", "IconSearch", Search, "LIBRARY"),
            new NavItem("Collections", "IconLayers", Collections),
            DownloadsItem = new NavItem("Downloads", "IconDownload", Downloads),
            new NavItem("Ledger", "IconLedger", Ledger),
            new NavItem("License check", "IconShield", LicenseCheck, "TOOLS"),
            new NavItem("Sources", "IconGlobe", Sources),
        ];
        SettingsItem = new NavItem("Settings", "IconSliders", Settings);

        foreach (var item in NavItems.Append(SettingsItem))
            item.PropertyChanged += (s, e) =>
            {
                if (e.PropertyName == nameof(NavItem.IsSelected) && s is NavItem { IsSelected: true } selected) Show(selected);
            };

        Downloads.PropertyChanged += (_, e) =>
        {
            if (e.PropertyName == nameof(DownloadsViewModel.ActiveCount)) DownloadsItem.Badge = Downloads.ActiveCount;
        };
        Search.QueuedDownload += () => DownloadsItem.Badge = Downloads.ActiveCount;

        services.Engine.StateChanged += () => Dispatcher.UIThread.Post(UpdateEngine);
        services.Session.Changed += () => Dispatcher.UIThread.Post(UpdateAccount);
        UpdateEngine();
        UpdateAccount();
        NavItems[0].IsSelected = true;
    }

    public ObservableCollection<NavItem> NavItems { get; }
    public NavItem SettingsItem { get; }
    public NavItem DownloadsItem { get; }

    public SearchViewModel Search { get; }
    public CollectionsViewModel Collections { get; }
    public DownloadsViewModel Downloads { get; }
    public LedgerViewModel Ledger { get; }
    public LicenseCheckViewModel LicenseCheck { get; }
    public SourcesViewModel Sources { get; }
    public SettingsViewModel Settings { get; }
    public SignInViewModel SignIn { get; }
    public ToastService Toasts => _services.Toasts;

    [ObservableProperty] public partial ViewModelBase? CurrentPage { get; set; }
    [ObservableProperty] public partial string EngineText { get; set; } = "Connecting…";
    [ObservableProperty] public partial bool EngineOnline { get; set; }
    [ObservableProperty] public partial bool EngineStarting { get; set; }
    [ObservableProperty] public partial bool NeedsSignIn { get; set; }
    [ObservableProperty] public partial string AccountName { get; set; } = "";
    [ObservableProperty] public partial string AccountSub { get; set; } = "";
    public bool ShowShell => !NeedsSignIn;
    partial void OnNeedsSignInChanged(bool value) => OnPropertyChanged(nameof(ShowShell));

    public bool EngineOffline => !EngineOnline && !EngineStarting;
    partial void OnEngineOnlineChanged(bool value) => OnPropertyChanged(nameof(EngineOffline));
    partial void OnEngineStartingChanged(bool value) => OnPropertyChanged(nameof(EngineOffline));

    public void Navigate(NavItem item) => item.IsSelected = true;

    [RelayCommand]
    private void GoSearch() => Navigate(NavItems[0]);

    [RelayCommand]
    private void GoSettings() => Navigate(SettingsItem);

    [RelayCommand]
    private async Task ReconnectAsync() => await _services.Engine.EnsureRunningAsync();

    private void Show(NavItem selected)
    {
        foreach (var item in NavItems.Append(SettingsItem))
            if (!ReferenceEquals(item, selected)) item.IsSelected = false;
        CurrentPage = selected.Page;
        _ = selected.Page.OnShownAsync();
    }

    /// <summary>The account card at the foot of the rail, and the sign-in gate (hosted mode, no session).</summary>
    private void UpdateAccount()
    {
        NeedsSignIn = _services.NeedsSignIn;
        var user = _services.Session.Current?.User;
        AccountName = user?.DisplayName ?? user?.Email?.Split('@')[0] ?? "This computer";
        AccountSub = _services.UsesAccounts ? "synced · web + desktop" : "local engine";
    }

    private void UpdateEngine()
    {
        EngineText = _services.Engine.StatusText;
        EngineOnline = _services.Engine.State == EngineState.Online;
        EngineStarting = _services.Engine.State == EngineState.Starting;
    }
}
