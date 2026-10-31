namespace Freestash.Client.Settings;

public enum ConnectionMode { Local, Remote }

public enum AppTheme { EmberDark, MachinedLight }

public enum AccentColor { Ember, Iris, Teal, Cobalt }

/// <summary>Non-secret settings, stored as JSON. API keys and tokens live in <see cref="SecretStore"/>.</summary>
public sealed class AppSettings
{
    // connection
    public ConnectionMode Mode { get; set; } = ConnectionMode.Local;
    public string PythonCommand { get; set; } = OperatingSystem.IsWindows() ? "python" : "python3";
    public int LocalPort { get; set; } = 8787;
    public bool AutoStartEngine { get; set; } = true;
    public string RemoteUrl { get; set; } = "";
    public string ContactEmail { get; set; } = "";

    // downloads
    public string DownloadDirectory { get; set; } = DefaultDownloadDirectory();
    public bool OrganizeByProject { get; set; } = true;
    public int MaxConcurrentDownloads { get; set; } = 3;
    public bool WriteSidecars { get; set; } = true;
    public bool RecordInLedger { get; set; } = true;
    public bool WatchClipboard { get; set; }
    public string LastProject { get; set; } = "";

    // search defaults
    public UseCase DefaultUseCase { get; set; } = UseCase.Demo;
    public Tier DefaultMaxTier { get; set; } = Tier.Yellow;
    public int ResultsPerSource { get; set; } = 12;

    // appearance
    public AppTheme Theme { get; set; } = AppTheme.EmberDark;
    public AccentColor Accent { get; set; } = AccentColor.Ember;

    public Uri ApiBaseUri => Mode == ConnectionMode.Remote && Uri.TryCreate(RemoteUrl, UriKind.Absolute, out var u)
        ? u
        : new Uri($"http://127.0.0.1:{LocalPort}");

    public string DirectoryFor(string? project) =>
        OrganizeByProject && !string.IsNullOrWhiteSpace(project)
            ? Path.Combine(DownloadDirectory, Downloads.FileNames.Sanitize(project) ?? "unsorted")
            : DownloadDirectory;

    public static string DefaultDownloadDirectory()
    {
        var home = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        var downloads = Path.Combine(home, "Downloads");
        return Path.Combine(Directory.Exists(downloads) ? downloads : home, "Freestash");
    }
}
