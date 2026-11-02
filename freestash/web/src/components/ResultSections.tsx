import { useEffect, useState } from "react";
import { groupResults, isGrouped, leadPacks, SECTION_SIZE } from "../lib/results";
import type { MediaType, ScoredAsset } from "../lib/types";
import { AssetCard } from "./AssetCard";

/** Results in one grid for one medium, or one section per category with a jump bar for several, packs first in each
 *  (desktop: the sections in SearchView.axaml; same words). `searchKey` changes per search: it closes every section. */
export function ResultSections({ results, media, searchKey, onOpen }: {
  results: ScoredAsset[]; media: MediaType[]; searchKey: string; onOpen: (item: ScoredAsset) => void;
}) {
  const [expanded, setExpanded] = useState<ReadonlySet<MediaType>>(new Set());
  useEffect(() => setExpanded(new Set()), [searchKey]);

  if (!isGrouped(media)) return <div className="grid">{leadPacks(results).map((r) => <AssetCard key={r.uid} item={r} onOpen={onOpen} />)}</div>;

  const sections = groupResults(results, expanded);
  const toggle = (id: MediaType) => setExpanded((prev) => {
    const next = new Set(prev);
    if (!next.delete(id)) next.add(id);
    return next;
  });
  const jump = (id: MediaType) => document.getElementById(`results-${id}`)?.scrollIntoView({ behavior: "smooth", block: "start" });

  return (
    <>
      <nav className="jumpbar" aria-label="Jump to a section">
        {sections.map((s) => (
          <button key={s.id} type="button" className="jump" onClick={() => jump(s.id)}>
            {s.label} <span className="mono">{s.total}</span>
          </button>
        ))}
      </nav>
      {sections.map((s) => (
        <section key={s.id} id={`results-${s.id}`} className="result-section" aria-labelledby={`results-${s.id}-h`}>
          <div className="section-head">
            <h3 id={`results-${s.id}-h`}>{s.label}</h3>
            <span className="mono muted">{s.total}</span>
          </div>
          <div className="grid">{s.items.map((r) => <AssetCard key={r.uid} item={r} onOpen={onOpen} />)}</div>
          {s.total > SECTION_SIZE && (
            <button type="button" className="link section-more" aria-expanded={expanded.has(s.id)} onClick={() => toggle(s.id)}>
              {expanded.has(s.id) ? "Show fewer" : `Show all (${s.total})`}
            </button>
          )}
        </section>
      ))}
    </>
  );
}
