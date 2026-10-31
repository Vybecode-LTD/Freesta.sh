using System.Text.Json;
using System.Text.Json.Nodes;

namespace Freestash.Client.Downloads;

/// <summary>
/// Writes "&lt;file&gt;.license.json", byte-compatible in shape with the Python CLI's sidecars
/// (freestash/src/freestash/download.py) so `freestash audit` and other tools read both.
/// </summary>
public static class Sidecar
{
    public static async Task<string> WriteAsync(DownloadJob job, CancellationToken ct = default)
    {
        var scored = job.Asset!;
        var asset = scored.Asset with { Renditions = job.Rendition is null ? [] : [job.Rendition] };
        var node = new JsonObject
        {
            ["freestash_sidecar"] = 1,
            ["file"] = job.FileName,
            ["sha256"] = job.Sha256,
            ["retrieved_at"] = DateTimeOffset.UtcNow.ToString("O"),
            ["source_url"] = job.Url.AbsoluteUri,
            ["landing_url"] = asset.LandingUrl,
            ["license"] = JsonSerializer.SerializeToNode(asset.License, FreestashJson.Options),
            ["trust"] = asset.Trust.ToString().ToLowerInvariant(),
            ["use_case"] = job.UseCase.Wire(),
            ["tier"] = scored.Verdict.Tier.Wire(),
            ["attribution"] = scored.Verdict.Attribution,
            ["obligations"] = JsonSerializer.SerializeToNode(scored.Verdict.Obligations, FreestashJson.Options),
            ["reasons"] = JsonSerializer.SerializeToNode(scored.Verdict.Reasons, FreestashJson.Options),
            ["project"] = job.Project,
            ["written_by"] = "freestash-desktop",
            ["asset"] = JsonSerializer.SerializeToNode(asset, FreestashJson.Options),
        };
        var path = job.LocalPath + ".license.json";
        await File.WriteAllTextAsync(path, node.ToJsonString(new JsonSerializerOptions { WriteIndented = true,
            Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping }), ct);
        return path;
    }
}
