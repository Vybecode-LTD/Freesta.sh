using Avalonia;
using Avalonia.Controls;
using Freestash.Desktop.ViewModels;

namespace Freestash.Desktop.Views;

public partial class SearchView : UserControl
{
    private SearchViewModel? _vm;

    public SearchView() => InitializeComponent();

    public void FocusSearch()
    {
        SearchBox.Focus();
        SearchBox.SelectAll();
    }

    protected override void OnDataContextChanged(EventArgs e)
    {
        base.OnDataContextChanged(e);
        if (_vm is not null) _vm.JumpRequested -= JumpTo;
        _vm = DataContext as SearchViewModel;
        if (_vm is not null) _vm.JumpRequested += JumpTo;
    }

    /// <summary>The jump bar: put a section's heading at the top of the results (web: scrollIntoView).</summary>
    private void JumpTo(ResultSectionViewModel section)
    {
        if (SectionsItems.ContainerFromItem(section) is not { } container) return;
        if (container.TranslatePoint(new Point(0, 0), SectionsItems) is { } top)
            ResultsScroll.Offset = new Vector(ResultsScroll.Offset.X, top.Y);
    }
}
