using Avalonia;
using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.Threading;
using Avalonia.VisualTree;
using Freestash.Desktop.ViewModels;

namespace Freestash.Desktop.Views;

public partial class MainWindow : Window
{
    public MainWindow()
    {
        InitializeComponent();
        // Leave room for native caption buttons: traffic lights on the left (macOS), min/max/close on the right (Windows).
        TitleBarGrid.Margin = OperatingSystem.IsMacOS() ? new Thickness(84, 0, 18, 0) : new Thickness(18, 0, 150, 0);
    }

    protected override void OnKeyDown(KeyEventArgs e)
    {
        base.OnKeyDown(e);
        var cmd = e.KeyModifiers.HasFlag(KeyModifiers.Control) || e.KeyModifiers.HasFlag(KeyModifiers.Meta);
        if (cmd && e.Key == Key.K && DataContext is MainWindowViewModel vm)
        {
            vm.GoSearchCommand.Execute(null);
            Dispatcher.UIThread.Post(() => this.GetVisualDescendants().OfType<SearchView>().FirstOrDefault()?.FocusSearch(), DispatcherPriority.Input);
            e.Handled = true;
        }
    }
}
