// Mirrors freestash/src/freestash/models.py (and web/src/lib/types.ts). JSON is snake_case; enums are lowercase strings.
// When the Python models change, change these too: see docs/CONTRACT.md.

using System.Text.Json.Serialization;

namespace Freestash.Client;

public enum MediaType { Image, Audio, Video, Texture, Hdri, Model, Font, Icon, Brush, Shape, Sprite }

public enum UseCase { Reference, Demo, Client, Bundled, Merch }

public enum Tier { Green, Yellow, Red }

public enum Trust { Institution, Government, Curated, Community, Uploader, Unknown }

public sealed record LicenseInfo(string Id, string Label, string? Url = null, string? Raw = null);

public sealed record Rendition(string Url, string Label = "original", int? Width = null, int? Height = null,
                               string? Mime = null, long? Bytes = null)
{
    [JsonIgnore]
    public string SizeText => Width is > 0 && Height is > 0 ? $"{Width}×{Height}" : Formatting.Bytes(Bytes);
}

public sealed record Asset
{
    public required string Provider { get; init; }
    public required string SourceId { get; init; }
    public required string Title { get; init; }
    public MediaType MediaType { get; init; }
    public required LicenseInfo License { get; init; }
    public Trust Trust { get; init; }
    public string? LandingUrl { get; init; }
    public string? SourceName { get; init; }
    public string? Creator { get; init; }
    public string? CreatorUrl { get; init; }
    public string? ThumbnailUrl { get; init; }
    public string? PreviewUrl { get; init; }
    public List<Rendition> Renditions { get; init; } = [];
    public int? Width { get; init; }
    public int? Height { get; init; }
    public double? DurationSeconds { get; init; }
    public string? Date { get; init; }
    public int? Year { get; init; }
    public List<string> Tags { get; init; } = [];
    public string? Description { get; init; }
    public string? AttributionHint { get; init; }
    public List<string> Notes { get; init; } = [];
    public List<string> Tips { get; init; } = [];
    public bool DetailRequired { get; init; }
    public Dictionary<string, object?> Extra { get; init; } = [];
    /// <summary>One result holding many files (contract packs-and-new-kinds).</summary>
    public bool IsPack { get; init; }
    public int? ItemCount { get; init; }
    public List<string> Formats { get; init; } = [];
    /// <summary>When the source licenses each file: their distinct licenses and how many files were read
    /// (null: <see cref="License"/> covers the whole pack).</summary>
    public List<LicenseInfo> MemberLicenses { get; init; } = [];
    public int? MembersChecked { get; init; }

    [JsonIgnore] public string Uid => $"{Provider}:{SourceId}";
}

public sealed record Verdict(UseCase UseCase, Tier Tier, List<string> Reasons, List<string> Obligations, string? Attribution = null);

public sealed record ScoredAsset(string Uid, Asset Asset, Verdict Verdict);

public sealed record ProviderStatus(string Provider, bool Ok, int Count = 0, int? Total = null, string? Error = null, int ElapsedMs = 0);

/// <summary>One SSE `batch` event from /api/search/stream.</summary>
public sealed record StreamBatch(ProviderStatus Status, int Hidden, List<ScoredAsset> Results);

public sealed record AssetDetail(string Uid, Asset Asset, Verdict Verdict, Dictionary<string, Verdict> Verdicts, string AttributionHtml);

public sealed record ProviderInfo(string Id, string Name, string Homepage, List<string> MediaTypes, bool Enabled,
                                  string? KeySetting, bool KeyOptional, string? KeySignupUrl, bool VerifiedLive, List<string> Notes);

public sealed record CollectionItem(string Uid, Asset Asset, Verdict Verdict, string? Note, string? AddedAt);

public sealed record Collection(string Id, string Name, string? Description, UseCase UseCase, string? TeamId,
                                string? CreatedAt, int ItemCount, List<CollectionItem>? Items = null);

public sealed record LedgerEntry(string Id, string AssetUid, string Provider, string Title, string? Creator, string? LandingUrl,
                                 string? FileUrl, string LicenseId, string LicenseLabel, string? LicenseUrl, Trust Trust,
                                 UseCase UseCase, Tier Tier, string? Attribution, string? Project, string RetrievedAt);

public sealed record LicenseCheckResult(LicenseInfo RecognizedAs, Dictionary<string, Verdict> Verdicts);

public sealed record HealthInfo(bool Ok, string Version, string AuthMode);

public sealed record PdCutoff(int Works, int SoundRecordings);

public sealed record SearchRequest(string Query, IReadOnlyList<MediaType> Media, UseCase Use, Tier MaxTier,
                                   IReadOnlyList<string>? Providers = null, int Limit = 12, int Page = 1, bool Packs = false);

/// <summary>A query word read as a category ("sfx" → audio) or as packs ("pack": no media type); <see cref="Word"/> is
/// exactly as typed.</summary>
public sealed record QueryPick(string Word, MediaType? MediaType, bool Packs = false);

/// <summary>What the engine made of a query (<c>GET /api/search/parse</c>). Empty <see cref="MediaTypes"/> means no
/// medium was picked; <see cref="Packs"/> that a pack word was.</summary>
public sealed record ParsedQuery(string Original, string Q, List<MediaType> MediaTypes, List<QueryPick> Picks, bool Packs = false);

public static class Formatting
{
    public static string Bytes(long? n) => n switch
    {
        null or 0 => "",
        > 1_000_000_000 => $"{n / 1e9:0.0} GB",
        > 1_000_000 => $"{n / 1e6:0.0} MB",
        _ => $"{Math.Max(1, n.Value / 1000)} KB",
    };

    public static string Speed(double bytesPerSecond) => bytesPerSecond <= 0 ? "" : $"{Bytes((long)bytesPerSecond)}/s";

    public static string Wire(this MediaType m) => m.ToString().ToLowerInvariant();
    public static string Wire(this UseCase u) => u.ToString().ToLowerInvariant();
    public static string Wire(this Tier t) => t.ToString().ToLowerInvariant();
}
