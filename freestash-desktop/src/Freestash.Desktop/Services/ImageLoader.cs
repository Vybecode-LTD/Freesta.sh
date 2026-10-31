using System.Collections.Concurrent;
using System.Net;
using System.Security.Cryptography;
using System.Text;
using Avalonia.Media;
using Avalonia.Media.Imaging;
using Avalonia.Svg.Skia;
using Avalonia.Threading;
using Freestash.Client.Settings;

namespace Freestash.Desktop.Services;

/// <summary>
/// Thumbnail loader: shared HttpClient, decode-to-width (memory friendly), small in-memory LRU, disk cache.
/// Hosts that refuse hotlinking just fail; the AsyncImage control shows a clean placeholder.
/// </summary>
public sealed class ImageLoader : IDisposable
{
    private readonly HttpClient _http;
    private readonly string _diskDir;
    private readonly ConcurrentDictionary<string, Task<IImage?>> _inflight = new();
    private readonly LinkedList<(string Key, IImage Image)> _lru = new();
    private readonly Dictionary<string, LinkedListNode<(string Key, IImage Image)>> _index = new();
    private const int MaxMemoryItems = 400;

    public ImageLoader()
    {
        _http = new HttpClient(new SocketsHttpHandler { AutomaticDecompression = DecompressionMethods.All, MaxConnectionsPerServer = 6, ConnectTimeout = TimeSpan.FromSeconds(6) })
        {
            Timeout = TimeSpan.FromSeconds(12), // per-host limits come from the handler; one slow host can't starve the rest
        };
        _http.DefaultRequestHeaders.UserAgent.ParseAdd("FreestashDesktop/0.1 (+https://freesta.sh; thumbnail preview)");
        _diskDir = Path.Combine(AppPaths.CacheDirectory(), "thumbs");
        Directory.CreateDirectory(_diskDir);
    }

    public Task<IImage?> LoadAsync(string url, int decodeWidth)
    {
        var key = $"{decodeWidth}|{url}";
        lock (_lru)
        {
            if (_index.TryGetValue(key, out var node))
            {
                _lru.Remove(node);
                _lru.AddFirst(node);
                return Task.FromResult<IImage?>(node.Value.Image);
            }
        }
        return _inflight.GetOrAdd(key, _ => LoadCoreAsync(url, decodeWidth, key));
    }

    private async Task<IImage?> LoadCoreAsync(string url, int decodeWidth, string key)
    {
        try
        {
            var bytes = await GetBytesAsync(url).ConfigureAwait(false);
            if (bytes is null) return null;
            IImage? image;
            if (IsSvg(url, bytes))
            {
                var source = DecodeSvg(bytes); // parse off the UI thread...
                image = source is null ? null : await Dispatcher.UIThread.InvokeAsync(() => (IImage)new SvgImage { Source = source }); // ...wrap on it
            }
            else
            {
                image = DecodeBitmap(bytes, decodeWidth);
            }
            if (image is null) return null;
            lock (_lru)
            {
                _index[key] = _lru.AddFirst((key, image));
                while (_lru.Count > MaxMemoryItems)
                {
                    var last = _lru.Last!;
                    _lru.RemoveLast();
                    _index.Remove(last.Value.Key);
                }
            }
            return image;
        }
        catch
        {
            return null;
        }
        finally
        {
            _inflight.TryRemove(key, out _);
        }
    }

    private async Task<byte[]?> GetBytesAsync(string url)
    {
        var file = Path.Combine(_diskDir, Convert.ToHexStringLower(SHA1.HashData(Encoding.UTF8.GetBytes(url))));
        if (File.Exists(file)) return await File.ReadAllBytesAsync(file).ConfigureAwait(false);
        if (url.StartsWith("data:", StringComparison.Ordinal)) return null;
        using var res = await _http.GetAsync(url).ConfigureAwait(false);
        if (!res.IsSuccessStatusCode) return null;
        var bytes = await res.Content.ReadAsByteArrayAsync().ConfigureAwait(false);
        if (bytes.Length is 0 or > 25_000_000) return null;
        await File.WriteAllBytesAsync(file, bytes).ConfigureAwait(false);
        return bytes;
    }

    private static bool IsSvg(string url, byte[] bytes) =>
        url.Contains(".svg", StringComparison.OrdinalIgnoreCase) ||
        (bytes.Length > 5 && Encoding.UTF8.GetString(bytes, 0, Math.Min(bytes.Length, 256)).Contains("<svg", StringComparison.OrdinalIgnoreCase));

    private static SvgSource? DecodeSvg(byte[] bytes)
    {
        using var ms = new MemoryStream(bytes);
        return SvgSource.LoadFromStream(ms, null);
    }

    private static IImage? DecodeBitmap(byte[] bytes, int width)
    {
        using var ms = new MemoryStream(bytes);
        return width > 0 ? Bitmap.DecodeToWidth(ms, width, BitmapInterpolationMode.MediumQuality) : new Bitmap(ms);
    }

    public void Dispose() => _http.Dispose();
}
