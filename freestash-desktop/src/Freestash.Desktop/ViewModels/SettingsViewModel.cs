using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Freestash.Client;
using Freestash.Client.Account;
using Freestash.Client.Settings;
using Freestash.Desktop.Services;

namespace Freestash.Desktop.ViewModels;

public sealed record KeyStep(int Number, string Text);

/// <summary>
/// One provider key, with the help that sits under its input on both apps: the exact page to open, the steps,
/// the free limits, and anything broken right now. The text comes from the engine's key catalog.
/// </summary>
public sealed partial class KeyRowViewModel : ObservableObject
{
    private readonly Func<string, Task<string?>> _reveal;

    public KeyRowViewModel(KeySpec spec, Func<string, Task<string?>> reveal)
    {
        Spec = spec;
        _reveal = reveal;
        Steps = spec.Steps.Select((s, i) => new KeyStep(i + 1, s)).ToList();
    }

    public KeySpec Spec { get; }
    public string Name => Spec.Name;
    public string ProviderName => Spec.ProviderName;
    public string Label => Spec.Label;
    public string Url => Spec.Url;
    public string UrlLabel => Spec.UrlLabel;
    public IReadOnlyList<KeyStep> Steps { get; }
    public string Foot => Spec.Limits is { Length: > 0 } l ? $"{Spec.Unlocks}  ·  Free: {l}" : Spec.Unlocks;
    public string? Notice => Spec.Notice;
    public bool HasNotice => !string.IsNullOrEmpty(Spec.Notice);
    public bool IsRegister => Spec.Action == "openverse_register";
    public bool ShowLink => !IsRegister;

    public string OriginalValue { get; private set; } = "";
    [ObservableProperty] public partial string Value { get; set; } = "";
    [ObservableProperty] public partial bool IsRevealed { get; set; }
    [ObservableProperty] public partial string? SavedHint { get; set; } // cloud: the last 4 characters the account holds
    [ObservableProperty] public partial bool Removing { get; set; }

    public bool HasSaved => SavedHint is not null || OriginalValue.Length > 0;
    public bool IsDirty => Removing || Value.Trim() != OriginalValue.Trim();
    public char Mask => IsRevealed ? '\0' : '•';
    public string StatusText => Removing ? "WILL BE REMOVED" : HasSaved ? (SavedHint is { } h ? $"SET · …{h}" : "SET") : Spec.Optional ? "OPTIONAL" : "NOT SET";
    public bool IsSet => HasSaved && !Removing;
    public bool IsMissing => !HasSaved && !Spec.Optional;
    public string Placeholder => SavedHint is { } h && Value.Length == 0 ? $"Saved key ending in {h}. Paste a new one to replace it." : $"Paste your {Spec.Label}";

    partial void OnValueChanged(string value) => Refresh();
    partial void OnSavedHintChanged(string? value) => Refresh();
    partial void OnRemovingChanged(bool value) => Refresh();
    partial void OnIsRevealedChanged(bool value) => OnPropertyChanged(nameof(Mask));

    private void Refresh()
    {
        foreach (var p in new[] { nameof(HasSaved), nameof(IsDirty), nameof(StatusText), nameof(IsSet), nameof(IsMissing), nameof(Placeholder) })
            OnPropertyChanged(p);
    }

    /// <summary>Local mode: the plaintext from this machine's encrypted store.</summary>
    public void LoadLocal(string? value) { OriginalValue = value ?? ""; SavedHint = null; Removing = false; Value = OriginalValue; IsRevealed = false; Refresh(); }

    /// <summary>Cloud mode: only the masked state; the value is fetched on Reveal.</summary>
    public void LoadCloud(KeyState? state) { OriginalValue = ""; Value = ""; Removing = false; IsRevealed = false; SavedHint = state is { Set: true } ? state.Hint ?? "" : null; Refresh(); }

    [RelayCommand]
    private async Task ToggleRevealAsync()
    {
        if (IsRevealed) { IsRevealed = false; if (SavedHint is not null && !IsDirtyBeyondReveal()) { Value = ""; OriginalValue = ""; } return; }
        if (SavedHint is not null && Value.Length == 0 && await _reveal(Name) is { } plain) { OriginalValue = plain; Value = plain; }
        IsRevealed = true;
    }

    private bool IsDirtyBeyondReveal() => Value.Trim() != OriginalValue.Trim();

    [RelayCommand] private void Remove() => Removing = !Removing;
}

public sealed partial class ThemeOption(AppTheme value, string label, string description, string canvas, string surface, string text) : ObservableObject
{
    public AppTheme Value { get; } = value;
    public string Label { get; } = label;
    public string Description { get; } = description;
    public string Canvas { get; } = canvas;
    public string Surface { get; } = surface;
    public string Text { get; } = text;
    [ObservableProperty] public partial bool IsSelected { get; set; }
}

public sealed partial class AccentOption(AccentColor value, string hex) : ObservableObject
{
    public AccentColor Value { get; } = value;
    public string Label => Value.ToString();
    public string Hex { get; } = hex;
    [ObservableProperty] public partial bool IsSelected { get; set; }
}

public sealed partial class MediaOption(MediaType value, string label) : ObservableObject
{
    public MediaType Value { get; } = value;
    public string Label { get; } = label;
    [ObservableProperty] public partial bool IsSelected { get; set; }
}

public sealed partial class SettingsViewModel : ViewModelBase
{
    private readonly AppServices _services;

    public SettingsViewModel(AppServices services)
    {
        _services = services;
        Keys = new ObservableCollection<KeyRowViewModel>(ProviderKeys.All.Select(k => new KeyRowViewModel(k, RevealAsync)));
        string Tok(string theme, string key) => "#" + (theme == "light" ? DesignTokens.Light : DesignTokens.Dark)[key][3..];
        Themes =
        [
            new ThemeOption(AppTheme.Glass, "Glass", "Cold glass on near-black, warm sodium light.", Tok("dark", "canvas"), Tok("dark", "surface"), Tok("dark", "text")),
            new ThemeOption(AppTheme.Frost, "Frost", "Frosted glass on cool white.", Tok("light", "canvas"), Tok("light", "surface"), Tok("light", "text")),
        ];
        Accents = new ObservableCollection<AccentOption>(ThemeManager.Accents.Select(a => new AccentOption(a.Key, $"#{a.Value.R:X2}{a.Value.G:X2}{a.Value.B:X2}")));
        Media = [.. MediaLabels.Select(m => new MediaOption(m.Key, m.Value))];
        UseCases = [.. Enum.GetValues<UseCase>()];
        TierChoices = [.. Enum.GetValues<Tier>()];
        LoadFrom(services.Settings);

        foreach (var t in Themes) t.PropertyChanged += (s, e) => { if (e.PropertyName == nameof(ThemeOption.IsSelected) && s is ThemeOption { IsSelected: true }) PreviewTheme(); };
        foreach (var a in Accents) a.PropertyChanged += (s, e) => { if (e.PropertyName == nameof(AccentOption.IsSelected) && s is AccentOption { IsSelected: true }) PreviewTheme(); };
        services.Engine.StateChanged += () => Avalonia.Threading.Dispatcher.UIThread.Post(() => EngineStatus = services.Engine.StatusText);
        services.Session.Changed += () => Avalonia.Threading.Dispatcher.UIThread.Post(RefreshAccount);
        services.PrefsChanged += () => Avalonia.Threading.Dispatcher.UIThread.Post(() => LoadFrom(services.Settings));
        EngineStatus = services.Engine.StatusText;
        RefreshAccount();
    }

    private static readonly Dictionary<MediaType, string> MediaLabels = new()
    {
        [MediaType.Image] = "Images", [MediaType.Audio] = "Audio", [MediaType.Video] = "Video", [MediaType.Texture] = "Textures",
        [MediaType.Hdri] = "HDRIs", [MediaType.Model] = "3D", [MediaType.Font] = "Fonts", [MediaType.Icon] = "Icons",
    };

    public ObservableCollection<KeyRowViewModel> Keys { get; }
    public ObservableCollection<ThemeOption> Themes { get; }
    public ObservableCollection<AccentOption> Accents { get; }
    public ObservableCollection<MediaOption> Media { get; }
    public IReadOnlyList<UseCase> UseCases { get; }
    public IReadOnlyList<Tier> TierChoices { get; }

    [ObservableProperty] public partial bool IsLocal { get; set; }
    [ObservableProperty] public partial bool IsRemote { get; set; }
    [ObservableProperty] public partial string PythonCommand { get; set; } = "";
    [ObservableProperty] public partial decimal? LocalPort { get; set; }
    [ObservableProperty] public partial bool AutoStartEngine { get; set; }
    [ObservableProperty] public partial string RemoteUrl { get; set; } = "";
    [ObservableProperty] public partial string ContactEmail { get; set; } = "";
    [ObservableProperty] public partial string DownloadDirectory { get; set; } = "";
    [ObservableProperty] public partial bool OrganizeByProject { get; set; }
    [ObservableProperty] public partial decimal? MaxConcurrent { get; set; }
    [ObservableProperty] public partial bool WriteSidecars { get; set; }
    [ObservableProperty] public partial bool RecordInLedger { get; set; }
    [ObservableProperty] public partial bool WatchClipboard { get; set; }
    [ObservableProperty] public partial UseCase DefaultUseCase { get; set; }
    [ObservableProperty] public partial Tier DefaultMaxTier { get; set; }
    [ObservableProperty] public partial decimal? ResultsPerSource { get; set; }
    [ObservableProperty] public partial string EngineStatus { get; set; } = "";
    [ObservableProperty] public partial string EngineLog { get; set; } = "";
    [ObservableProperty] public partial bool IsBusy { get; set; }
    [ObservableProperty] public partial string AccountEmail { get; set; } = "";
    [ObservableProperty] public partial string AccountName { get; set; } = "";
    [ObservableProperty] public partial bool IsSignedIn { get; set; }

    /// <summary>Keys and preferences live in the account (synced) rather than on this machine.</summary>
    public bool KeysInAccount => _services.UsesAccounts && IsSignedIn;
    public int KeysSet => Keys.Count(k => k.IsSet);
    public string KeysSummary => KeysInAccount
        ? $"{KeysSet} of {Keys.Count} set · encrypted in your account, synced with freesta.sh"
        : $"{KeysSet} of {Keys.Count} set · encrypted on this computer, used by the local engine";
    public string SaveNote => KeysInAccount
        ? "Keys and preferences save to your account and sync with the website."
        : "Keys are encrypted on this computer (DPAPI on Windows) and only passed to the local engine.";
    public string ConfigPath => _services.SettingsStore.FilePath;

    partial void OnIsLocalChanged(bool value) { if (value) IsRemote = false; }
    partial void OnIsRemoteChanged(bool value) { if (value) IsLocal = false; }
    partial void OnIsSignedInChanged(bool value) { OnPropertyChanged(nameof(KeysInAccount)); OnPropertyChanged(nameof(KeysSummary)); OnPropertyChanged(nameof(SaveNote)); }

    private void RefreshAccount()
    {
        var s = _services.Session.CurrentFor(_services.Settings.ApiBaseUri);
        IsSignedIn = s is not null;
        AccountEmail = s?.User.Email ?? "";
        AccountName = s?.User.DisplayName ?? s?.User.Email?.Split('@')[0] ?? "";
        _ = LoadKeysAsync();
    }

    private void LoadFrom(AppSettings s)
    {
        IsLocal = s.Mode == ConnectionMode.Local;
        IsRemote = s.Mode == ConnectionMode.Remote;
        PythonCommand = s.PythonCommand;
        LocalPort = s.LocalPort;
        AutoStartEngine = s.AutoStartEngine;
        RemoteUrl = s.RemoteUrl;
        ContactEmail = s.ContactEmail;
        DownloadDirectory = s.DownloadDirectory;
        OrganizeByProject = s.OrganizeByProject;
        MaxConcurrent = s.MaxConcurrentDownloads;
        WriteSidecars = s.WriteSidecars;
        RecordInLedger = s.RecordInLedger;
        WatchClipboard = s.WatchClipboard;
        DefaultUseCase = s.DefaultUseCase;
        DefaultMaxTier = s.DefaultMaxTier;
        ResultsPerSource = s.ResultsPerSource;
        foreach (var m in Media) m.IsSelected = s.DefaultMedia.Contains(m.Value);
        foreach (var t in Themes) t.IsSelected = t.Value == s.Theme;
        foreach (var a in Accents) a.IsSelected = a.Value == s.Accent;
    }

    private async Task LoadKeysAsync()
    {
        if (KeysInAccount)
        {
            try
            {
                var states = (await _services.Account.Current.KeysAsync()).ToDictionary(k => k.Name);
                foreach (var k in Keys) k.LoadCloud(states.GetValueOrDefault(k.Name));
            }
            catch (Exception) { foreach (var k in Keys) k.LoadCloud(null); }
        }
        else
        {
            foreach (var k in Keys) k.LoadLocal(_services.Secrets.Get(k.Name));
        }
        OnPropertyChanged(nameof(KeysSet));
        OnPropertyChanged(nameof(KeysSummary));
    }

    private async Task<string?> RevealAsync(string name)
    {
        try { return await _services.Account.Current.RevealKeyAsync(name); }
        catch (Exception ex) { _services.Toasts.Show($"Couldn't show the key: {ex.Message}"); return null; }
    }

    private AppTheme SelectedTheme => Themes.FirstOrDefault(t => t.IsSelected)?.Value ?? AppTheme.Glass;
    private AccentColor SelectedAccent => Accents.FirstOrDefault(a => a.IsSelected)?.Value ?? AccentColor.Sodium;

    private void PreviewTheme() => _services.Theme.Apply(SelectedTheme, SelectedAccent);

    public override Task OnShownAsync()
    {
        RefreshLog();
        return LoadKeysAsync();
    }

    [RelayCommand]
    private async Task SaveAsync()
    {
        IsBusy = true;
        try
        {
            var old = _services.Settings;
            var media = Media.Where(m => m.IsSelected).Select(m => m.Value).ToList();
            var s = new AppSettings
            {
                Mode = IsRemote ? ConnectionMode.Remote : ConnectionMode.Local,
                PythonCommand = string.IsNullOrWhiteSpace(PythonCommand) ? old.PythonCommand : PythonCommand.Trim(),
                LocalPort = (int)(LocalPort ?? 8787),
                AutoStartEngine = AutoStartEngine,
                RemoteUrl = string.IsNullOrWhiteSpace(RemoteUrl) ? AppSettings.HostedUrl : RemoteUrl.Trim(),
                ContactEmail = ContactEmail.Trim(),
                DownloadDirectory = string.IsNullOrWhiteSpace(DownloadDirectory) ? AppSettings.DefaultDownloadDirectory() : DownloadDirectory.Trim(),
                OrganizeByProject = OrganizeByProject,
                MaxConcurrentDownloads = (int)Math.Clamp(MaxConcurrent ?? 3, 1, 8),
                WriteSidecars = WriteSidecars,
                RecordInLedger = RecordInLedger,
                WatchClipboard = WatchClipboard,
                LastProject = old.LastProject,
                DefaultUseCase = DefaultUseCase,
                DefaultMaxTier = DefaultMaxTier,
                DefaultMedia = media.Count > 0 ? media : [MediaType.Image],
                ResultsPerSource = (int)Math.Clamp(ResultsPerSource ?? 12, 1, 50),
                Theme = SelectedTheme,
                Accent = SelectedAccent,
            };

            var dirtyKeys = Keys.Where(k => k.IsDirty).ToList();
            var keysChanged = dirtyKeys.Count > 0 || s.ContactEmail != old.ContactEmail;
            var connectionChanged = s.Mode != old.Mode || s.LocalPort != old.LocalPort || s.RemoteUrl != old.RemoteUrl || s.PythonCommand != old.PythonCommand;

            if (KeysInAccount && s.Mode == ConnectionMode.Remote)
            {
                if (dirtyKeys.Count > 0)
                {
                    var states = (await _services.Account.Current.SaveKeysAsync(
                        dirtyKeys.ToDictionary(k => k.Name, k => k.Removing ? null : (string?)k.Value.Trim()))).ToDictionary(k => k.Name);
                    foreach (var k in Keys) k.LoadCloud(states.GetValueOrDefault(k.Name));
                }
                await _services.Account.Current.SavePrefsAsync(AppServices.PrefsFrom(s));
            }
            else
            {
                LocalKeyWrites.Apply(_services.Secrets, rowsFromAccount: KeysInAccount, Keys.Select(k => new KeyEdit(k.Name, k.Value, k.IsDirty, k.Removing)));
                foreach (var k in Keys) k.LoadLocal(_services.Secrets.Get(k.Name));
            }
            _services.SaveSettings(s);
            _services.Theme.Apply(s.Theme, s.Accent);
            OnPropertyChanged(nameof(KeysSet));
            OnPropertyChanged(nameof(KeysSummary));

            if (connectionChanged)
            {
                await _services.Engine.RestartAsync();
                _services.Session.Set(_services.Session.Current); // re-evaluate the sign-in gate for the new server
                _services.Toasts.Show("Saved. Reconnected.");
            }
            else if (s.Mode == ConnectionMode.Local && keysChanged && _services.Engine.OwnsProcess)
            {
                _services.Toasts.Show("Saved. Restarting the engine with your new keys…");
                await _services.Engine.RestartAsync();
            }
            else
            {
                _services.Toasts.Show(KeysInAccount ? "Saved to your account. The website picks it up on its next load." : "Settings saved");
            }
        }
        catch (Exception ex)
        {
            _services.Toasts.Show($"Couldn't save: {ex.Message}");
        }
        finally
        {
            IsBusy = false;
            RefreshLog();
        }
    }

    [RelayCommand]
    private async Task RevertAsync()
    {
        LoadFrom(_services.Settings);
        await LoadKeysAsync();
        _services.Theme.Apply(_services.Settings.Theme, _services.Settings.Accent);
    }

    [RelayCommand]
    private async Task RegisterOpenverseAsync()
    {
        IsBusy = true;
        try
        {
            var r = await _services.Account.Current.RegisterOpenverseAsync(KeysInAccount ? null : ContactEmail.Trim());
            if (!KeysInAccount)
            {
                foreach (var (name, value) in r.Values) _services.Secrets.Set(name, value);
                _services.Secrets.Save();
            }
            await LoadKeysAsync();
            _services.Toasts.Show(r.Next);
        }
        catch (Exception ex) { _services.Toasts.Show(ex.Message); }
        finally { IsBusy = false; }
    }

    [RelayCommand] private void SignOut() => _services.SignOut();

    [RelayCommand]
    private async Task SignOutEverywhereAsync()
    {
        try { await _services.Account.Current.SignOutEverywhereAsync(); } catch (Exception) { /* sign out here regardless */ }
        _services.SignOut();
    }

    [RelayCommand]
    private async Task TestConnectionAsync()
    {
        IsBusy = true;
        var ok = await _services.Engine.PingAsync();
        IsBusy = false;
        _services.Toasts.Show(ok ? $"Connected · {_services.Engine.StatusText}" : "No answer from the engine");
    }

    [RelayCommand]
    private async Task RestartEngineAsync()
    {
        IsBusy = true;
        await _services.Engine.RestartAsync();
        IsBusy = false;
        RefreshLog();
    }

    [RelayCommand]
    private async Task BrowseDownloadsAsync()
    {
        var picked = await _services.Platform.PickFolderAsync("Default download folder", DownloadDirectory);
        if (picked is not null) DownloadDirectory = picked;
    }

    [RelayCommand]
    private async Task OpenUrlAsync(string? url) => await _services.Platform.OpenUrlAsync(url);

    [RelayCommand]
    private async Task OpenConfigFolderAsync() => await _services.Platform.OpenFolderAsync(Path.GetDirectoryName(ConfigPath));

    [RelayCommand]
    private void RefreshLog() => EngineLog = string.Join(Environment.NewLine, _services.Engine.Log.TakeLast(60)) is { Length: > 0 } log
        ? log : _services.Engine.OwnsProcess ? "(no output yet)" : "Engine output appears here when the app starts the engine itself.";
}
