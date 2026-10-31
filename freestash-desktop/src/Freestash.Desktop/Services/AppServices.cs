using Freestash.Client;
using Freestash.Client.Account;
using Freestash.Client.Downloads;
using Freestash.Client.Engine;
using Freestash.Client.Settings;

namespace Freestash.Desktop.Services;

/// <summary>App-wide singletons. Built once at startup (or by the snapshot tool with overrides).</summary>
public sealed class AppServices : IAsyncDisposable
{
    public AppServices(string configDirectory)
    {
        SettingsStore = new SettingsStore(configDirectory);
        Settings = SettingsStore.Load();
        Secrets = new SecretStore(configDirectory);
        Session = new SessionStore(Secrets);
        Api = new ApiHolder(() => Settings, Session);
        Account = new AccountHolder(() => Settings, Session);
        Engine = new EngineHost(() => Settings, Secrets, () => Api.Current);
        Downloads = new DownloadEngine(new DownloadEngineOptions
        {
            MaxConcurrent = Settings.MaxConcurrentDownloads,
            WriteSidecars = Settings.WriteSidecars,
        });
        Downloads.AssetCompleted += RecordDownloadAsync;
    }

    /// <summary>FREESTASH_DESKTOP_HOME points a dev or test run at its own settings, secrets and session.</summary>
    public static AppServices CreateDefault() => new(AppPaths.ConfigDirectory(Environment.GetEnvironmentVariable("FREESTASH_DESKTOP_HOME") is { Length: > 0 } home ? home : null));

    public SettingsStore SettingsStore { get; }
    public AppSettings Settings { get; private set; }
    public SecretStore Secrets { get; }
    public SessionStore Session { get; }
    public ApiHolder Api { get; }
    public AccountHolder Account { get; }
    public EngineHost Engine { get; }
    public DownloadEngine Downloads { get; }
    public ThemeManager Theme { get; } = new();
    public PlatformServices Platform { get; } = new();
    public ToastService Toasts { get; } = new();
    public ImageLoader Images { get; } = new();

    /// <summary>Signed-in accounts live on a Freesta.sh server; the local engine has no accounts.</summary>
    public bool UsesAccounts => Settings.Mode == ConnectionMode.Remote;

    /// <summary>True when the app has to show the sign-in screen before anything else.</summary>
    public bool NeedsSignIn => UsesAccounts && !Session.IsSignedIn;

    public async Task StartAsync()
    {
        await Engine.EnsureRunningAsync();
        if (UsesAccounts && Session.IsSignedIn) await RefreshAccountAsync();
    }

    /// <summary>On launch and after sign-in: re-check the session (a 401 signs out) and pull the account's preferences.</summary>
    public async Task RefreshAccountAsync()
    {
        try
        {
            Session.UpdateUser(await Account.Current.MeAsync());
            ApplyPrefs((await Account.Current.PrefsAsync()).Data);
        }
        catch (FreestashApiException ex) when (ex.Status == 401) { /* SessionExpired already signed out */ }
        catch (Exception) { /* offline: keep the cached session and settings */ }
    }

    public async Task SignedInAsync(Session session)
    {
        Session.Set(session);
        Api.Invalidate();
        await RefreshAccountAsync();
    }

    public void SignOut() { Session.Set(null); Api.Invalidate(); }

    public void SaveSettings(AppSettings updated)
    {
        Settings = updated;
        SettingsStore.Save(updated);
        Downloads.MaxConcurrent = updated.MaxConcurrentDownloads;
        Downloads.WriteSidecars = updated.WriteSidecars;
        Api.Invalidate();
        Account.Invalidate();
    }

    /// <summary>The account's copy wins on pull: preferences follow the account between web and desktop.</summary>
    public void ApplyPrefs(UserPrefs p)
    {
        var s = SettingsStore.Load();
        s.DefaultUseCase = p.DefaultUseCase;
        s.DefaultMaxTier = p.DefaultMaxTier;
        s.DefaultMedia = p.DefaultMedia.Count > 0 ? p.DefaultMedia : [MediaType.Image];
        s.ResultsPerSource = p.ResultsPerSource;
        s.Theme = p.Theme == "light" ? AppTheme.Frost : AppTheme.Glass;
        s.Accent = Enum.TryParse<AccentColor>(p.Accent, ignoreCase: true, out var a) ? a : AccentColor.Sodium;
        SaveSettings(s);
        Theme.Apply(s.Theme, s.Accent);
        PrefsChanged?.Invoke();
    }

    public event Action? PrefsChanged;

    public static UserPrefs PrefsFrom(AppSettings s) => new(
        s.DefaultUseCase, s.DefaultMaxTier, s.DefaultMedia, s.ResultsPerSource,
        ThemeManager.TokenName(s.Theme), ThemeManager.TokenName(s.Accent));

    private async Task RecordDownloadAsync(DownloadJob job)
    {
        if (!Settings.RecordInLedger || job.Asset is null) return;
        try
        {
            await Api.Current.RecordAsync(job.Asset.Asset, job.UseCase, job.Project, job.Url.AbsoluteUri);
            job.MarkRecorded();
        }
        catch (Exception ex)
        {
            Toasts.Show($"Downloaded, but couldn't record in the ledger: {ex.Message}");
        }
    }

    public async ValueTask DisposeAsync()
    {
        Downloads.Dispose();
        await Engine.DisposeAsync();
        Api.Dispose();
        Account.Dispose();
        Images.Dispose();
    }
}

/// <summary>Holds the current API client; rebuilt when the connection settings change.</summary>
public sealed class ApiHolder(Func<AppSettings> settings, SessionStore session) : IDisposable
{
    private FreestashApiClient? _client;
    private Uri? _builtFor;

    public IFreestashApi Current
    {
        get
        {
            if (Override is not null) return Override;
            var s = settings();
            var uri = s.ApiBaseUri;
            if (_client is null || _builtFor != uri)
            {
                _client?.Dispose();
                _client = new FreestashApiClient(uri, () => settings().Mode == ConnectionMode.Remote ? session.Token : null);
                _builtFor = uri;
            }
            return _client;
        }
    }

    /// <summary>Test seam: lets the snapshot tool or tests swap in any IFreestashApi.</summary>
    public IFreestashApi? Override { get; set; }

    public void Invalidate() => _builtFor = null;

    public void Dispose() => _client?.Dispose();
}

/// <summary>Holds the account client for the current server. A 401 from it signs the user out.</summary>
public sealed class AccountHolder(Func<AppSettings> settings, SessionStore session) : IDisposable
{
    private AccountClient? _client;
    private Uri? _builtFor;

    public AccountClient Current
    {
        get
        {
            var uri = settings().ApiBaseUri;
            if (_client is null || _builtFor != uri)
            {
                _client?.Dispose();
                _client = new AccountClient(uri, () => session.Token, Handler);
                _client.SessionExpired += () => session.Set(null);
                _builtFor = uri;
            }
            return _client;
        }
    }

    /// <summary>Test seam: a fake HTTP handler for the snapshot tool.</summary>
    public HttpMessageHandler? Handler { get; set; }

    public void Invalidate() => _builtFor = null;

    public void Dispose() => _client?.Dispose();
}
