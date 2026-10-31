using Avalonia;
using Avalonia.Controls;
using Avalonia.Layout;
using Avalonia.Media;
using Avalonia.Media.Imaging;

namespace Freestash.Desktop.Controls;

/// <summary>
/// Remote image with a quiet placeholder. While loading it shows a soft shimmer; if the host blocks
/// hotlinking it shows "preview blocked" instead of a broken image. Monochrome Iconify SVGs are tinted to
/// the theme so icons stay visible in both looks.
/// </summary>
public sealed class AsyncImage : Panel
{
    public static readonly StyledProperty<string?> UrlProperty = AvaloniaProperty.Register<AsyncImage, string?>(nameof(Url));
    public static readonly StyledProperty<int> DecodeWidthProperty = AvaloniaProperty.Register<AsyncImage, int>(nameof(DecodeWidth), 480);
    public static readonly StyledProperty<Stretch> StretchProperty = AvaloniaProperty.Register<AsyncImage, Stretch>(nameof(Stretch), Stretch.UniformToFill);
    public static readonly StyledProperty<string> PlaceholderProperty = AvaloniaProperty.Register<AsyncImage, string>(nameof(Placeholder), "");

    private readonly Image _image = new() { HorizontalAlignment = HorizontalAlignment.Stretch, VerticalAlignment = VerticalAlignment.Stretch };
    private readonly TextBlock _placeholder = new()
    {
        HorizontalAlignment = HorizontalAlignment.Center,
        VerticalAlignment = VerticalAlignment.Center,
        TextAlignment = TextAlignment.Center,
        FontFamily = new FontFamily(App.MonoFont),
        FontSize = 10.5,
        LetterSpacing = 1.2,
        Margin = new Thickness(12),
        TextWrapping = TextWrapping.Wrap,
    };
    private int _generation;

    public AsyncImage()
    {
        ClipToBounds = true;
        _placeholder.Bind(TextBlock.ForegroundProperty, this.GetResourceObservable("TextFaintBrush"));
        Children.Add(_placeholder);
        Children.Add(_image);
        _image.Bind(Image.StretchProperty, this.GetObservable(StretchProperty));
    }

    public string? Url { get => GetValue(UrlProperty); set => SetValue(UrlProperty, value); }
    public int DecodeWidth { get => GetValue(DecodeWidthProperty); set => SetValue(DecodeWidthProperty, value); }
    public Stretch Stretch { get => GetValue(StretchProperty); set => SetValue(StretchProperty, value); }
    public string Placeholder { get => GetValue(PlaceholderProperty); set => SetValue(PlaceholderProperty, value); }

    protected override void OnPropertyChanged(AvaloniaPropertyChangedEventArgs change)
    {
        base.OnPropertyChanged(change);
        if (change.Property == UrlProperty || change.Property == DecodeWidthProperty) _ = LoadAsync();
        if (change.Property == PlaceholderProperty && _image.Source is null) _placeholder.Text = Placeholder.ToUpperInvariant();
    }

    protected override void OnAttachedToVisualTree(VisualTreeAttachmentEventArgs e)
    {
        base.OnAttachedToVisualTree(e);
        App.Services.Theme.Changed += OnThemeChanged;
    }

    protected override void OnDetachedFromVisualTree(VisualTreeAttachmentEventArgs e)
    {
        base.OnDetachedFromVisualTree(e);
        App.Services.Theme.Changed -= OnThemeChanged;
    }

    private void OnThemeChanged()
    {
        if (Url?.Contains("api.iconify.design", StringComparison.Ordinal) == true) _ = LoadAsync();
    }

    private string? EffectiveUrl()
    {
        var url = Url;
        if (url is null) return null;
        // Iconify returns currentColor SVGs; ask for the theme's text color.
        if (url.Contains("api.iconify.design", StringComparison.Ordinal) && !url.Contains("color=", StringComparison.Ordinal))
            url += (url.Contains('?') ? "&" : "?") + "color=%23" + App.Services.Theme.IconTintHex;
        return url;
    }

    private async Task LoadAsync()
    {
        var gen = ++_generation;
        _image.Source = null;
        var url = EffectiveUrl();
        _placeholder.Text = string.IsNullOrEmpty(url) ? Placeholder.ToUpperInvariant() : "";
        if (string.IsNullOrEmpty(url)) return;

        var image = await App.Services.Images.LoadAsync(url, DecodeWidth);
        if (gen != _generation) return; // a newer URL won the race
        if (image is null)
        {
            _placeholder.Text = string.IsNullOrEmpty(Placeholder) ? "PREVIEW BLOCKED" : Placeholder.ToUpperInvariant() + "\nPREVIEW BLOCKED";
            return;
        }
        _image.Source = image;
        _image.Opacity = 0;
        _image.Transitions ??= [new Avalonia.Animation.DoubleTransition { Property = OpacityProperty, Duration = TimeSpan.FromMilliseconds(220) }];
        _image.Opacity = 1;
        _ = image is Bitmap; // decoded bitmaps are cached and shared; never dispose here
    }
}
