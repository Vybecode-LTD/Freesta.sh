using Avalonia;
using Avalonia.Controls;

namespace Freestash.Desktop.Controls;

/// <summary>
/// Responsive card grid: as many columns as fit at <see cref="MinItemWidth"/>, then stretches items to fill the
/// row exactly, so there's never a dead strip on the right (unlike WrapPanel with fixed-width cards).
/// </summary>
public sealed class AdaptiveGrid : Panel
{
    public static readonly StyledProperty<double> MinItemWidthProperty = AvaloniaProperty.Register<AdaptiveGrid, double>(nameof(MinItemWidth), 232);
    public static readonly StyledProperty<double> ItemHeightProperty = AvaloniaProperty.Register<AdaptiveGrid, double>(nameof(ItemHeight), double.NaN);
    public static readonly StyledProperty<double> SpacingProperty = AvaloniaProperty.Register<AdaptiveGrid, double>(nameof(Spacing), 16);

    static AdaptiveGrid() => AffectsMeasure<AdaptiveGrid>(MinItemWidthProperty, ItemHeightProperty, SpacingProperty);

    public double MinItemWidth { get => GetValue(MinItemWidthProperty); set => SetValue(MinItemWidthProperty, value); }
    public double ItemHeight { get => GetValue(ItemHeightProperty); set => SetValue(ItemHeightProperty, value); }
    public double Spacing { get => GetValue(SpacingProperty); set => SetValue(SpacingProperty, value); }

    private (int Columns, double ItemWidth) Layout(double width)
    {
        if (double.IsInfinity(width) || width <= 0) return (1, MinItemWidth);
        var cols = Math.Max(1, (int)((width + Spacing) / (MinItemWidth + Spacing)));
        return (cols, (width - Spacing * (cols - 1)) / cols);
    }

    protected override Size MeasureOverride(Size availableSize)
    {
        var (cols, itemW) = Layout(availableSize.Width);
        double total = 0, rowH = 0;
        for (var i = 0; i < Children.Count; i++)
        {
            var child = Children[i];
            child.Measure(new Size(itemW, double.IsNaN(ItemHeight) ? double.PositiveInfinity : ItemHeight));
            rowH = Math.Max(rowH, double.IsNaN(ItemHeight) ? child.DesiredSize.Height : ItemHeight);
            if ((i + 1) % cols == 0 || i == Children.Count - 1)
            {
                total += rowH + (i == Children.Count - 1 ? 0 : Spacing);
                rowH = 0;
            }
        }
        var width = double.IsInfinity(availableSize.Width) ? cols * itemW + (cols - 1) * Spacing : availableSize.Width;
        return new Size(width, total);
    }

    protected override Size ArrangeOverride(Size finalSize)
    {
        var (cols, itemW) = Layout(finalSize.Width);
        double y = 0;
        for (var row = 0; row * cols < Children.Count; row++)
        {
            var rowItems = Children.Skip(row * cols).Take(cols).ToList();
            var rowH = double.IsNaN(ItemHeight) ? rowItems.Max(c => c.DesiredSize.Height) : ItemHeight;
            for (var c = 0; c < rowItems.Count; c++)
                rowItems[c].Arrange(new Rect(c * (itemW + Spacing), y, itemW, rowH));
            y += rowH + Spacing;
        }
        return finalSize;
    }
}
