using Avalonia;
using Avalonia.Media;
using Avalonia.Styling;
using Freestash.Client.Settings;

namespace Freestash.Desktop.Services;

/// <summary>
/// Single source of truth for both looks. Every XAML color is a DynamicResource set here, so switching
/// theme or accent at runtime repaints the whole app instantly.
///
/// Ember Dark ...... the VybeCod.ing identity: #0a0a0a canvas, Ember #e8440a, quiet warm greys.
/// Machined Light .. warm-graphite canvas, raised "machined" surfaces with a white top highlight over soft
///                   warm shadows, carved/inset inputs, champagne hairlines reserved for premium touches.
/// </summary>
public sealed class ThemeManager
{
    public static readonly IReadOnlyDictionary<AccentColor, Color> Accents = new Dictionary<AccentColor, Color>
    {
        [AccentColor.Ember] = Color.Parse("#E8440A"),
        [AccentColor.Iris] = Color.Parse("#7C6CF2"),
        [AccentColor.Teal] = Color.Parse("#12A594"),
        [AccentColor.Cobalt] = Color.Parse("#3B6CF6"),
    };

    private sealed record Palette(
        string Canvas, string Chrome, string Surface, string Raised, string Hover, string Inset,
        string BorderSubtle, string BorderStrong, string Highlight, string Hairline,
        string Text, string TextSecondary, string TextFaint, string ScrimAlpha,
        string Green, string Yellow, string Red,
        string CardShadow, string RaisedShadow, string InsetShadow, string PopShadow, double GlowOpacity);

    private static readonly Palette EmberDark = new(
        Canvas: "#0A0A0A", Chrome: "#0C0B0A", Surface: "#131211", Raised: "#191816", Hover: "#211F1C", Inset: "#0E0D0C",
        BorderSubtle: "#262320", BorderStrong: "#3A3530", Highlight: "#0DFFFFFF", Hairline: "#8C7A55",
        Text: "#F3F1EE", TextSecondary: "#B3ADA5", TextFaint: "#77716A", ScrimAlpha: "#B3000000",
        Green: "#5CCF8F", Yellow: "#F2C350", Red: "#F2654F",
        CardShadow: "inset 0 1 0 0 #0AFFFFFF, 0 16 36 -18 #F0000000",
        RaisedShadow: "inset 0 1 0 0 #0FFFFFFF, 0 8 20 -10 #E6000000",
        InsetShadow: "inset 0 1 3 0 #99000000",
        PopShadow: "0 24 60 -12 #F2000000, 0 0 0 1 #22FFFFFF",
        GlowOpacity: 0.16);

    private static readonly Palette MachinedLight = new(
        Canvas: "#D3CEC6", Chrome: "#CBC6BD", Surface: "#E3DFD8", Raised: "#ECE9E3", Hover: "#F3F0EB", Inset: "#C9C4BB",
        BorderSubtle: "#BDB7AD", BorderStrong: "#A69F94", Highlight: "#E6FFFFFF", Hairline: "#B89A5E",
        Text: "#1D1A17", TextSecondary: "#4D4741", TextFaint: "#7A736B", ScrimAlpha: "#66342A20",
        Green: "#1E8A55", Yellow: "#9A6A00", Red: "#C3361E",
        CardShadow: "inset 0 1 0 0 #E6FFFFFF, 0 1 2 0 #263A2E24, 0 14 30 -14 #593A2E24",
        RaisedShadow: "inset 0 1 0 0 #F2FFFFFF, 0 1 1 0 #2E3A2E24, 0 6 14 -6 #4D3A2E24",
        InsetShadow: "inset 0 1 3 0 #403A2E24, inset 0 -1 0 0 #80FFFFFF",
        PopShadow: "0 24 56 -14 #803A2E24, 0 0 0 1 #26000000",
        GlowOpacity: 0.12);

    public AppTheme Current { get; private set; }
    public Color Accent { get; private set; } = Color.Parse("#E8440A");

    public event Action? Changed;

    public void Apply(AppTheme theme, AccentColor accent)
    {
        var app = Application.Current ?? throw new InvalidOperationException("Avalonia app not initialized");
        var p = theme == AppTheme.MachinedLight ? MachinedLight : EmberDark;
        var a = Accents[accent];
        var r = app.Resources;
        Current = theme;
        Accent = a;

        app.RequestedThemeVariant = theme == AppTheme.MachinedLight ? ThemeVariant.Light : ThemeVariant.Dark;

        void Brush(string key, string hex) => r[key] = new SolidColorBrush(Color.Parse(hex));
        void BrushC(string key, Color c) => r[key] = new SolidColorBrush(c);

        Brush("CanvasBrush", p.Canvas);
        Brush("ChromeBrush", p.Chrome);
        Brush("SurfaceBrush", p.Surface);
        Brush("RaisedBrush", p.Raised);
        Brush("HoverBrush", p.Hover);
        Brush("InsetBrush", p.Inset);
        Brush("BorderSubtleBrush", p.BorderSubtle);
        Brush("BorderStrongBrush", p.BorderStrong);
        Brush("HighlightBrush", p.Highlight);
        Brush("HairlineBrush", p.Hairline);
        Brush("TextBrush", p.Text);
        Brush("TextSecondaryBrush", p.TextSecondary);
        Brush("TextFaintBrush", p.TextFaint);
        Brush("ScrimBrush", p.ScrimAlpha);
        Brush("OverlayBrush", theme == AppTheme.MachinedLight ? "#E6F4F1EC" : "#CC0E0D0C");

        BrushC("AccentBrush", a);
        BrushC("AccentHoverBrush", Lighten(a, theme == AppTheme.MachinedLight ? -0.08 : 0.10));
        BrushC("AccentSoftBrush", WithAlpha(a, (byte)(theme == AppTheme.MachinedLight ? 0x2E : 0x2A)));
        BrushC("AccentLineBrush", WithAlpha(a, 0x80));
        BrushC("AccentTextBrush", theme == AppTheme.MachinedLight ? Lighten(a, -0.12) : Lighten(a, 0.18));
        Brush("OnAccentBrush", "#FFFFFF");

        foreach (var (name, hex) in new[] { ("Green", p.Green), ("Yellow", p.Yellow), ("Red", p.Red) })
        {
            var c = Color.Parse(hex);
            BrushC($"{name}Brush", c);
            BrushC($"{name}SoftBrush", WithAlpha(c, (byte)(theme == AppTheme.MachinedLight ? 0x26 : 0x24)));
        }

        r["CardShadow"] = BoxShadows.Parse(p.CardShadow);
        r["RaisedShadow"] = BoxShadows.Parse(p.RaisedShadow);
        r["InsetShadow"] = BoxShadows.Parse(p.InsetShadow);
        r["PopShadow"] = BoxShadows.Parse(p.PopShadow);
        r["AccentGlowShadow"] = BoxShadows.Parse($"0 0 18 2 #{WithAlpha(a, 0x99).ToUInt32():X8}");
        r["AccentButtonShadow"] = BoxShadows.Parse($"inset 0 1 0 0 #33FFFFFF, 0 6 18 -6 #{WithAlpha(a, 0xB3).ToUInt32():X8}");

        r["AmbientGlowBrush"] = new RadialGradientBrush
        {
            Center = new RelativePoint(0.12, 0.0, RelativeUnit.Relative),
            GradientOrigin = new RelativePoint(0.12, 0.0, RelativeUnit.Relative),
            RadiusX = new RelativeScalar(0.65, RelativeUnit.Relative),
            RadiusY = new RelativeScalar(0.55, RelativeUnit.Relative),
            GradientStops =
            {
                new GradientStop(WithAlpha(a, (byte)(255 * p.GlowOpacity)), 0),
                new GradientStop(WithAlpha(a, 0), 1),
            },
        };

        // Fluent controls (ToggleSwitch, ProgressBar, focus rings, selection) follow the accent too.
        r["SystemAccentColor"] = a;
        r["SystemAccentColorLight1"] = Lighten(a, 0.10);
        r["SystemAccentColorLight2"] = Lighten(a, 0.20);
        r["SystemAccentColorLight3"] = Lighten(a, 0.30);
        r["SystemAccentColorDark1"] = Lighten(a, -0.10);
        r["SystemAccentColorDark2"] = Lighten(a, -0.20);
        r["SystemAccentColorDark3"] = Lighten(a, -0.30);

        Changed?.Invoke();
    }

    /// <summary>Hex color for tinting monochrome SVG icons (Iconify's ?color=) to the theme text color.</summary>
    public string IconTintHex => Current == AppTheme.MachinedLight ? "1D1A17" : "F3F1EE";

    private static Color WithAlpha(Color c, byte alpha) => Color.FromArgb(alpha, c.R, c.G, c.B);

    private static Color Lighten(Color c, double amount)
    {
        byte Mix(byte ch) => (byte)Math.Clamp(amount >= 0 ? ch + (255 - ch) * amount : ch * (1 + amount), 0, 255);
        return Color.FromArgb(c.A, Mix(c.R), Mix(c.G), Mix(c.B));
    }
}
