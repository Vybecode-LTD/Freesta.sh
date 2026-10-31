using Freestash.Client;
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
        Api = new ApiHolder(() => Settings, Secrets);
        Engine = new EngineHost(() => Settings, Secrets, () => Api.Current);
        Downloads = new DownloadEngine(new DownloadEngineOptions
        {
            MaxConcurrent = Settings.MaxConcurrentDownloads,
            WriteSidecars = Settings.WriteSidecars,
        });
        Downloads.AssetCompleted += RecordDownloadAsync;
    }

    public static AppServices CreateDefault() => new(AppPaths.ConfigDirectory());

    public SettingsStore SettingsStore { get; }
    public AppSettings Settings { get; private set; }
    public SecretStore Secrets { get; }
    public ApiHolder Api { get; }
    public EngineHost Engine { get; }
    public DownloadEngine Downloads { get; }
    public ThemeManager Theme { get; } = new();
    public PlatformServices Platform { get; } = new();
    public ToastService Toasts { get; } = new();
    public ImageLoader Images { get; } = new();

    public async Task StartAsync()
    {
        await Engine.EnsureRunningAsync();
    }

    public void SaveSettings(AppSettings updated)
    {
        Settings = updated;
        SettingsStore.Save(updated);
        Downloads.MaxConcurrent = updated.MaxConcurrentDownloads;
        Downloads.WriteSidecars = updated.WriteSidecars;
        Api.Invalidate();
    }

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
        Images.Dispose();
    }
}

/// <summary>Holds the current API client; rebuilt when the connection settings change.</summary>
public sealed class ApiHolder(Func<AppSettings> settings, SecretStore secrets) : IDisposable
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
                _client = new FreestashApiClient(uri, () => s.Mode == ConnectionMode.Remote ? secrets.Get(ProviderKeys.RemoteToken) : null);
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
