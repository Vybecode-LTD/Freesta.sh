using Avalonia;
using Avalonia.Controls.ApplicationLifetimes;
using Avalonia.Markup.Xaml;
using Freestash.Desktop.Services;
using Freestash.Desktop.ViewModels;
using Freestash.Desktop.Views;

namespace Freestash.Desktop;

public partial class App : Application
{
    public const string UiFont = "avares://Freestash/Assets/Fonts#Geist";
    public const string MonoFont = "avares://Freestash/Assets/Fonts#Geist Mono";

    public static AppServices Services { get; private set; } = null!;

    public override void Initialize() => AvaloniaXamlLoader.Load(this);

    public override void OnFrameworkInitializationCompleted()
    {
        if (ApplicationLifetime is IClassicDesktopStyleApplicationLifetime desktop)
        {
            var window = CreateMainWindow(AppServices.CreateDefault());
            desktop.MainWindow = window;
            desktop.ShutdownRequested += async (_, _) => await Services.DisposeAsync();
            _ = Services.StartAsync();
        }
        base.OnFrameworkInitializationCompleted();
    }

    /// <summary>Composition root, shared by the real app and the headless snapshot tool.</summary>
    public static MainWindow CreateMainWindow(AppServices services)
    {
        Services = services;
        services.Theme.Apply(services.Settings.Theme, services.Settings.Accent);
        var vm = new MainWindowViewModel(services);
        var window = new MainWindow { DataContext = vm };
        services.Platform.Attach(window);
        return window;
    }
}
