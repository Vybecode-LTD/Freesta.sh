import { describe, expect, it } from "vitest";
import {
  dropPick, formatList, groupResults, interleave, isGrouped, leadPacks, licensesInside, needsParse, packBadge, readQuery, SECTION_SIZE,
  withoutPicks,
} from "./results";
import type { MediaType, ParsedQuery, ScoredAsset, Tier } from "./types";

const card = (uid: string, media_type: MediaType = "image", tier: Tier = "green", is_pack = false): ScoredAsset => ({
  uid,
  asset: { provider: uid.split(":")[0], source_id: uid, title: uid, media_type, license: { id: "CC0-1.0", label: "CC0" },
           trust: "institution", renditions: [], tags: [], notes: [], tips: [], detail_required: false, extra: {},
           is_pack, item_count: null, formats: [], member_licenses: [], members_checked: null },
  verdict: { use_case: "demo", tier, reasons: [], obligations: [] },
});
const many = (n: number, media: MediaType, provider = "p") => Array.from({ length: n }, (_, i) => card(`${provider}:${media}${i}`, media));
const parsed = (over: Partial<ParsedQuery> = {}): ParsedQuery => ({ original: "rain sfx", q: "rain", media_types: [], packs: false, picks: [], ...over });
const SFX = { word: "sfx", media_type: "audio" as MediaType, packs: false };
const FONT = { word: "font", media_type: "font" as MediaType, packs: false };
const PACK = { word: "pack", media_type: null, packs: true };

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

  it("puts packs first in each section, each group keeping its order", () => {
    const [images] = groupResults([card("a:1"), card("a:p1", "image", "green", true), card("a:2"), card("a:p2", "image", "yellow", true)], new Set());
    expect(images.items.map((s) => s.uid)).toEqual(["a:p1", "a:p2", "a:1", "a:2"]);
  });

  it("is only used with more than one medium selected", () => {
    expect(isGrouped(["image"])).toBe(false);
    expect(isGrouped(["image", "font"])).toBe(true);
  });
});

describe("leadPacks", () => {
  it("puts packs first for the one-grid view too, and leaves a list without packs alone", () => {
    const list = [card("a:1"), card("b:p", "audio", "green", true), card("a:2")];
    expect(leadPacks(list).map((s) => s.uid)).toEqual(["b:p", "a:1", "a:2"]);
    const plain = [card("a:1"), card("a:2")];
    expect(leadPacks(plain)).toEqual(plain);
  });
});

describe("pack words", () => {
  const pack = (over: Partial<ScoredAsset["asset"]>) => ({ ...card("p:1", "audio", "green", true).asset, ...over });
  it("badge counts the files when the source does", () => {
    expect(packBadge(pack({ item_count: 4133 }))).toBe("Pack · 4,133 files");
    expect(packBadge(pack({ item_count: 1 }))).toBe("Pack · 1 file");
    expect(packBadge(pack({}))).toBe("Pack");
    expect(formatList(pack({ formats: ["wav", "mp3"] }))).toBe("WAV · MP3");
  });

  it("says which licenses are inside and how far they were read", () => {
    const cc0 = { id: "CC0-1.0", label: "CC0 1.0" };
    const by = { id: "CC-BY-4.0", label: "CC BY 4.0" };
    expect(licensesInside(pack({}))).toBeNull(); // one license for the whole pack
    expect(licensesInside(pack({ member_licenses: [cc0, by], members_checked: 4, item_count: 4 }))).toBe("CC0 1.0, CC BY 4.0");
    expect(licensesInside(pack({ member_licenses: [cc0], members_checked: 1, item_count: 24 }))).toBe("CC0 1.0 · read for 1 of 24 files");
    expect(licensesInside(pack({ member_licenses: [cc0], members_checked: 3 }))).toBe("CC0 1.0 · read for 3 files");
    expect(licensesInside(pack({ members_checked: 0, item_count: 5 }))).toBe("None read yet · read for 0 of 5 files");
  });
});

describe("reading query words", () => {
  it("a pick replaces the media and remembers the selection it replaced", () => {
    const { reading, media } = readQuery(parsed({ media_types: ["audio"], picks: [SFX] }), ["image", "font"], null);
    expect(media).toEqual(["audio"]);
    expect(reading).toEqual({ original: "rain sfx", q: "rain", keep: [], picks: [SFX], before: ["image", "font"], packsBefore: false });
  });

  it("a new query without picks leaves the media as they are", () => {
    const first = readQuery(parsed({ media_types: ["audio"], picks: [SFX] }), ["image"], null);
    const next = readQuery(parsed({ original: "thunder", q: "thunder" }), first.media, first.reading);
    expect(next.media).toEqual(["audio"]);
    expect(next.reading.picks).toEqual([]);
  });

  it("a second picked query still remembers the user's own selection", () => {
    const first = readQuery(parsed({ media_types: ["audio"], picks: [SFX] }), ["image"], null);
    const second = readQuery(parsed({ original: "font serif", q: "serif", media_types: ["font"], picks: [FONT] }),
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
    const { reading } = readQuery(parsed({ original: "sfx font x", q: "x", media_types: ["audio", "font"], picks: [SFX, FONT] }), ["image"], null);
    const dropped = dropPick(parsed({ original: "sfx font x", q: "sfx x", media_types: ["font"], picks: [FONT] }), reading, ["sfx"]);
    expect(dropped.media).toEqual(["font"]);
    expect(dropped.reading.picks).toEqual([FONT]);
  });

  it("an unchanged query isn't read again, so a removed pick stays removed", () => {
    const { reading } = readQuery(parsed({ media_types: ["audio"], picks: [SFX] }), ["image"], null);
    const dropped = dropPick(parsed({ q: "rain sfx" }), reading, ["sfx"]);
    expect(needsParse("rain sfx", dropped.reading)).toBe(false);
    expect(needsParse("  rain sfx ", dropped.reading)).toBe(false);
    expect(needsParse("rain sfx loud", dropped.reading)).toBe(true);
    expect(needsParse("rain", null)).toBe(true);
  });

  it("a pack word turns packs on, and removing its chip puts back the user's own setting", () => {
    const read = readQuery(parsed({ original: "rain sfx pack", media_types: ["audio"], packs: true, picks: [SFX, PACK] }), ["image"], null, false);
    expect([read.media, read.packs, read.reading.packsBefore]).toEqual([["audio"], true, false]);
    const dropped = dropPick(parsed({ original: "rain sfx pack", q: "rain pack", media_types: ["audio"], picks: [SFX] }), read.reading, ["pack"]);
    expect([dropped.media, dropped.packs]).toEqual([["audio"], false]);
    const kept = dropPick(parsed({ original: "rain sfx pack", q: "rain sfx", packs: true, picks: [PACK] }), read.reading, ["sfx"]);
    expect([kept.media, kept.packs]).toEqual([["image"], true]);
  });

  it("packs the user turned on stay on through reads without a pack word", () => {
    const read = readQuery(parsed({ media_types: ["audio"], picks: [SFX] }), ["image"], null, true);
    expect([read.packs, read.reading.packsBefore]).toEqual([true, true]);
    expect(dropPick(parsed({ q: "rain sfx" }), read.reading, ["sfx"]).packs).toBe(true);
  });

  it("choosing media by hand settles the picks", () => {
    const { reading } = readQuery(parsed({ media_types: ["audio"], picks: [SFX] }), ["image"], null);
    expect(withoutPicks(reading)).toMatchObject({ q: "rain", picks: [] });
    expect(withoutPicks(null)).toBeNull();
  });
});
