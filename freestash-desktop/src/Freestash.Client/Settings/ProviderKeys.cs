using System.Text.Json;
using Freestash.Client.Account;

namespace Freestash.Client.Settings;

/// <summary>
/// Every provider credential the engine can use, with where to get it. Built in from shared/provider-keys.json
/// (generated from the engine's KEY_CATALOG, embedded at build), so the desktop shows the same help as the web
/// even offline. The app refreshes it from GET /api/keys/catalog when it can reach the server.
/// </summary>
public static class ProviderKeys
{
    private static readonly Lazy<IReadOnlyList<KeySpec>> Embedded = new(LoadEmbedded);

    public static IReadOnlyList<KeySpec> All => Embedded.Value;

    private static IReadOnlyList<KeySpec> LoadEmbedded()
    {
        using var stream = typeof(ProviderKeys).Assembly.GetManifestResourceStream("provider-keys.json")
                           ?? throw new InvalidOperationException("provider-keys.json is not embedded; check Freestash.Client.csproj");
        return JsonSerializer.Deserialize<List<KeySpec>>(stream, FreestashJson.Options) ?? [];
    }
}
