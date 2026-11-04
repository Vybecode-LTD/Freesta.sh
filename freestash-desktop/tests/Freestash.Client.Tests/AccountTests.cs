using System.Net;
using System.Text;
using Freestash.Client.Account;
using Freestash.Client.Settings;

namespace Freestash.Client.Tests;

/// <summary>The desktop side of one account across web and desktop: client calls, session storage, the key catalog.</summary>
public class AccountTests : IDisposable
{
    private readonly string _dir = Directory.CreateTempSubdirectory("freestash-account-").FullName;

    private static CancellationToken Ct => TestContext.Current.CancellationToken;

    public void Dispose() => Directory.Delete(_dir, true);

    private sealed class FakeServer : HttpMessageHandler
    {
        public List<(HttpMethod Method, string Path, string? Auth, string Body)> Calls { get; } = [];
        public Func<HttpRequestMessage, (HttpStatusCode, string)> Respond { get; set; } = _ => (HttpStatusCode.OK, "{}");

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            var body = request.Content is null ? "" : await request.Content.ReadAsStringAsync(ct);
            Calls.Add((request.Method, request.RequestUri!.AbsolutePath, request.Headers.Authorization?.Parameter, body));
            var (code, json) = Respond(request);
            return new HttpResponseMessage(code) { Content = new StringContent(json, Encoding.UTF8, "application/json") };
        }
    }

    [Fact]
    public async Task Login_sends_credentials_without_a_token_and_returns_the_session()
    {
        var server = new FakeServer
        {
            Respond = _ => (HttpStatusCode.OK, """{"access_token":"jwt-1","token_type":"bearer","user":{"id":"u1","email":"ada@example.com","display_name":"Ada","created_at":null}}"""),
        };
        using var client = new AccountClient(new Uri("https://freesta.sh"), () => "stale", server);

        var session = await client.LoginAsync("ada@example.com", "pw", Ct);

        Assert.Equal("jwt-1", session.Token);
        Assert.Equal("Ada", session.User.DisplayName);
        var call = Assert.Single(server.Calls);
        Assert.Equal("/api/auth/login", call.Path);
        Assert.Null(call.Auth); // sign-in never sends an old token
        Assert.Contains("\"email\":\"ada@example.com\"", call.Body);
    }

    [Fact]
    public async Task Account_calls_send_the_token_and_use_the_web_apps_json()
    {
        var server = new FakeServer
        {
            Respond = r => r.RequestUri!.AbsolutePath switch
            {
                "/api/me/settings" => (HttpStatusCode.OK, """{"data":{"default_use_case":"bundled","default_max_tier":"green","default_media":["audio"],"results_per_source":20,"theme":"light","accent":"teal"},"updated_at":"2026-10-31T00:00:00Z"}"""),
                "/api/me/keys" => (HttpStatusCode.OK, """{"keys":[{"name":"PEXELS_API_KEY","set":true,"hint":"1234","updated_at":null}]}"""),
                _ => (HttpStatusCode.OK, "{}"),
            },
        };
        using var client = new AccountClient(new Uri("https://freesta.sh"), () => "jwt-1", server);

        var prefs = (await client.PrefsAsync(Ct)).Data;
        Assert.Equal((UseCase.Bundled, Tier.Green, "light", "teal"), (prefs.DefaultUseCase, prefs.DefaultMaxTier, prefs.Theme, prefs.Accent));
        Assert.Equal([MediaType.Audio], prefs.DefaultMedia);

        await client.SavePrefsAsync(prefs with { Accent = "iris" }, Ct);
        Assert.Contains("\"data\":{\"default_use_case\":\"bundled\"", server.Calls[^1].Body);

        var keys = await client.SaveKeysAsync(new Dictionary<string, string?> { ["PEXELS_API_KEY"] = "new-key", ["UNSPLASH_ACCESS_KEY"] = null }, Ct);
        Assert.Equal("1234", Assert.Single(keys).Hint);
        Assert.Contains("\"values\":{\"PEXELS_API_KEY\":\"new-key\"", server.Calls[^1].Body);
        Assert.All(server.Calls, c => Assert.Equal("jwt-1", c.Auth));
    }

    [Theory]
    // (saved, hint, removing, site, optional) -> what the row says; same words as the web's lib/admin.ts::memberKeyStatus
    [InlineData(true, "1234", true, true, true, KeyTone.Removing, "WILL BE REMOVED")] // PR #6 review: no label showed
    [InlineData(true, "1234", true, false, false, KeyTone.Removing, "WILL BE REMOVED")]
    [InlineData(true, "1234", false, true, false, KeyTone.Set, "YOURS · …1234")]
    [InlineData(true, null, false, false, false, KeyTone.Set, "SET")] // local engine: no hint, the value is on this machine
    [InlineData(false, null, false, true, false, KeyTone.Site, "FREESTA.SH'S KEY")]
    [InlineData(false, null, false, false, true, KeyTone.Optional, "OPTIONAL")]
    [InlineData(false, null, false, false, false, KeyTone.Missing, "NOT SET")]
    public void Every_key_row_shows_exactly_one_status(bool saved, string? hint, bool removing, bool site, bool optional,
                                                      KeyTone tone, string text)
    {
        Assert.Equal((tone, text), KeyStatus.For(saved, hint, removing, site, optional));
    }

    [Fact]
    public async Task Key_rows_say_when_freesta_sh_has_its_own_key()
    {
        // Decision 0003: members search on the site's keys; each row says whether the site covers it.
        var server = new FakeServer
        {
            Respond = _ => (HttpStatusCode.OK, """{"keys":[{"name":"PEXELS_API_KEY","set":false,"hint":null,"updated_at":null,"site":true},{"name":"UNSPLASH_ACCESS_KEY","set":false,"hint":null,"updated_at":null}]}"""),
        };
        using var client = new AccountClient(new Uri("https://freesta.sh"), () => "jwt-1", server);

        var keys = await client.KeysAsync(Ct);

        Assert.True(keys[0].Site);
        Assert.False(keys[1].Site); // an older server without the field: not covered
    }

    [Fact]
    public async Task A_401_raises_SessionExpired_so_the_app_signs_out()
    {
        var server = new FakeServer { Respond = _ => (HttpStatusCode.Unauthorized, """{"detail":"Your session has expired. Sign in again."}""") };
        using var client = new AccountClient(new Uri("https://freesta.sh"), () => "revoked", server);
        var expired = 0;
        client.SessionExpired += () => expired++;

        var ex = await Assert.ThrowsAsync<FreestashApiException>(() => client.MeAsync(Ct));

        Assert.Equal(401, ex.Status);
        Assert.Equal("Your session has expired. Sign in again.", ex.Message);
        Assert.Equal(1, expired);
    }

    [Fact]
    public void Session_is_kept_encrypted_with_the_secrets_and_survives_a_restart()
    {
        var store = new SessionStore(new SecretStore(_dir));
        var changed = 0;
        store.Changed += () => changed++;
        store.Set(new Session("jwt-xyz", new SessionUser("u1", "ada@example.com", "Ada", null), "https://freesta.sh"));

        Assert.DoesNotContain("jwt-xyz", Encoding.UTF8.GetString(File.ReadAllBytes(Path.Combine(_dir, "secrets.bin"))));
        var again = new SessionStore(new SecretStore(_dir));
        Assert.Equal("jwt-xyz", again.TokenFor(Hosted));
        Assert.Equal("Ada", again.Current!.User.DisplayName);

        again.Set(null);
        Assert.Null(new SessionStore(new SecretStore(_dir)).Current);
        Assert.Equal(1, changed);
    }

    private static readonly Uri Hosted = new("https://freesta.sh");

    [Fact]
    public async Task A_session_remembers_the_server_that_issued_it()
    {
        var server = new FakeServer { Respond = _ => (HttpStatusCode.OK, """{"access_token":"jwt-1","token_type":"bearer","user":{"id":"u1","email":"a@b.co","display_name":null,"created_at":null}}""") };
        using var client = new AccountClient(new Uri("https://Freesta.sh/"), () => null, server);

        Assert.Equal("https://freesta.sh", (await client.LoginAsync("a@b.co", "pw", Ct)).Server);
    }

    [Fact]
    public void The_token_is_only_ever_handed_to_the_server_that_issued_it()
    {
        var store = new SessionStore(new SecretStore(_dir));
        store.Set(new Session("freesta-jwt", new SessionUser("u1", "a@b.co", null, null), "https://freesta.sh"));

        Assert.Equal("freesta-jwt", store.TokenFor(new Uri("https://FREESTA.sh/api/")));
        Assert.Null(store.TokenFor(new Uri("https://other-server.example"))); // pointing the app elsewhere doesn't leak it
        Assert.Null(store.TokenFor(new Uri("http://freesta.sh")));            // nor over plain http
        store.Set(new Session("legacy", new SessionUser("u1", "a@b.co", null, null))); // no issuer recorded
        Assert.Null(store.TokenFor(Hosted));
    }

    [Fact]
    public void Key_catalog_is_the_shared_one_with_its_help_text()
    {
        var all = ProviderKeys.All;
        Assert.Equal(10, all.Count);
        Assert.All(all, k =>
        {
            Assert.StartsWith("https://", k.Url);
            Assert.NotEmpty(k.Steps);
            Assert.False(string.IsNullOrWhiteSpace(k.UrlLabel));
        });
        Assert.Contains("paused", all.Single(k => k.Name == "PEXELS_API_KEY").Notice);
        Assert.Equal("openverse_register", all.Single(k => k.Name == "OPENVERSE_CLIENT_ID").Action);
        Assert.True(all.Single(k => k.Name == "WIKIMEDIA_ACCESS_TOKEN").Optional);
        var github = all.Single(k => k.Name == "GITHUB_ACCESS_TOKEN"); // PR #9: optional, raises GitHub's search limit
        Assert.True(github.Optional);
        Assert.Equal("github", github.Provider);
    }

    [Fact]
    public void New_installs_use_the_hosted_engine_at_freesta_sh()
    {
        var s = new AppSettings();
        Assert.Equal(ConnectionMode.Remote, s.Mode);
        Assert.Equal("https://freesta.sh/", s.ApiBaseUri.ToString());
        Assert.Equal((AppTheme.Glass, AccentColor.Sodium), (s.Theme, s.Accent));
    }
}
