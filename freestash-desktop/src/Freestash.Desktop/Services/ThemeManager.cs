using Avalonia;
using Avalonia.Media;
using Avalonia.Styling;
using Freestash.Client.Settings;

namespace Freestash.Desktop.Services;

/// <summary>
/// Applies the Aperture look. Every colour comes from <see cref="DesignTokens"/>, which is generated from
/// shared/design-tokens.json, the same file the web app's tokens.css comes from, so the two apps can't drift.
/// Every XAML colour is a DynamicResource set here; switching theme or accent repaints the whole app instantly.
///
/// Glass ... cold glass strata on near-black, warm sodium light (the default).
/// Frost ... frosted glass on cool white.
/// </summary>
public sealed class ThemeManager
{
    public static IReadOnlyDictionary<AccentColor, Color> Accents { get; } = Enum.GetValues<AccentColor>()
        .ToDictionary(a => a, a => Color.Parse(DesignTokens.Accents[TokenName(a)].Fill));

    public AppTheme Current { get; private set; }
    public Color Accent { get; private set; } = Accents[AccentColor.Sodium];

    public event Action? Changed;

    public static string TokenName(AccentColor accent) => accent.ToString().ToLowerInvariant();
    public static string TokenName(AppTheme theme) => theme == AppTheme.Frost ? "light" : "dark";

    public void Apply(AppTheme theme, AccentColor accent)
    {
        var app = Application.Current ?? throw new InvalidOperationException("Avalonia app not initialized");
        var light = theme == AppTheme.Frost;
        var t = light ? DesignTokens.Light : DesignTokens.Dark;
        var at = DesignTokens.Accents[TokenName(accent)];
        var a = Color.Parse(at.Fill);
        var r = app.Resources;
        Current = theme;
        Accent = a;

        app.RequestedThemeVariant = light ? ThemeVariant.Light : ThemeVariant.Dark;

        Color C(string token) => Color.Parse(t[token]);
        void Brush(string key, Color c) => r[key] = new SolidColorBrush(c);

        Brush("CanvasBrush", C("canvas"));
        Brush("ChromeBrush", C("chrome"));
        Brush("SurfaceBrush", C("surface"));
        Brush("RaisedBrush", C("raised"));
        Brush("HoverBrush", C("hover"));
        Brush("InsetBrush", C("inset"));
        Brush("BorderSubtleBrush", C("borderSubtle"));
        Brush("BorderStrongBrush", C("borderStrong"));
        Brush("HighlightBrush", C("highlight"));
        Brush("HairlineBrush", C("hairline"));
        Brush("TextBrush", C("text"));
        Brush("TextSecondaryBrush", C("textSecondary"));
        Brush("TextFaintBrush", C("textFaint"));
        Brush("ScrimBrush", C("scrim"));
        Brush("OverlayBrush", C("overlay"));

        Brush("AccentBrush", a);
        Brush("AccentHoverBrush", a);
        Brush("AccentSoftBrush", WithAlpha(a, 0x1F));       // 12%, as --accent-soft on the web
        Brush("AccentLineBrush", WithAlpha(a, 0x8C));       // 55%, as --accent-line
        Brush("AccentTextBrush", Color.Parse(light ? at.TextLight : at.TextDark));
        Brush("OnAccentBrush", Color.Parse(at.On));

        foreach (var name in new[] { "Green", "Yellow", "Red" })
        {
            var c = C(name.ToLowerInvariant());
            Brush($"{name}Brush", c);
            Brush($"{name}SoftBrush", WithAlpha(c, 0x24));
        }

        var shadow = Hex(C("shadow"));
        var highlight = Hex(C("highlight"));
        r["CardShadow"] = BoxShadows.Parse($"inset 0 1 0 0 {highlight}, 0 30 60 -30 {shadow}");
        r["RaisedShadow"] = BoxShadows.Parse($"inset 0 1 0 0 {highlight}");
        r["InsetShadow"] = BoxShadows.Parse($"inset 0 1 2 0 {shadow}");
        r["PopShadow"] = BoxShadows.Parse($"0 24 60 -16 {shadow}, 0 0 0 1 {Hex(C("borderStrong"))}");
        r["AccentGlowShadow"] = BoxShadows.Parse($"0 0 10 0 {Hex(WithAlpha(a, 0xB3))}");
        r["AccentButtonShadow"] = BoxShadows.Parse($"0 10 30 -10 {Hex(WithAlpha(a, 0xCC))}");
        r["AccentRingShadow"] = BoxShadows.Parse($"0 0 0 4 {Hex(WithAlpha(a, 0x1F))}");
        r["AmbientGlowBrush"] = Brushes.Transparent; // Aperture is cold glass: no accent haze behind the chrome

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

    /// <summary>Hex colour for tinting monochrome SVG icons (Iconify's ?color=) to the theme text colour.</summary>
    public string IconTintHex => (Current == AppTheme.Frost ? DesignTokens.Light : DesignTokens.Dark)["text"][3..];

    private static string Hex(Color c) => $"#{c.ToUInt32():X8}";

    private static Color WithAlpha(Color c, byte alpha) => Color.FromArgb(alpha, c.R, c.G, c.B);

    private static Color Lighten(Color c, double amount)
    {
        byte Mix(byte ch) => (byte)Math.Clamp(amount >= 0 ? ch + (255 - ch) * amount : ch * (1 + amount), 0, 255);
        return Color.FromArgb(c.A, Mix(c.R), Mix(c.G), Mix(c.B));
    }
}
