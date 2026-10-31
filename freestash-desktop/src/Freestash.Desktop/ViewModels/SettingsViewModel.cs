using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Freestash.Client;
using Freestash.Client.Settings;
using Freestash.Desktop.Services;

namespace Freestash.Desktop.ViewModels;

public sealed partial class ProviderKeyViewModel(ProviderKey key, string? value) : ObservableObject
{
    public ProviderKey Key { get; } = key;
    public string Provider => Key.Provider;
    public string Label => Key.Label;
    public string Hint => Key.Hint;
    public string EnvVar => Key.EnvVar;
    public string SignupUrl => Key.SignupUrl;
    public bool Optional => Key.Optional;
    public string OriginalValue { get; private set; } = value ?? "";

    [ObservableProperty] public partial string Value { get; set; } = value ?? "";
    [ObservableProperty] public partial bool IsRevealed { get; set; }

    public bool HasValue => !string.IsNullOrWhiteSpace(Value);
    public char Mask => IsRevealed ? '\0' : '•';
    public string StatusText => HasValue ? "SET" : Optional ? "OPTIONAL" : "MISSING";
    public bool IsDirty => Value.Trim() != OriginalValue.Trim();

    partial void OnValueChanged(string value) { OnPropertyChanged(nameof(HasValue)); OnPropertyChanged(nameof(StatusText)); }
    partial void OnIsRevealedChanged(bool value) => OnPropertyChanged(nameof(Mask));

    public void MarkSaved() => OriginalValue = Value;

    [RelayCommand] private void ToggleReveal() => IsRevealed = !IsRevealed;
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

public sealed partial class SettingsViewModel : ViewModelBase
{
    private readonly AppServices _services;

    public SettingsViewModel(AppServices services)
    {
        _services = services;
        Keys = new ObservableCollection<ProviderKeyViewModel>(ProviderKeys.All.Select(k => new ProviderKeyViewModel(k, services.Secrets.Get(k.EnvVar))));
        Themes =
        [
            new ThemeOption(AppTheme.EmberDark, "Ember Dark", "#0a0a0a canvas, quiet warm greys, Ember accent.", "#0A0A0A", "#191816", "#F3F1EE"),
            new ThemeOption(AppTheme.MachinedLight, "Machined Light", "Warm graphite, raised machined surfaces, carved inputs.", "#D3CEC6", "#ECE9E3", "#1D1A17"),
        ];
        Accents = new ObservableCollection<AccentOption>(ThemeManager.Accents.Select(a => new AccentOption(a.Key, $"#{a.Value.R:X2}{a.Value.G:X2}{a.Value.B:X2}")));
        UseCases = [.. Enum.GetValues<UseCase>()];
        TierChoices = [.. Enum.GetValues<Tier>()];
        LoadFrom(services.Settings);

        foreach (var t in Themes) t.PropertyChanged += (s, e) => { if (e.PropertyName == nameof(ThemeOption.IsSelected) && s is ThemeOption { IsSelected: true }) PreviewTheme(); };
        foreach (var a in Accents) a.PropertyChanged += (s, e) => { if (e.PropertyName == nameof(AccentOption.IsSelected) && s is AccentOption { IsSelected: true }) PreviewTheme(); };
        services.Engine.StateChanged += () => Avalonia.Threading.Dispatcher.UIThread.Post(() => EngineStatus = services.Engine.StatusText);
        EngineStatus = services.Engine.StatusText;
    }

    public ObservableCollection<ProviderKeyViewModel> Keys { get; }
    public ObservableCollection<ThemeOption> Themes { get; }
    public ObservableCollection<AccentOption> Accents { get; }
    public IReadOnlyList<UseCase> UseCases { get; }
    public IReadOnlyList<Tier> TierChoices { get; }

    [ObservableProperty] public partial bool IsLocal { get; set; }
    [ObservableProperty] public partial bool IsRemote { get; set; }
    [ObservableProperty] public partial string PythonCommand { get; set; } = "";
    [ObservableProperty] public partial decimal? LocalPort { get; set; }
    [ObservableProperty] public partial bool AutoStartEngine { get; set; }
    [ObservableProperty] public partial string RemoteUrl { get; set; } = "";
    [ObservableProperty] public partial string RemoteToken { get; set; } = "";
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

    public int KeysSet => Keys.Count(k => k.HasValue);
    public string KeysSummary => $"{KeysSet} of {Keys.Count} set · stored encrypted on this machine";
    public string ConfigPath => _services.SettingsStore.FilePath;

    partial void OnIsLocalChanged(bool value) { if (value) IsRemote = false; }
    partial void OnIsRemoteChanged(bool value) { if (value) IsLocal = false; }

    private void LoadFrom(AppSettings s)
    {
        IsLocal = s.Mode == ConnectionMode.Local;
        IsRemote = s.Mode == ConnectionMode.Remote;
        PythonCommand = s.PythonCommand;
        LocalPort = s.LocalPort;
        AutoStartEngine = s.AutoStartEngine;
        RemoteUrl = s.RemoteUrl;
        RemoteToken = _services.Secrets.Get(ProviderKeys.RemoteToken) ?? "";
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
        foreach (var t in Themes) t.IsSelected = t.Value == s.Theme;
        foreach (var a in Accents) a.IsSelected = a.Value == s.Accent;
    }

    private AppTheme SelectedTheme => Themes.FirstOrDefault(t => t.IsSelected)?.Value ?? AppTheme.EmberDark;
    private AccentColor SelectedAccent => Accents.FirstOrDefault(a => a.IsSelected)?.Value ?? AccentColor.Ember;

    private void PreviewTheme() => _services.Theme.Apply(SelectedTheme, SelectedAccent);

    public override Task OnShownAsync()
    {
        RefreshLog();
        return Task.CompletedTask;
    }

    [RelayCommand]
    private async Task SaveAsync()
    {
        IsBusy = true;
        try
        {
            var old = _services.Settings;
            var s = new AppSettings
            {
                Mode = IsRemote ? ConnectionMode.Remote : ConnectionMode.Local,
                PythonCommand = string.IsNullOrWhiteSpace(PythonCommand) ? old.PythonCommand : PythonCommand.Trim(),
                LocalPort = (int)(LocalPort ?? 8787),
                AutoStartEngine = AutoStartEngine,
                RemoteUrl = RemoteUrl.Trim(),
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
                ResultsPerSource = (int)Math.Clamp(ResultsPerSource ?? 12, 1, 50),
                Theme = SelectedTheme,
                Accent = SelectedAccent,
            };

            var keysChanged = Keys.Any(k => k.IsDirty) || s.ContactEmail != old.ContactEmail;
            var connectionChanged = s.Mode != old.Mode || s.LocalPort != old.LocalPort || s.RemoteUrl != old.RemoteUrl ||
                                    s.PythonCommand != old.PythonCommand || RemoteToken != (_services.Secrets.Get(ProviderKeys.RemoteToken) ?? "");

            foreach (var k in Keys) { _services.Secrets.Set(k.EnvVar, k.Value); k.MarkSaved(); }
            _services.Secrets.Set(ProviderKeys.RemoteToken, RemoteToken);
            _services.Secrets.Save();
            _services.SaveSettings(s);
            _services.Theme.Apply(s.Theme, s.Accent);
            OnPropertyChanged(nameof(KeysSet));
            OnPropertyChanged(nameof(KeysSummary));

            if (s.Mode == ConnectionMode.Local && (keysChanged || connectionChanged) && (_services.Engine.OwnsProcess || connectionChanged))
            {
                _services.Toasts.Show("Saved. Restarting the engine with your new keys…");
                await _services.Engine.RestartAsync();
            }
            else if (connectionChanged)
            {
                await _services.Engine.EnsureRunningAsync();
                _services.Toasts.Show("Saved");
            }
            else
            {
                _services.Toasts.Show(keysChanged && !_services.Engine.OwnsProcess && s.Mode == ConnectionMode.Local
                    ? "Saved. The engine was started outside the app, so restart it to pick up new keys."
                    : "Settings saved");
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
    private void Revert()
    {
        LoadFrom(_services.Settings);
        foreach (var k in Keys) k.Value = _services.Secrets.Get(k.EnvVar) ?? "";
        _services.Theme.Apply(_services.Settings.Theme, _services.Settings.Accent);
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
