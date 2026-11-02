// Grouped results and query-word chips (contract dev plans/contracts/grouped-results.md). The desktop's
// Freestash.Client/ResultGroups.cs follows the same rules; keep the two in step.
import { CATEGORIES } from "./categories";
import type { MediaType, ParsedQuery, QueryPick, ScoredAsset, Tier } from "./types";

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

/** One section per category that has results, in the shared order, each keeping the incoming order. */
export function groupResults(ordered: ScoredAsset[], expanded: ReadonlySet<MediaType>): ResultSection[] {
  const byId = new Map<MediaType, ScoredAsset[]>();
  for (const s of ordered) byId.set(s.asset.media_type, [...(byId.get(s.asset.media_type) ?? []), s]);
  const known = CATEGORIES.filter((c) => byId.has(c.id));
  const unknown = [...byId.keys()].filter((id) => !CATEGORIES.some((c) => c.id === id)).map((id) => ({ id, label: id }));
  return [...known, ...unknown].map(({ id, label }) => {
    const all = byId.get(id)!;
    return { id, label, total: all.length, items: expanded.has(id) ? all : all.slice(0, SECTION_SIZE) };
  });
}

/** The query as last read: what was typed, what is searched, the words kept as words, the picks shown as chips,
 *  and the media the user had chosen before the picks replaced them. */
export interface Reading { original: string; q: string; keep: string[]; picks: QueryPick[]; before: MediaType[] }

/** Read a query again only when its text changed, so a removed pick stays removed when Search is pressed again. */
export const needsParse = (text: string, reading: Reading | null) => !reading || text.trim() !== reading.q;

/** A fresh read of a typed query. Picks replace the media; without picks the media stay as they are. */
export function readQuery(parsed: ParsedQuery, media: MediaType[], prev: Reading | null): { reading: Reading; media: MediaType[] } {
  const before = prev?.picks.length ? prev.before : media;
  return {
    reading: { original: parsed.original, q: parsed.q, keep: [], picks: parsed.picks, before },
    media: parsed.media_types.length ? parsed.media_types : media,
  };
}

/** The read after a chip was removed (`parsed` came back for `reading.original` with `keep`). With no picks left the
 *  media go back to the user's own selection. */
export function dropPick(parsed: ParsedQuery, reading: Reading, keep: string[]): { reading: Reading; media: MediaType[] } {
  return {
    reading: { ...reading, q: parsed.q, keep, picks: parsed.picks },
    media: parsed.media_types.length ? parsed.media_types : reading.before,
  };
}

/** Choosing media by hand takes over from the picks: the chips go, the text stays. */
export const withoutPicks = (reading: Reading | null): Reading | null => reading && { ...reading, picks: [] };
