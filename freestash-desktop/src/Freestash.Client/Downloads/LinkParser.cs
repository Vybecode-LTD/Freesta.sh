using System.Text.RegularExpressions;

namespace Freestash.Client.Downloads;

/// <summary>Pulls downloadable http(s) links out of pasted text: one per line, comma lists, markdown, HTML, whatever.</summary>
public static partial class LinkParser
{
    public static IReadOnlyList<Uri> Extract(string? text)
    {
        if (string.IsNullOrWhiteSpace(text)) return [];
        var seen = new HashSet<string>(StringComparer.Ordinal);
        var links = new List<Uri>();
        foreach (Match m in UrlPattern().Matches(text))
        {
            var raw = m.Value.TrimEnd('.', ',', ';', ':', '!', '?', '\'', '"');
            // Trim an unbalanced closing paren from markdown links: (https://x.com/a.png)
            if (raw.EndsWith(')') && raw.Count(c => c == '(') < raw.Count(c => c == ')')) raw = raw[..^1];
            if (Uri.TryCreate(raw, UriKind.Absolute, out var uri) && uri.Scheme is "http" or "https" && seen.Add(uri.AbsoluteUri))
                links.Add(uri);
        }
        return links;
    }

    public static bool ContainsLink(string? text) => !string.IsNullOrWhiteSpace(text) && UrlPattern().IsMatch(text);

    [GeneratedRegex(@"https?://[^\s<>""'\]\[{}|\\^`]+", RegexOptions.IgnoreCase)]
    private static partial Regex UrlPattern();
}
