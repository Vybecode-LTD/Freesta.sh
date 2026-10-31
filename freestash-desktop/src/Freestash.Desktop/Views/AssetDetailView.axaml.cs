using Avalonia.Controls;
using Avalonia.Input;
using Freestash.Desktop.ViewModels;

namespace Freestash.Desktop.Views;

public partial class AssetDetailView : UserControl
{
    public AssetDetailView()
    {
        InitializeComponent();
        KeyDown += (_, e) =>
        {
            if (e.Key == Key.Escape && DataContext is AssetDetailViewModel vm) { vm.CloseCommand.Execute(null); e.Handled = true; }
        };
    }
}
