using System.Runtime.CompilerServices;
using System.Text;

namespace Freestash.Client;

public readonly record struct SseEvent(string Event, string Data);

/// <summary>Minimal Server-Sent Events reader (event/data fields, blank-line delimited, multi-line data joined with \n).</summary>
public static class Sse
{
    public static async IAsyncEnumerable<SseEvent> ReadAsync(Stream stream, [EnumeratorCancellation] CancellationToken ct = default)
    {
        using var reader = new StreamReader(stream, Encoding.UTF8);
        string evt = "message";
        var data = new StringBuilder();
        while (!ct.IsCancellationRequested)
        {
            var line = await reader.ReadLineAsync(ct);
            if (line is null) break;
            if (line.Length == 0)
            {
                if (data.Length > 0 || evt != "message") yield return new SseEvent(evt, data.ToString());
                evt = "message";
                data.Clear();
                continue;
            }
            if (line.StartsWith(':')) continue; // comment / keep-alive
            var colon = line.IndexOf(':');
            var field = colon < 0 ? line : line[..colon];
            var value = colon < 0 ? "" : line[(colon + 1)..].TrimStart(' ');
            switch (field)
            {
                case "event": evt = value; break;
                case "data":
                    if (data.Length > 0) data.Append('\n');
                    data.Append(value);
                    break;
            }
        }
        if (data.Length > 0) yield return new SseEvent(evt, data.ToString());
    }
}
