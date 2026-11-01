using Freestash.Client.Engine;
using Freestash.Client.Settings;

namespace Freestash.Client.Tests;

public class SettingsTests : IDisposable
{
    private readonly string _dir = Directory.CreateTempSubdirectory("freestash-settings-").FullName;

    public void Dispose() => Directory.Delete(_dir, true);

    [Fact]
    public void Settings_saved_before_the_Aperture_rename_still_load()
    {
        File.WriteAllText(Path.Combine(_dir, "settings.json"),
            """{"Mode":"Remote","RemoteUrl":"https://team.example","DownloadDirectory":"D:\\Assets","Theme":"MachinedLight","Accent":"Ember"}""");

        var s = new SettingsStore(_dir).Load();

        Assert.Equal(AppTheme.Frost, s.Theme);
        Assert.Equal(AccentColor.Sodium, s.Accent);
        Assert.Equal("https://team.example", s.RemoteUrl); // the rest of the file survives, not just the look
        Assert.Equal(@"D:\Assets", s.DownloadDirectory);
        Assert.False(File.Exists(Path.Combine(_dir, "settings.json.corrupt")));
    }

    [Fact]
    public void Switching_from_the_account_to_the_local_engine_keeps_this_machines_keys()
    {
        var secrets = new SecretStore(_dir);
        secrets.Set("PEXELS_API_KEY", "local-pexels");
        secrets.Save();

        // the account's rows are masked: empty values, even for keys the account has set
        LocalKeyWrites.Apply(secrets, rowsFromAccount: true,
            [new("PEXELS_API_KEY", "", Dirty: false, Removing: false), new("UNSPLASH_ACCESS_KEY", "", Dirty: false, Removing: false)]);

        Assert.Equal("local-pexels", new SecretStore(_dir).Get("PEXELS_API_KEY"));
    }

    [Fact]
    public void Local_rows_write_only_what_the_user_changed()
    {
        var secrets = new SecretStore(_dir);
        secrets.Set("PEXELS_API_KEY", "old");
        secrets.Set("PIXABAY_API_KEY", "keep");
        secrets.Save();

        LocalKeyWrites.Apply(secrets, rowsFromAccount: false,
            [new("PEXELS_API_KEY", "new", Dirty: true, Removing: false), new("PIXABAY_API_KEY", "keep", Dirty: false, Removing: false),
             new("FREESOUND_API_KEY", "", Dirty: true, Removing: true)]);

        var reloaded = new SecretStore(_dir);
        Assert.Equal("new", reloaded.Get("PEXELS_API_KEY"));
        Assert.Equal("keep", reloaded.Get("PIXABAY_API_KEY"));
        Assert.Null(reloaded.Get("FREESOUND_API_KEY"));
    }

    [Fact]
    public void Secrets_round_trip_encrypted_at_rest()
    {
        var store = new SecretStore(_dir);
        store.Set("UNSPLASH_ACCESS_KEY", "  abc123-secret  ");
        store.Set("PEXELS_API_KEY", "");
        store.Save();

        var raw = File.ReadAllBytes(Path.Combine(_dir, "secrets.bin"));
        Assert.DoesNotContain("abc123-secret", System.Text.Encoding.UTF8.GetString(raw));

        var reloaded = new SecretStore(_dir);
        Assert.Equal("abc123-secret", reloaded.Get("UNSPLASH_ACCESS_KEY"));
        Assert.Null(reloaded.Get("PEXELS_API_KEY"));
    }

    [Fact]
    public void Unreadable_secrets_start_empty_and_keep_a_backup()
    {
        File.WriteAllBytes(Path.Combine(_dir, "secrets.bin"), [2, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30]);
        var store = new SecretStore(_dir);
        Assert.Empty(store.All);
        Assert.True(File.Exists(Path.Combine(_dir, "secrets.bin.unreadable")));
    }

    [Fact]
    public void Settings_round_trip_and_project_folders()
    {
        var store = new SettingsStore(_dir);
        var s = store.Load();
        s.Theme = AppTheme.Frost;
        s.DownloadDirectory = Path.Combine(_dir, "dl");
        store.Save(s);
        var again = store.Load();
        Assert.Equal(AppTheme.Frost, again.Theme);
        Assert.Equal(Path.Combine(_dir, "dl", "aurora-template"), again.DirectoryFor("aurora-template"));
        again.OrganizeByProject = false;
        Assert.Equal(Path.Combine(_dir, "dl"), again.DirectoryFor("aurora-template"));
    }

    [Fact]
    public void Engine_environment_carries_keys_and_identity_only()
    {
        var secrets = new SecretStore(_dir);
        secrets.Set("SMITHSONIAN_API_KEY", "si-key");
        new Freestash.Client.Account.SessionStore(secrets).Set(new("account-jwt", new("u1", "a@b.co", null, null), "https://freesta.sh"));
        var settings = new AppSettings { ContactEmail = "studio@example.com" };
        var host = new EngineHost(() => settings, secrets, () => throw new InvalidOperationException());
        var env = host.BuildEnvironment();
        Assert.Equal("si-key", env["SMITHSONIAN_API_KEY"]);
        Assert.Equal("studio@example.com", env["FREESTASH_CONTACT_EMAIL"]);
        Assert.Equal("none", env["FREESTASH_AUTH_MODE"]);
        Assert.DoesNotContain(env.Values, v => v.Contains("account-jwt")); // the account session never leaks into the local engine
    }

    [Fact]
    public void Remote_mode_uses_remote_url()
    {
        var s = new AppSettings { Mode = ConnectionMode.Remote, RemoteUrl = "https://freestash.example.app" };
        Assert.Equal("https://freestash.example.app/", s.ApiBaseUri.ToString());
        s.Mode = ConnectionMode.Local;
        Assert.Equal("http://127.0.0.1:8787/", s.ApiBaseUri.ToString());
    }
}
