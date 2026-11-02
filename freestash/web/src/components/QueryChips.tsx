import { CATEGORIES } from "../lib/categories";
import type { QueryPick } from "../lib/types";
import { Icon } from "./Icon";

const label = (pick: QueryPick) =>
  pick.media_type ? (CATEGORIES.find((c) => c.id === pick.media_type)?.label ?? pick.media_type) : "Packs";

/** The query words read as categories ("sfx" → Audio) or as packs ("pack" → Packs). Removing one searches it as a
 *  word again (desktop: the "Read as" row in SearchView.axaml; same words). */
export function QueryChips({ picks, onRemove }: { picks: QueryPick[]; onRemove: (pick: QueryPick) => void }) {
  if (!picks.length) return null;
  return (
    <div className="read-as" role="group" aria-label="Read as">
      <span className="eyebrow">Read as</span>
      {picks.map((p) => {
        const why = `Search “${p.word}” as a word, not as ${label(p)}`;
        return (
          <button key={`${p.word}:${p.media_type ?? "packs"}`} type="button" className="chip" onClick={() => onRemove(p)} title={why} aria-label={why}>
            <span>“{p.word}” → {label(p)}</span>
            <Icon name="close" size={13} />
          </button>
        );
      })}
    </div>
  );
}
