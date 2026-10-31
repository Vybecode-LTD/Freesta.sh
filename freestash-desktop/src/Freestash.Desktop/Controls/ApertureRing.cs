using System.Globalization;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Media;
using Avalonia.Threading;

namespace Freestash.Desktop.Controls;

/// <summary>
/// Aperture's signature element: one tick per source being searched, lit as each source reports (red if it
/// failed), with a two-digit count in the middle. Same geometry as the web's components/Aperture.tsx.
/// Colours are the theme's brushes, so it follows Glass/Frost and the accent live.
/// </summary>
public sealed class ApertureRing : Control
{
    public static readonly StyledProperty<int> TotalProperty = AvaloniaProperty.Register<ApertureRing, int>(nameof(Total));
    public static readonly StyledProperty<int> ReportedProperty = AvaloniaProperty.Register<ApertureRing, int>(nameof(Reported));
    public static readonly StyledProperty<int> FailedProperty = AvaloniaProperty.Register<ApertureRing, int>(nameof(Failed));
    public static readonly StyledProperty<bool> IsBusyProperty = AvaloniaProperty.Register<ApertureRing, bool>(nameof(IsBusy));
    public static readonly StyledProperty<double> SizeProperty = AvaloniaProperty.Register<ApertureRing, double>(nameof(Size), 66);

    private readonly DispatcherTimer _breath = new() { Interval = TimeSpan.FromMilliseconds(60) };
    private double _phase;

    static ApertureRing()
    {
        AffectsRender<ApertureRing>(TotalProperty, ReportedProperty, FailedProperty, IsBusyProperty);
        AffectsMeasure<ApertureRing>(SizeProperty);
    }

    public ApertureRing()
    {
        _breath.Tick += (_, _) => { _phase = (_phase + 0.06) % 1; InvalidateVisual(); };
        ActualThemeVariantChanged += (_, _) => InvalidateVisual();
    }

    public int Total { get => GetValue(TotalProperty); set => SetValue(TotalProperty, value); }
    public int Reported { get => GetValue(ReportedProperty); set => SetValue(ReportedProperty, value); }
    public int Failed { get => GetValue(FailedProperty); set => SetValue(FailedProperty, value); }
    public bool IsBusy { get => GetValue(IsBusyProperty); set => SetValue(IsBusyProperty, value); }
    public double Size { get => GetValue(SizeProperty); set => SetValue(SizeProperty, value); }

    protected override void OnPropertyChanged(AvaloniaPropertyChangedEventArgs change)
    {
        base.OnPropertyChanged(change);
        if (change.Property == IsBusyProperty) { if (IsBusy) _breath.Start(); else _breath.Stop(); }
    }

    protected override void OnDetachedFromVisualTree(VisualTreeAttachmentEventArgs e)
    {
        _breath.Stop();
        base.OnDetachedFromVisualTree(e);
    }

    protected override Size MeasureOverride(Size availableSize) => new(Size, Size);

    private IBrush Res(string key, IBrush fallback) =>
        this.TryFindResource(key, ActualThemeVariant, out var v) && v is IBrush b ? b : fallback;

    public override void Render(DrawingContext ctx)
    {
        var size = Math.Min(Bounds.Width, Bounds.Height);
        var c = new Point(size / 2, size / 2);
        var accent = Res("AccentBrush", Brushes.Orange);
        var red = Res("RedBrush", Brushes.IndianRed);
        var idle = Res("BorderStrongBrush", Brushes.Gray);
        var ring = Res("BorderSubtleBrush", Brushes.DimGray);
        var text = Res("TextBrush", Brushes.White);

        ctx.DrawEllipse(null, new Pen(ring, 1), c, size / 2 - 1.5, size / 2 - 1.5);

        var n = Math.Max(Total, 1);
        double r1 = size * 0.33, r2 = size * 0.44, w = Math.Max(2.2, size * 0.04);
        for (var i = 0; i < n; i++)
        {
            var a = i / (double)n * Math.PI * 2 - Math.PI / 2;
            IBrush brush = Total == 0 ? idle : i < Reported - Failed ? accent : i < Reported ? red : idle;
            var pen = new Pen(brush, w, lineCap: PenLineCap.Round);
            var p1 = new Point(c.X + Math.Cos(a) * r1, c.Y + Math.Sin(a) * r1);
            var p2 = new Point(c.X + Math.Cos(a) * r2, c.Y + Math.Sin(a) * r2);
            if (IsBusy && i >= Reported)
            {
                var pulse = 0.35 + 0.65 * Math.Abs(Math.Sin((_phase + i / (double)n) * Math.PI));
                using (ctx.PushOpacity(pulse)) ctx.DrawLine(new Pen(accent, w, lineCap: PenLineCap.Round), p1, p2);
            }
            else ctx.DrawLine(pen, p1, p2);
        }

        if (Total == 0)
        {
            ctx.DrawEllipse(accent, null, c, size * 0.045, size * 0.045);
            return;
        }
        var mono = this.TryFindResource("MonoFont", out var f) && f is FontFamily ff ? ff : FontFamily.Default;
        var label = new FormattedText(Reported.ToString("00", CultureInfo.InvariantCulture), CultureInfo.InvariantCulture,
            FlowDirection.LeftToRight, new Typeface(mono, FontStyle.Normal, FontWeight.SemiBold), size * 0.2, text);
        ctx.DrawText(label, new Point(c.X - label.Width / 2, c.Y - label.Height / 2));
    }
}
