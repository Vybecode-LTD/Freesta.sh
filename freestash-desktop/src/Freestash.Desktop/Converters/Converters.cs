using System.Globalization;
using Avalonia;
using Avalonia.Data.Converters;
using Avalonia.Media;
using Freestash.Client;

namespace Freestash.Desktop.Converters;

/// <summary>Tier → theme brush. Parameter "soft" returns the translucent background variant.</summary>
public sealed class TierBrushConverter : IValueConverter
{
    public static readonly TierBrushConverter Instance = new();

    public object? Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
    {
        var name = value switch { Tier.Green => "Green", Tier.Yellow => "Yellow", Tier.Red => "Red", _ => "TextFaint" };
        var key = parameter as string == "soft" && name != "TextFaint" ? $"{name}SoftBrush" : $"{name}Brush";
        return Application.Current?.TryGetResource(key, Application.Current.ActualThemeVariant, out var brush) == true ? brush : Brushes.Gray;
    }

    public object? ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture) => throw new NotSupportedException();
}

/// <summary>Resource key (string) → icon geometry from Styles/Icons.axaml.</summary>
public sealed class IconKeyConverter : IValueConverter
{
    public static readonly IconKeyConverter Instance = new();

    public object? Convert(object? value, Type targetType, object? parameter, CultureInfo culture) =>
        value is string key && Application.Current?.TryGetResource(key, null, out var g) == true ? g : null;

    public object? ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture) => throw new NotSupportedException();
}

public static class Conv
{
    public static readonly FuncValueConverter<string?, bool> NotEmpty = new(s => !string.IsNullOrWhiteSpace(s));
    public static readonly FuncValueConverter<int, bool> Positive = new(n => n > 0);
    public static readonly FuncValueConverter<int, bool> Zero = new(n => n == 0);
    public static readonly FuncValueConverter<string?, string> Upper = new(s => s?.ToUpperInvariant() ?? "");
}
