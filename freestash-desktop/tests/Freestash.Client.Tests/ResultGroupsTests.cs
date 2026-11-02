// The same cases as the web's lib/results.test.ts: both apps group results and read query words alike.
using System.Net;
using System.Text;

namespace Freestash.Client.Tests;

public class ResultGroupsTests
{
    private static ScoredAsset Card(string uid, MediaType media = MediaType.Image, Tier tier = Tier.Green, bool pack = false) => new(uid,
        new Asset { Provider = uid.Split(':')[0], SourceId = uid, Title = uid, MediaType = media, License = new LicenseInfo("CC0-1.0", "CC0"), IsPack = pack },
        new Verdict(UseCase.Demo, tier, [], []));

    private static List<ScoredAsset> Many(int n, MediaType media) => Enumerable.Range(0, n).Select(i => Card($"p:{media}{i}", media)).ToList();

    private static ParsedQuery Parsed(string q = "rain", List<MediaType>? media = null, List<QueryPick>? picks = null, string original = "rain sfx",
                                      bool packs = false)
        => new(original, q, media ?? [], picks ?? [], packs);

    private static readonly QueryPick Sfx = new("sfx", MediaType.Audio);
    private static readonly QueryPick Pack = new("pack", null, true);

    [Fact]
    public void Interleave_takes_turns_across_sources_clear_first()
    {
        var out_ = ResultGroups.Interleave([[Card("a:1", tier: Tier.Yellow), Card("a:2")], [Card("b:1"), Card("b:2")]]);
        Assert.Equal(["a:2", "b:1", "b:2", "a:1"], out_.Select(s => s.Uid));
    }

    [Fact]
    public void Group_makes_one_section_per_category_in_the_shared_order_skipping_empty_ones()
    {
        var sections = ResultGroups.Group([.. Many(2, MediaType.Font), .. Many(1, MediaType.Image), .. Many(3, MediaType.Audio)], new HashSet<MediaType>());
        Assert.Equal([(MediaType.Image, "Images", 1), (MediaType.Audio, "Audio", 3), (MediaType.Font, "Fonts", 2)],
                     sections.Select(s => (s.Id, s.Label, s.Total)));
    }

    [Fact]
    public void Group_shows_eight_per_section_until_expanded_keeping_the_incoming_order()
    {
        var images = Many(11, MediaType.Image);
        var collapsed = ResultGroups.Group(images, new HashSet<MediaType>())[0];
        Assert.Equal(8, ResultGroups.SectionSize);
        Assert.Equal(images.Take(8).Select(s => s.Uid), collapsed.Items.Select(s => s.Uid));
        Assert.Equal(11, collapsed.Total);
        Assert.Equal(11, ResultGroups.Group(images, new HashSet<MediaType> { MediaType.Image })[0].Items.Count);
    }

    [Fact]
    public void Group_puts_packs_first_in_each_section_each_group_keeping_its_order()
    {
        var images = ResultGroups.Group([Card("a:1"), Card("a:p1", pack: true), Card("a:2"), Card("a:p2", tier: Tier.Yellow, pack: true)],
                                        new HashSet<MediaType>())[0];
        Assert.Equal(["a:p1", "a:p2", "a:1", "a:2"], images.Items.Select(s => s.Uid));
    }

    [Fact]
    public void LeadPacks_puts_packs_first_for_the_one_grid_view_and_leaves_a_list_without_packs_alone()
    {
        Assert.Equal(["b:p", "a:1", "a:2"], ResultGroups.LeadPacks([Card("a:1"), Card("b:p", MediaType.Audio, pack: true), Card("a:2")]).Select(s => s.Uid));
        Assert.Equal(["a:1", "a:2"], ResultGroups.LeadPacks([Card("a:1"), Card("a:2")]).Select(s => s.Uid));
    }

    [Fact]
    public void Pack_badge_counts_the_files_when_the_source_does()
    {
        var a = Card("p:1", MediaType.Audio, pack: true).Asset;
        Assert.Equal("Pack · 4,133 files", PackText.Badge(a with { ItemCount = 4133 }));
        Assert.Equal("Pack · 1 file", PackText.Badge(a with { ItemCount = 1 }));
        Assert.Equal("Pack", PackText.Badge(a));
        Assert.Equal("WAV · MP3", PackText.Formats(a with { Formats = ["wav", "mp3"] }));
    }

    [Fact]
    public void Pack_says_which_licenses_are_inside_and_how_far_they_were_read()
    {
        var a = Card("p:1", MediaType.Audio, pack: true).Asset;
        LicenseInfo cc0 = new("CC0-1.0", "CC0 1.0"), by = new("CC-BY-4.0", "CC BY 4.0");
        Assert.Null(PackText.LicensesInside(a));
        Assert.Equal("CC0 1.0, CC BY 4.0", PackText.LicensesInside(a with { MemberLicenses = [cc0, by], MembersChecked = 4, ItemCount = 4 }));
        Assert.Equal("CC0 1.0 · read for 1 of 24 files", PackText.LicensesInside(a with { MemberLicenses = [cc0], MembersChecked = 1, ItemCount = 24 }));
        Assert.Equal("CC0 1.0 · read for 3 files", PackText.LicensesInside(a with { MemberLicenses = [cc0], MembersChecked = 3 }));
        Assert.Equal("None read yet · read for 0 of 5 files", PackText.LicensesInside(a with { MembersChecked = 0, ItemCount = 5 }));
    }

    [Fact]
    public void Grouping_is_only_for_more_than_one_medium()
    {
        Assert.False(ResultGroups.IsGrouped([MediaType.Image]));
        Assert.True(ResultGroups.IsGrouped([MediaType.Image, MediaType.Font]));
    }

    [Fact]
    public void A_pick_replaces_the_media_and_remembers_the_selection_it_replaced()
    {
        var (reading, media, _) = QueryReading.Read(Parsed(media: [MediaType.Audio], picks: [Sfx]), [MediaType.Image, MediaType.Font], null);
        Assert.Equal([MediaType.Audio], media);
        Assert.Equal(("rain sfx", "rain", 0), (reading.Original, reading.Q, reading.Keep.Count));
        Assert.Equal([Sfx], reading.Picks);
        Assert.Equal([MediaType.Image, MediaType.Font], reading.Before);
        Assert.False(reading.PacksBefore);
    }

    [Fact]
    public void A_new_query_without_picks_leaves_the_media_as_they_are()
    {
        var first = QueryReading.Read(Parsed(media: [MediaType.Audio], picks: [Sfx]), [MediaType.Image], null);
        var next = QueryReading.Read(Parsed("thunder", original: "thunder"), first.Media, first.Reading);
        Assert.Equal([MediaType.Audio], next.Media);
        Assert.Empty(next.Reading.Picks);
    }

    [Fact]
    public void A_second_picked_query_still_remembers_the_users_own_selection()
    {
        var first = QueryReading.Read(Parsed(media: [MediaType.Audio], picks: [Sfx]), [MediaType.Image], null);
        var second = QueryReading.Read(Parsed("serif", [MediaType.Font], [new("font", MediaType.Font)], "font serif"), first.Media, first.Reading);
        Assert.Equal([MediaType.Image], second.Reading.Before);
    }

    [Fact]
    public void Removing_the_last_pick_searches_the_word_as_a_word_in_the_media_chosen_before()
    {
        var (reading, _, _) = QueryReading.Read(Parsed(media: [MediaType.Audio], picks: [Sfx]), [MediaType.Image, MediaType.Font], null);
        var dropped = QueryReading.Drop(Parsed("rain sfx"), reading, ["sfx"]);
        Assert.Equal([MediaType.Image, MediaType.Font], dropped.Media);
        Assert.Equal(("rain sfx", "rain sfx", 0), (dropped.Reading.Q, dropped.Reading.Original, dropped.Reading.Picks.Count));
        Assert.Equal(["sfx"], dropped.Reading.Keep);
    }

    [Fact]
    public void Removing_one_of_two_picks_keeps_the_others_media()
    {
        var font = new QueryPick("font", MediaType.Font);
        var (reading, _, _) = QueryReading.Read(Parsed("x", [MediaType.Audio, MediaType.Font], [Sfx, font], "sfx font x"), [MediaType.Image], null);
        var dropped = QueryReading.Drop(Parsed("sfx x", [MediaType.Font], [font], "sfx font x"), reading, ["sfx"]);
        Assert.Equal([MediaType.Font], dropped.Media);
        Assert.Equal([font], dropped.Reading.Picks);
    }

    [Fact]
    public void An_unchanged_query_is_not_read_again_so_a_removed_pick_stays_removed()
    {
        var (reading, _, _) = QueryReading.Read(Parsed(media: [MediaType.Audio], picks: [Sfx]), [MediaType.Image], null);
        var dropped = QueryReading.Drop(Parsed("rain sfx"), reading, ["sfx"]);
        Assert.False(QueryReading.NeedsParse("rain sfx", dropped.Reading));
        Assert.False(QueryReading.NeedsParse("  rain sfx ", dropped.Reading));
        Assert.True(QueryReading.NeedsParse("rain sfx loud", dropped.Reading));
        Assert.True(QueryReading.NeedsParse("rain", null));
    }

    [Fact]
    public void A_pack_word_turns_packs_on_and_removing_its_chip_puts_back_the_users_own_setting()
    {
        var read = QueryReading.Read(Parsed(media: [MediaType.Audio], picks: [Sfx, Pack], original: "rain sfx pack", packs: true), [MediaType.Image], null, false);
        Assert.Equal([MediaType.Audio], read.Media);
        Assert.Equal((true, false), (read.Packs, read.Reading.PacksBefore));
        var dropped = QueryReading.Drop(Parsed("rain pack", [MediaType.Audio], [Sfx], "rain sfx pack"), read.Reading, ["pack"]);
        Assert.Equal([MediaType.Audio], dropped.Media);
        Assert.False(dropped.Packs);
        var kept = QueryReading.Drop(Parsed("rain sfx", [], [Pack], "rain sfx pack", packs: true), read.Reading, ["sfx"]);
        Assert.Equal([MediaType.Image], kept.Media);
        Assert.True(kept.Packs);
    }

    [Fact]
    public void Packs_the_user_turned_on_stay_on_through_reads_without_a_pack_word()
    {
        var read = QueryReading.Read(Parsed(media: [MediaType.Audio], picks: [Sfx]), [MediaType.Image], null, true);
        Assert.Equal((true, true), (read.Packs, read.Reading.PacksBefore));
        Assert.True(QueryReading.Drop(Parsed("rain sfx"), read.Reading, ["sfx"]).Packs);
    }

    [Fact]
    public void Choosing_media_by_hand_settles_the_picks()
    {
        var (reading, _, _) = QueryReading.Read(Parsed(media: [MediaType.Audio], picks: [Sfx]), [MediaType.Image], null);
        Assert.Equal(("rain", 0), (QueryReading.WithoutPicks(reading)!.Q, QueryReading.WithoutPicks(reading)!.Picks.Count));
        Assert.Null(QueryReading.WithoutPicks(null));
    }

    [Fact]
    public void The_shared_categories_cover_every_media_type_once()
    {
        Assert.Equal(Enum.GetValues<MediaType>().Order(), Categories.All.Select(c => c.Id).Order());
        Assert.Equal(["Images", "Audio", "Video", "Textures", "HDRIs", "3D", "Fonts", "Icons", "Brushes", "Shapes", "Sprites"],
                     Categories.All.Select(c => c.Label));
        var game = Assert.Single(Categories.Presets);
        Assert.Equal(("Game assets", true), (game.Label, game.Packs));
        Assert.Equal([MediaType.Audio, MediaType.Texture, MediaType.Model, MediaType.Font, MediaType.Icon, MediaType.Sprite], game.Media);
    }

    [Fact]
    public async Task Parse_calls_the_api_with_the_kept_words_and_reads_its_answer()
    {
        var handler = new StubHandler(_ => new HttpResponseMessage(HttpStatusCode.OK)
        {
            Content = new StringContent("""{"original":"sound of rain sfx pack","q":"sound of rain","media_types":["audio"],"packs":true,"picks":[{"word":"sfx","media_type":"audio","packs":false},{"word":"pack","media_type":null,"packs":true}]}""",
                                        Encoding.UTF8, "application/json"),
        });
        using var api = new FreestashApiClient(new Uri("http://localhost:8787"), handler: handler);
        var parsed = await api.ParseQueryAsync("sound of rain sfx", ["sound"], TestContext.Current.CancellationToken);
        Assert.Equal("/api/search/parse?q=sound%20of%20rain%20sfx&keep=sound", handler.Requests[0].RequestUri!.PathAndQuery);
        Assert.Equal("sound of rain", parsed.Q);
        Assert.Equal([MediaType.Audio], parsed.MediaTypes);
        Assert.Equal([new QueryPick("sfx", MediaType.Audio), new QueryPick("pack", null, true)], parsed.Picks);
        Assert.True(parsed.Packs);
    }
}
