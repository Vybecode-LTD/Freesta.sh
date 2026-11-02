// Grouped results and query-word chips (contract dev plans/contracts/grouped-results.md). The desktop's
// Freestash.Client/ResultGroups.cs follows the same rules; keep the two in step.
import { CATEGORIES } from "./categories";
import type { Asset, MediaType, ParsedQuery, QueryPick, ScoredAsset, Tier } from "./types";

/** Cards per section until "Show all (n)". */
export const SECTION_SIZE = 8;

export interface ResultSection { id: MediaType; label: string; total: number; items: ScoredAsset[] }

/** Round-robin across sources (so one chatty source can't bury the rest), clear results first. */
export function interleave(byProvider: Map<string, ScoredAsset[]>): ScoredAsset[] {
  const out: ScoredAsset[] = [];
  for (const tier of ["green", "yellow", "red"] as Tier[]) {
    const queues = [...byProvider.values()].map((list) => list.filter((s) => s.verdict.tier === tier));
    while (queues.some((q) => q.length)) for (const q of queues) { const next = q.shift(); if (next) out.push(next); }
  }
  return out;
}

/** Sections only with more than one medium selected; one medium looks as it always has (one grid). */
export const isGrouped = (media: readonly MediaType[]) => media.length > 1;

/** Packs first, then single files, each keeping its order (contract packs-and-new-kinds). */
export const leadPacks = (ordered: ScoredAsset[]): ScoredAsset[] =>
  [...ordered.filter((s) => s.asset.is_pack), ...ordered.filter((s) => !s.asset.is_pack)];

/** One section per category that has results, in the shared order, packs leading each. */
export function groupResults(ordered: ScoredAsset[], expanded: ReadonlySet<MediaType>): ResultSection[] {
  const byId = new Map<MediaType, ScoredAsset[]>();
  for (const s of leadPacks(ordered)) byId.set(s.asset.media_type, [...(byId.get(s.asset.media_type) ?? []), s]);
  const known = CATEGORIES.filter((c) => byId.has(c.id));
  const unknown = [...byId.keys()].filter((id) => !CATEGORIES.some((c) => c.id === id)).map((id) => ({ id, label: id }));
  return [...known, ...unknown].map(({ id, label }) => {
    const all = byId.get(id)!;
    return { id, label, total: all.length, items: expanded.has(id) ? all : all.slice(0, SECTION_SIZE) };
  });
}

/** The query as last read: what was typed, what is searched, the words kept as words, the picks shown as chips,
 *  and the media and Packs setting the user had chosen before the picks replaced them. */
export interface Reading { original: string; q: string; keep: string[]; picks: QueryPick[]; before: MediaType[]; packsBefore: boolean }

/** What a read decides: the reading itself, the media to search and whether to look for packs. */
export interface Read { reading: Reading; media: MediaType[]; packs: boolean }

/** Read a query again only when its text changed, so a removed pick stays removed when Search is pressed again. */
export const needsParse = (text: string, reading: Reading | null) => !reading || text.trim() !== reading.q;

/** A fresh read of a typed query. Picks replace the media and a pack word turns packs on; without them the media
 *  and packs stay as they are. */
export function readQuery(parsed: ParsedQuery, media: MediaType[], prev: Reading | null, packs = false): Read {
  const picked = !!prev?.picks.length;
  const before = picked ? prev!.before : media;
  const packsBefore = picked ? prev!.packsBefore : packs;
  return {
    reading: { original: parsed.original, q: parsed.q, keep: [], picks: parsed.picks, before, packsBefore },
    media: parsed.media_types.length ? parsed.media_types : media,
    packs: parsed.packs || packs,
  };
}

/** The read after a chip was removed (`parsed` came back for `reading.original` with `keep`). With no media picks
 *  left the media go back to the user's own selection; with no pack word left, so does packs. */
export function dropPick(parsed: ParsedQuery, reading: Reading, keep: string[]): Read {
  return {
    reading: { ...reading, q: parsed.q, keep, picks: parsed.picks },
    media: parsed.media_types.length ? parsed.media_types : reading.before,
    packs: parsed.packs || reading.packsBefore,
  };
}

// ---- how a pack reads, the same words as the desktop's PackText (contract packs-and-new-kinds)

/** "1 file", "4,133 files". */
export const fileCount = (n: number) => `${n.toLocaleString("en-US")} file${n === 1 ? "" : "s"}`;

/** The card's badge: "Pack · 24 files", or "Pack" when the source doesn't count them. */
export const packBadge = (a: Asset) => (a.item_count != null ? `Pack · ${fileCount(a.item_count)}` : "Pack");

/** "WAV · MP3". */
export const formatList = (a: Asset) => a.formats.map((f) => f.toUpperCase()).join(" · ");

/** The licenses of a pack's files, and how far they were read: "CC0 1.0, CC BY 4.0 · read for 1 of 24 files".
 *  Null when one license covers the whole pack. */
export function licensesInside(a: Asset): string | null {
  if (a.members_checked == null) return null;
  const labels = a.member_licenses.map((l) => l.label).join(", ") || "None read yet";
  const checked = a.members_checked;
  if (a.item_count == null) return `${labels} · read for ${fileCount(checked)}`;
  return checked < a.item_count ? `${labels} · read for ${checked} of ${fileCount(a.item_count)}` : labels;
}

/** Choosing media by hand takes over from the picks: the chips go, the text stays. */
export const withoutPicks = (reading: Reading | null): Reading | null => reading && { ...reading, picks: [] };
