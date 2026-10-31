// Headless visual check: boots the real app with Skia rendering, drives it against a running Freestash engine,
// and writes a PNG per screen. Usage:
//   python -m freestash serve --port 8787          (in the freestash repo)
//   dotnet run --project tools/Freestash.Desktop.Snapshots -- http://127.0.0.1:8787 docs/screenshots

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

    // ---- Machined Light + icons/fonts/textures mix
    services.Theme.Apply(AppTheme.MachinedLight, AccentColor.Ember);
    foreach (var m in vm.Search.Media) m.IsSelected = m.Value is MediaType.Texture or MediaType.Icon or MediaType.Font or MediaType.Hdri;
    vm.Search.Query = "wood";
    Go(vm.Search);
    await vm.Search.SearchAsync();
    await WaitFor(() => !vm.Search.IsSearching, 60_000, "search 2");
    await Wait(7000);
    await Shot("10-machined-light-search.png");
    var tex = vm.Search.Results.FirstOrDefault(r => r.Asset.Provider == "polyhaven") ?? vm.Search.Results.First();
    await vm.Search.OpenCommand.ExecuteAsync(tex);
    await WaitFor(() => vm.Search.Detail is { IsLoading: false }, 30_000, "detail 2");
    await Wait(3000);
    await Shot("11-machined-light-detail.png");

    Go(vm.Settings);
    await Shot("12-machined-light-settings.png");

    services.Theme.Apply(AppTheme.EmberDark, AccentColor.Iris);
    vm.Search.CloseDetailCommand.Execute(null);
    Go(vm.Search);
    await Wait(1500);
    await Shot("13-iris-accent.png");
}
