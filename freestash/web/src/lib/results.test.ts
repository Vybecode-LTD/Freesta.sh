import { describe, expect, it } from "vitest";
import { dropPick, groupResults, interleave, isGrouped, needsParse, readQuery, SECTION_SIZE, withoutPicks } from "./results";
import type { MediaType, ParsedQuery, ScoredAsset, Tier } from "./types";

const card = (uid: string, media_type: MediaType = "image", tier: Tier = "green"): ScoredAsset => ({
  uid,
  asset: { provider: uid.split(":")[0], source_id: uid, title: uid, media_type, license: { id: "CC0-1.0", label: "CC0" },
           trust: "institution", renditions: [], tags: [], notes: [], tips: [], detail_required: false, extra: {} },
  verdict: { use_case: "demo", tier, reasons: [], obligations: [] },
});
const many = (n: number, media: MediaType, provider = "p") => Array.from({ length: n }, (_, i) => card(`${provider}:${media}${i}`, media));
const parsed = (over: Partial<ParsedQuery> = {}): ParsedQuery => ({ original: "rain sfx", q: "rain", media_types: [], picks: [], ...over });
const SFX = { word: "sfx", media_type: "audio" as MediaType };

describe("interleave", () => {
  it("takes turns across sources, clear results first", () => {
    const out = interleave(new Map([["a", [card("a:1", "image", "yellow"), card("a:2")]], ["b", [card("b:1"), card("b:2")]]]));
    expect(out.map((s) => s.uid)).toEqual(["a:2", "b:1", "b:2", "a:1"]);
  });
});

describe("groupResults", () => {
  it("makes one section per category in the shared order, skipping empty ones", () => {
    const sections = groupResults([...many(2, "font"), ...many(1, "image"), ...many(3, "audio")], new Set());
    expect(sections.map((s) => [s.id, s.label, s.total])).toEqual([["image", "Images", 1], ["audio", "Audio", 3], ["font", "Fonts", 2]]);
  });

  it("shows 8 per section until that section is expanded, keeping the incoming order", () => {
    const images = many(11, "image");
    const [collapsed] = groupResults(images, new Set());
    expect(SECTION_SIZE).toBe(8);
    expect(collapsed.items.map((s) => s.uid)).toEqual(images.slice(0, 8).map((s) => s.uid));
    expect(collapsed.total).toBe(11);
    const [open] = groupResults(images, new Set<MediaType>(["image"]));
    expect(open.items).toHaveLength(11);
  });

  it("is only used with more than one medium selected", () => {
    expect(isGrouped(["image"])).toBe(false);
    expect(isGrouped(["image", "font"])).toBe(true);
  });
});

describe("reading query words", () => {
  it("a pick replaces the media and remembers the selection it replaced", () => {
    const { reading, media } = readQuery(parsed({ media_types: ["audio"], picks: [SFX] }), ["image", "font"], null);
    expect(media).toEqual(["audio"]);
    expect(reading).toEqual({ original: "rain sfx", q: "rain", keep: [], picks: [SFX], before: ["image", "font"] });
  });

  it("a new query without picks leaves the media as they are", () => {
    const first = readQuery(parsed({ media_types: ["audio"], picks: [SFX] }), ["image"], null);
    const next = readQuery(parsed({ original: "thunder", q: "thunder" }), first.media, first.reading);
    expect(next.media).toEqual(["audio"]);
    expect(next.reading.picks).toEqual([]);
  });

  it("a second picked query still remembers the user's own selection", () => {
    const first = readQuery(parsed({ media_types: ["audio"], picks: [SFX] }), ["image"], null);
    const second = readQuery(parsed({ original: "font serif", q: "serif", media_types: ["font"], picks: [{ word: "font", media_type: "font" }] }),
      first.media, first.reading);
    expect(second.reading.before).toEqual(["image"]);
  });

  it("removing the last pick searches the word as a word in the media chosen before", () => {
    const { reading } = readQuery(parsed({ media_types: ["audio"], picks: [SFX] }), ["image", "font"], null);
    const dropped = dropPick(parsed({ q: "rain sfx" }), reading, ["sfx"]);
    expect(dropped.media).toEqual(["image", "font"]);
    expect(dropped.reading).toMatchObject({ q: "rain sfx", keep: ["sfx"], picks: [], original: "rain sfx" });
  });

  it("removing one of two picks keeps the other's media", () => {
    const font = { word: "font", media_type: "font" as MediaType };
    const { reading } = readQuery(parsed({ original: "sfx font x", q: "x", media_types: ["audio", "font"], picks: [SFX, font] }), ["image"], null);
    const dropped = dropPick(parsed({ original: "sfx font x", q: "sfx x", media_types: ["font"], picks: [font] }), reading, ["sfx"]);
    expect(dropped.media).toEqual(["font"]);
    expect(dropped.reading.picks).toEqual([font]);
  });

  it("an unchanged query isn't read again, so a removed pick stays removed", () => {
    const { reading } = readQuery(parsed({ media_types: ["audio"], picks: [SFX] }), ["image"], null);
    const dropped = dropPick(parsed({ q: "rain sfx" }), reading, ["sfx"]);
    expect(needsParse("rain sfx", dropped.reading)).toBe(false);
    expect(needsParse("  rain sfx ", dropped.reading)).toBe(false);
    expect(needsParse("rain sfx loud", dropped.reading)).toBe(true);
    expect(needsParse("rain", null)).toBe(true);
  });

  it("choosing media by hand settles the picks", () => {
    const { reading } = readQuery(parsed({ media_types: ["audio"], picks: [SFX] }), ["image"], null);
    expect(withoutPicks(reading)).toMatchObject({ q: "rain", picks: [] });
    expect(withoutPicks(null)).toBeNull();
  });
});
