using Avalonia.Controls;

namespace Freestash.Desktop.Views;

public partial class SearchView : UserControl
{
    public SearchView() => InitializeComponent();

    public void FocusSearch()
    {
        SearchBox.Focus();
        SearchBox.SelectAll();
    }
}
