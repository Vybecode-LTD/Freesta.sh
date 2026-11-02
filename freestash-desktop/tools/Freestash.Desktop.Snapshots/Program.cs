// Headless visual check: boots the real app with Skia rendering, drives it against a running Freestash engine,
// and writes a PNG per screen. Usage:
//   python -m freestash serve --port 8787          (in the freestash repo)
//   dotnet run --project tools/Freestash.Desktop.Snapshots -- http://127.0.0.1:8787 docs/screenshots [http://127.0.0.1:8790]
// The third argument is an accounts-mode server (freestash/scripts/dev_accounts.py): signs up through the real
// sign-in screen, saves a key and an accent from Settings, and reads them back through the account API.

using System.Reflection;
using Avalonia;
using Avalonia.Headless;
using Avalonia.Media;
using Avalonia.Threading;
using Freestash.Client;
using Freestash.Client.Downloads;
using Freestash.Client.Settings;
using Freestash.Desktop;
using Freestash.Desktop.Services;
using Freestash.Desktop.ViewModels;

var api = new Uri(args.Length > 0 ? args[0] : "http://127.0.0.1:8787");
var outDir = Path.GetFullPath(args.Length > 1 ? args[1] : "docs/screenshots");
var accountsUrl = args.Length > 2 ? args[2] : null; // optional: an accounts-mode server, for the sign-in + sync phase
Directory.CreateDirectory(outDir);

AppBuilder.Configure<App>()
    .UseSkia()
    .UseHeadless(new AvaloniaHeadlessPlatformOptions { UseHeadlessDrawing = false })
    .With(new FontManagerOptions { DefaultFamilyName = App.UiFont })
    .SetupWithoutStarting();

var configDir = Directory.CreateTempSubdirectory("freestash-snap-").FullName;
var services = new AppServices(configDir);
services.Settings.Mode = ConnectionMode.Local;
services.Settings.LocalPort = api.Port;
services.Settings.AutoStartEngine = false;
services.Settings.DownloadDirectory = Path.Combine(configDir, "downloads");
services.Settings.ContactEmail = "studio@example.com";
services.Secrets.Set("UNSPLASH_ACCESS_KEY", "demo-key-not-real");
services.Secrets.Set("SMITHSONIAN_API_KEY", "demo-key-not-real");

var window = App.CreateMainWindow(services);
window.Width = 1440;
window.Height = 920;
var vm = (MainWindowViewModel)window.DataContext!;
window.Show();

var done = new CancellationTokenSource();
var failed = false;

Dispatcher.UIThread.Post(async () =>
{
    try { await Script(); }
    catch (Exception ex) { Console.Error.WriteLine($"SNAPSHOT FAILED: {ex}"); failed = true; }
    finally { done.Cancel(); }
});
Dispatcher.UIThread.MainLoop(done.Token);
await services.DisposeAsync();
return failed ? 1 : 0;

async Task Wait(int ms)
{
    var until = DateTime.UtcNow.AddMilliseconds(ms);
    while (DateTime.UtcNow < until) await Task.Delay(50);
}

async Task Shot(string name)
{
    await Wait(400);
    AvaloniaHeadlessPlatform.ForceRenderTimerTick();
    var frame = window.CaptureRenderedFrame();
#pragma warning disable CS0618 // PNG default encoder is what we want here
    frame?.Save(Path.Combine(outDir, name));
#pragma warning restore CS0618
    Console.WriteLine($"  saved {name}");
}

async Task WaitFor(Func<bool> condition, int timeoutMs, string what)
{
    var until = DateTime.UtcNow.AddMilliseconds(timeoutMs);
    while (!condition())
    {
        if (DateTime.UtcNow > until) { Console.WriteLine($"  (timed out waiting for {what})"); return; }
        await Task.Delay(100);
    }
}

void Go(ViewModelBase page) => vm.Navigate(vm.NavItems.Append(vm.SettingsItem).First(n => ReferenceEquals(n.Page, page)));

async Task Script()
{
    await services.Engine.EnsureRunningAsync();
    Console.WriteLine($"engine: {services.Engine.StatusText}");
    await Shot("01-search-empty.png");

    // ---- live search
    vm.Search.Query = "lighthouse";
    await vm.Search.SearchAsync();
    await WaitFor(() => !vm.Search.IsSearching, 60_000, "search");
    Console.WriteLine($"  results: {vm.Search.Results.Count}");
    await Wait(9000); // let thumbnails stream in
    await Shot("02-search-results.png");

    // ---- detail panel
    var card = vm.Search.Results.FirstOrDefault(r => r.Asset.Provider is "cleveland" or "smk" or "met") ?? vm.Search.Results.First();
    await vm.Search.OpenCommand.ExecuteAsync(card);
    await WaitFor(() => vm.Search.Detail is { IsLoading: false }, 30_000, "detail");
    await Wait(3500);
    await Shot("03-detail.png");

    // ---- downloads: a real asset, a plain pasted link, and a host that blocks bots
    vm.Search.Detail!.Project = "aurora-template";
    vm.Search.Detail.DownloadBestCommand.Execute(null);
    vm.Downloads.PasteText = "Here are the textures:\nhttps://dl.polyhaven.org/file/ph-assets/Textures/jpg/1k/concrete_floor_02/concrete_floor_02_diff_1k.jpg\n" +
                             "and https://www.artic.edu/iiif/2/0558d3c0-dd86-7d26-2e55-126c1470ca41/full/843,/0/default.jpg";
    Go(vm.Downloads);
    await Wait(600);
    await Shot("04a-downloads-paste.png");
    vm.Downloads.AddPastedCommand.Execute(null);
    var huge = new DownloadJob(new Uri("https://openaccess-cdn.clevelandart.org/1930.851/1930.851_full.tif"), services.Settings.DownloadDirectory, "lighthouse-village-full.tif");
    services.Downloads.Enqueue(huge);
    await WaitFor(() => vm.Downloads.Items.Count >= 3 && vm.Downloads.Items.Count(i => !i.IsActive || i.Progress > 2) >= 3, 30_000, "downloads");
    await Wait(1500);
    services.Downloads.Pause(huge);
    await Wait(800);
    vm.Downloads.ClipboardLink = "https://images-assets.nasa.gov/image/PIA14417/PIA14417~orig.jpg";
    await Shot("04-downloads.png");

    // ---- collections
    var coll = await services.Api.Current.CreateCollectionAsync("Aurora template · hero images", UseCase.Bundled);
    foreach (var r in vm.Search.Results.Where(r => r.IsGreen).Take(6))
        await services.Api.Current.AddToCollectionAsync(coll.Id, r.Asset);
    Go(vm.Collections);
    await WaitFor(() => vm.Collections.Items.Count > 0, 15_000, "collection items");
    await Wait(4000);
    await Shot("05-collections.png");

    // ---- ledger, license check, sources
    Go(vm.Ledger);
    await Wait(1500);
    await Shot("06-ledger.png");

    Go(vm.LicenseCheck);
    vm.LicenseCheck.LicenseText = "https://unsplash.com/license";
    await vm.LicenseCheck.CheckCommand.ExecuteAsync(null);
    await Shot("07-license-check.png");

    Go(vm.Sources);
    await Wait(1500);
    await Shot("08-sources.png");

    Go(vm.Settings);
    await Shot("09-settings.png");

    // ---- query words pick the media, and several media group into sections (contract grouped-results)
    vm.Search.CloseDetailCommand.Execute(null);
    Go(vm.Search);
    vm.Search.Query = "anchor photo icon";
    await vm.Search.SearchAsync();
    await WaitFor(() => !vm.Search.IsSearching, 60_000, "search words");
    Console.WriteLine($"  read as: {string.Join(", ", vm.Search.Picks.Select(p => p.Text))} · sections: " +
                      string.Join(", ", vm.Search.Sections.Select(s => $"{s.Label} {s.Cards.Count}/{s.Total}")));
    if (vm.Search.Query != "anchor" || vm.Search.Picks.Count != 2 || !vm.Search.IsGrouped || vm.Search.Sections.Count < 2)
        throw new InvalidOperationException("the query words weren't read as Images + Icons sections");
    await Wait(7000);
    await Shot("09b-search-grouped.png");
    vm.Search.ToggleSectionCommand.Execute(vm.Search.Sections[1]);
    await Wait(500);
    vm.Search.JumpCommand.Execute(vm.Search.Sections[1]);
    await Wait(2500);
    await Shot("09c-search-jump-expanded.png");
    await vm.Search.RemovePickCommand.ExecuteAsync(vm.Search.Picks.First(p => p.Pick.Word == "icon"));
    await WaitFor(() => !vm.Search.IsSearching, 60_000, "search after removing a chip");
    if (vm.Search.Query != "anchor icon" || vm.Search.Picks.Count != 1 || vm.Search.IsGrouped)
        throw new InvalidOperationException($"removing the chip left '{vm.Search.Query}', {vm.Search.Picks.Count} chip(s)");
    await Wait(5000);
    await Shot("09d-search-chip-removed.png");

    // ---- packs: a pack word turns Packs on and Iconify's sets lead the grid (contract packs-and-new-kinds)
    vm.Search.Query = "game icon pack";
    await vm.Search.SearchAsync();
    await WaitFor(() => vm.Search.Results.Any(r => r.IsPack) && !vm.Search.IsSearching, 60_000, "search packs");
    Console.WriteLine($"  read as: {string.Join(", ", vm.Search.Picks.Select(p => p.Text))} · first: " +
                      string.Join(", ", vm.Search.Results.Take(3).Select(r => r.IsPack ? r.PackBadge : r.Title)));
    if (!vm.Search.Packs || vm.Search.Picks.Count != 2 || vm.Search.Query != "game" || vm.Search.Results.FirstOrDefault()?.IsPack != true)
        throw new InvalidOperationException($"\"pack\" didn't turn Packs on, or no set led the results (packs {vm.Search.Packs}, query '{vm.Search.Query}', "
            + $"error '{vm.Search.Error}', searched {vm.Search.HasSearched}, sources {vm.Search.ReportedSources}/{vm.Search.TotalSources}, results {vm.Search.Results.Count})");
    await Wait(5000);
    await Shot("09e-search-packs.png");
    await vm.Search.OpenCommand.ExecuteAsync(vm.Search.Results.First(r => r.IsPack));
    await WaitFor(() => vm.Search.Detail is { IsLoading: false }, 30_000, "pack detail");
    if (vm.Search.Detail is not { IsPack: true, HasFormats: true })
        throw new InvalidOperationException("the pack's detail lost its pack rows");
    await Wait(1500);
    await Shot("09f-pack-detail.png");
    vm.Search.CloseDetailCommand.Execute(null);
    vm.Search.Presets[0].IsSelected = true; // Game assets: its media and packs, then one search
    await WaitFor(() => vm.Search.Results.Any(r => r.IsPack) && !vm.Search.IsSearching, 60_000, "game assets");
    var gameMedia = vm.Search.Media.Where(m => m.IsSelected).Select(m => m.Value).ToList();
    Console.WriteLine($"  game assets: {string.Join(", ", gameMedia)} · packs {vm.Search.Packs} · chips {vm.Search.Picks.Count}");
    if (!vm.Search.Packs || !gameMedia.SequenceEqual(Categories.Presets[0].Media) || vm.Search.Picks.Count != 0 || !vm.Search.Presets[0].IsSelected)
        throw new InvalidOperationException("Game assets didn't set its media and packs");
    window.Width = 760; // a narrow window: the eleven media pills and the preset wrap instead of running off (CodeRabbit, PR #8)
    await Wait(1500);
    await Shot("09g-search-narrow.png");
    window.Width = 1440;
    await Wait(800);
    vm.Search.PacksOptions[0].IsSelected = true; // Packs off again for the shots below

    // ---- Frost (light) + icons/fonts/textures mix
    services.Theme.Apply(AppTheme.Frost, AccentColor.Sodium);
    foreach (var m in vm.Search.Media) m.IsSelected = m.Value is MediaType.Texture or MediaType.Icon or MediaType.Font or MediaType.Hdri;
    vm.Search.Query = "wood";
    Go(vm.Search);
    await vm.Search.SearchAsync();
    await WaitFor(() => !vm.Search.IsSearching, 60_000, "search 2");
    await Wait(7000);
    await Shot("10-frost-search.png");
    var tex = vm.Search.Results.FirstOrDefault(r => r.Asset.Provider == "polyhaven") ?? vm.Search.Results.First();
    await vm.Search.OpenCommand.ExecuteAsync(tex);
    await WaitFor(() => vm.Search.Detail is { IsLoading: false }, 30_000, "detail 2");
    await Wait(3000);
    await Shot("11-frost-detail.png");

    Go(vm.Settings);
    await Shot("12-frost-settings.png");

    services.Theme.Apply(AppTheme.Glass, AccentColor.Iris);
    vm.Search.CloseDetailCommand.Execute(null);
    Go(vm.Search);
    await Wait(1500);
    await Shot("13-iris-accent.png");

    // ---- regression (CodeRabbit, PR #7): a query read that answers after a newer one must not take over
    var slow = DispatchProxy.Create<IFreestashApi, SlowRead>();
    ((SlowRead)(object)slow).Inner = services.Api.Current;
    ((SlowRead)(object)slow).SlowText = "rain sfx";
    services.Api.Override = slow;
    vm.Search.Query = "rain sfx";
    var older = vm.Search.SearchAsync(); // its read waits at the gate
    vm.Search.Query = "anchor font";
    await vm.Search.SearchAsync();
    ((SlowRead)(object)slow).Gate.SetResult();
    await older;
    await WaitFor(() => !vm.Search.IsSearching, 60_000, "search after the stale read");
    services.Api.Override = null;
    var picks = string.Join(", ", vm.Search.Picks.Select(p => p.Text));
    Console.WriteLine($"  stale read: query '{vm.Search.Query}' · read as {picks}");
    if (vm.Search.Query != "anchor" || picks != "“font” → Fonts")
        throw new InvalidOperationException($"an older read took over: '{vm.Search.Query}', {picks}");

    if (accountsUrl is null) return;

    // ---- hosted mode: sign up on the sign-in screen, then prove keys and prefs reach the account
    services.Theme.Apply(AppTheme.Glass, AccentColor.Sodium);
    var hosted = services.Settings;
    hosted.Mode = ConnectionMode.Remote;
    hosted.RemoteUrl = accountsUrl;
    services.SaveSettings(hosted);
    await services.Engine.EnsureRunningAsync();
    services.Session.Set(null);
    await WaitFor(() => vm.NeedsSignIn, 5_000, "sign-in gate");
    await Shot("14-sign-in.png");

    vm.SignIn.ShowSignUpCommand.Execute(null);
    vm.SignIn.DisplayName = "Jordan Vale";
    vm.SignIn.Email = $"desktop-{DateTime.UtcNow:HHmmss}@example.com";
    vm.SignIn.Password = "desktop password 1";
    await Shot("15-sign-up.png");
    await vm.SignIn.SubmitCommand.ExecuteAsync(null);
    await WaitFor(() => !vm.NeedsSignIn, 15_000, "sign-up");
    Console.WriteLine($"  signed up: {services.Session.Current?.User.Email} · error: {vm.SignIn.Error ?? "none"}");

    Go(vm.Settings);
    await vm.Settings.OnShownAsync();
    var pexels = vm.Settings.Keys.First(k => k.Name == "PEXELS_API_KEY");
    pexels.Value = "desktop-key-7Q2x";
    vm.Settings.Accents.First(a => a.Value == AccentColor.Teal).IsSelected = true;
    await vm.Settings.SaveCommand.ExecuteAsync(null);
    var keys = await services.Account.Current.KeysAsync();
    var prefs = (await services.Account.Current.PrefsAsync()).Data;
    var keyOk = keys.Single(k => k.Name == "PEXELS_API_KEY") is { Set: true, Hint: "7Q2x" };
    Console.WriteLine($"  SYNC key in account: {(keyOk ? "OK" : "FAILED")} · accent in account: {prefs.Accent}");
    if (!keyOk || prefs.Accent != "teal") throw new InvalidOperationException("account sync failed");
    await Wait(800);
    await Shot("16-account-settings.png");
}

/// <summary>Forwards every call to the real client but holds back one query's read until <see cref="Gate"/> opens.</summary>
public class SlowRead : DispatchProxy
{
    public IFreestashApi Inner { get; set; } = null!;
    public string SlowText { get; set; } = "";
    public TaskCompletionSource Gate { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);

    protected override object? Invoke(MethodInfo? method, object?[]? args)
    {
        if (method!.Name == nameof(IFreestashApi.ParseQueryAsync) && args![0] as string == SlowText)
            return HeldAsync((string)args[0]!, (IReadOnlyList<string>)args[1]!);
        return method.Invoke(Inner, args);
    }

    private async Task<ParsedQuery> HeldAsync(string q, IReadOnlyList<string> keep)
    {
        await Gate.Task;
        return await Inner.ParseQueryAsync(q, keep);
    }
}
