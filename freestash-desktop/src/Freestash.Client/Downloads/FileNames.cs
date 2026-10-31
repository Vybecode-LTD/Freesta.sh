using System.Text;
using System.Text.RegularExpressions;

namespace Freestash.Client.Downloads;

public static partial class FileNames
{
    private static readonly HashSet<char> Invalid = [.. Path.GetInvalidFileNameChars(), ':', '*', '?', '"', '<', '>', '|', '/', '\\'];

    private static readonly HashSet<string> WindowsReserved = new(StringComparer.OrdinalIgnoreCase)
    {
        "CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
        "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
    };

    /// <summary>Safe on Windows, macOS, and Linux. Returns null for empty input.</summary>
    public static string? Sanitize(string? name, int maxLength = 140)
    {
        if (string.IsNullOrWhiteSpace(name)) return null;
        var sb = new StringBuilder(name.Length);
        foreach (var c in name.Trim()) sb.Append(Invalid.Contains(c) || char.IsControl(c) ? '_' : c);
        var cleaned = MultiUnderscore().Replace(sb.ToString(), "_").Trim(' ', '.', '_');
        if (cleaned.Length == 0) return null;
        var stem = Path.GetFileNameWithoutExtension(cleaned);
        if (WindowsReserved.Contains(stem)) cleaned = "_" + cleaned;
        if (cleaned.Length > maxLength)
        {
            var ext = Path.GetExtension(cleaned);
            cleaned = cleaned[..(maxLength - ext.Length)].TrimEnd(' ', '.') + ext;
        }
        return cleaned;
    }

    public static string FromUrl(Uri url)
    {
        var last = Uri.UnescapeDataString(url.Segments.LastOrDefault()?.Trim('/') ?? "");
        // ambientCG style: /get?file=Wood096_1K-JPG.zip
        if (string.IsNullOrEmpty(Path.GetExtension(last)))
        {
            var query = System.Web.HttpUtility.ParseQueryString(url.Query);
            foreach (var key in new[] { "file", "filename", "name" })
                if (query[key] is { Length: > 0 } q) { last = q; break; }
        }
        return Sanitize(last) ?? $"download-{DateTime.Now:yyyyMMdd-HHmmss}";
    }

    /// <summary>"{title}--{provider}-{id}{ext}" so files sort by name and stay traceable to their source.</summary>
    public static string ForAsset(Asset asset, Rendition rendition)
    {
        var ext = Path.GetExtension(new Uri(rendition.Url).AbsolutePath);
        if (string.IsNullOrEmpty(ext) || ext.Length > 6) ext = ExtensionForMime(rendition.Mime);
        var title = Slug(asset.Title, 60);
        var id = Slug(asset.SourceId, 40);
        return Sanitize($"{title}--{asset.Provider}-{id}{ext}") ?? $"{asset.Provider}-{id}{ext}";
    }

    public static string Slug(string text, int max)
    {
        var s = NonAlnum().Replace(text.ToLowerInvariant(), "-").Trim('-');
        if (s.Length > max) s = s[..max].TrimEnd('-');
        return s.Length == 0 ? "asset" : s;
    }

    public static string ExtensionForMime(string? mime) => mime?.Split(';')[0].Trim().ToLowerInvariant() switch
    {
        "image/jpeg" => ".jpg", "image/png" => ".png", "image/webp" => ".webp", "image/gif" => ".gif",
        "image/svg+xml" => ".svg", "image/tiff" => ".tif", "audio/mpeg" => ".mp3", "audio/ogg" => ".ogg",
        "audio/wav" or "audio/x-wav" or "audio/wave" => ".wav", "audio/flac" => ".flac", "video/mp4" => ".mp4",
        "video/webm" => ".webm", "application/zip" => ".zip", "font/woff2" => ".woff2", "font/ttf" => ".ttf",
        "application/pdf" => ".pdf", _ => "",
    };

    /// <summary>"file.jpg" → "file (2).jpg" if taken.</summary>
    public static string Unique(string path)
    {
        if (!File.Exists(path)) return path;
        var dir = Path.GetDirectoryName(path)!;
        var stem = Path.GetFileNameWithoutExtension(path);
        var ext = Path.GetExtension(path);
        for (var i = 2; ; i++)
        {
            var candidate = Path.Combine(dir, $"{stem} ({i}){ext}");
            if (!File.Exists(candidate)) return candidate;
        }
    }

    [GeneratedRegex("_{2,}")] private static partial Regex MultiUnderscore();
    [GeneratedRegex("[^a-z0-9]+")] private static partial Regex NonAlnum();
}
