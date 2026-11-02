// Grouped results and query-word chips (contract dev plans/contracts/grouped-results.md). The web's
// lib/results.ts follows the same rules; keep the two in step (tests: ResultGroupsTests ↔ results.test.ts).
namespace Freestash.Client;

/// <summary>One category's results: <see cref="Items"/> is what's shown, <see cref="Total"/> what there is.</summary>
public sealed record ResultSection(MediaType Id, string Label, int Total, IReadOnlyList<ScoredAsset> Items);

public static class ResultGroups
{
    /// <summary>Cards per section until "Show all (n)".</summary>
    public const int SectionSize = 8;

    /// <summary>Round-robin across sources (so one chatty source can't bury the rest), clear results first.</summary>
    public static List<ScoredAsset> Interleave(IEnumerable<IReadOnlyList<ScoredAsset>> byProvider)
    {
        var lists = byProvider.ToList();
        var ordered = new List<ScoredAsset>();
        foreach (var tier in new[] { Tier.Green, Tier.Yellow, Tier.Red })
        {
            var queues = lists.Select(l => new Queue<ScoredAsset>(l.Where(s => s.Verdict.Tier == tier))).ToList();
            while (queues.Any(q => q.Count > 0))
                foreach (var q in queues)
                    if (q.TryDequeue(out var s)) ordered.Add(s);
        }
        return ordered;
    }

    /// <summary>Sections only with more than one medium selected; one medium looks as it always has (one grid).</summary>
    public static bool IsGrouped(IReadOnlyCollection<MediaType> media) => media.Count > 1;

    /// <summary>One section per category that has results, in the shared order, each keeping the incoming order.</summary>
    public static List<ResultSection> Group(IReadOnlyList<ScoredAsset> ordered, IReadOnlySet<MediaType> expanded)
    {
        var byId = ordered.GroupBy(s => s.Asset.MediaType).ToDictionary(g => g.Key, g => g.ToList());
        var order = Categories.All.Select(c => (c.Id, c.Label))
            .Concat(byId.Keys.Where(id => Categories.All.All(c => c.Id != id)).Select(id => (Id: id, Label: id.Wire())));
        return order.Where(c => byId.ContainsKey(c.Id)).Select(c =>
        {
            var all = byId[c.Id];
            return new ResultSection(c.Id, c.Label, all.Count, expanded.Contains(c.Id) ? all : all.Take(SectionSize).ToList());
        }).ToList();
    }
}

/// <summary>The query as last read: what was typed, what is searched, the words kept as words, the picks shown as
/// chips, and the media the user had chosen before the picks replaced them.</summary>
public sealed record QueryReading(string Original, string Q, IReadOnlyList<string> Keep, IReadOnlyList<QueryPick> Picks,
                                  IReadOnlyList<MediaType> Before)
{
    /// <summary>Read a query again only when its text changed, so a removed pick stays removed when Search is pressed again.</summary>
    public static bool NeedsParse(string text, QueryReading? reading) => reading is null || text.Trim() != reading.Q;

    /// <summary>A fresh read of a typed query. Picks replace the media; without picks the media stay as they are.</summary>
    public static (QueryReading Reading, IReadOnlyList<MediaType> Media) Read(ParsedQuery parsed, IReadOnlyList<MediaType> media, QueryReading? prev)
    {
        var before = prev is { Picks.Count: > 0 } ? prev.Before : media;
        return (new QueryReading(parsed.Original, parsed.Q, [], parsed.Picks, before), parsed.MediaTypes.Count > 0 ? parsed.MediaTypes : media);
    }

    /// <summary>The read after a chip was removed (<paramref name="parsed"/> came back for <c>reading.Original</c> with
    /// <paramref name="keep"/>). With no picks left the media go back to the user's own selection.</summary>
    public static (QueryReading Reading, IReadOnlyList<MediaType> Media) Drop(ParsedQuery parsed, QueryReading reading, IReadOnlyList<string> keep) =>
        (reading with { Q = parsed.Q, Keep = keep, Picks = parsed.Picks }, parsed.MediaTypes.Count > 0 ? parsed.MediaTypes : reading.Before);

    /// <summary>Choosing media by hand takes over from the picks: the chips go, the text stays.</summary>
    public static QueryReading? WithoutPicks(QueryReading? reading) => reading is null ? null : reading with { Picks = [] };
}
