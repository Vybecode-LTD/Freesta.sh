import { useCallback, useEffect, useRef, useState } from "react";
import { Aperture, SourceSpectrum } from "../components/Aperture";
import { AssetDrawer } from "../components/AssetDrawer";
import { Empty } from "../components/bits";
import { Icon } from "../components/Icon";
import { QueryChips } from "../components/QueryChips";
import { ResultSections } from "../components/ResultSections";
import { api, searchStream } from "../lib/api";
import { PRESETS } from "../lib/categories";
import { usePrefs } from "../lib/prefs";
import { dropPick, interleave, needsParse, readQuery, type Reading, withoutPicks } from "../lib/results";
import type { Collection, MediaType, ProviderStatus, QueryPick, ScoredAsset, Tier, UseCase } from "../lib/types";
import { MEDIA_TYPES, SHOW_OPTIONS, USE_CASES } from "../lib/types";

// The same list as the desktop's Suggestions; the last three show query words picking the media.
const EXAMPLES = ["lighthouse", "art deco poster", "botanical engraving", "weathered concrete texture", "rain on a tin roof sfx", "monospace font"];

const runKey = (q: string, media: MediaType[], use: UseCase, tier: Tier, packs: boolean) => JSON.stringify([q, media, use, tier, packs]);

/** The Packs switch, the same words as the desktop (contract packs-and-new-kinds). */
const PACKS_OPTIONS = [
  { on: false, label: "Off", hint: "Single files only" },
  { on: true, label: "On", hint: "Also look for packs: icon sets, sound packs, archives" },
];
type Preset = (typeof PRESETS)[number];

export function SearchPage({ onToast }: { onToast: (m: string) => void }) {
  const { prefs } = usePrefs();
  const [q, setQ] = useState("");
  const [media, setMedia] = useState<MediaType[]>(prefs.default_media);
  const [useCase, setUseCase] = useState<UseCase>(prefs.default_use_case);
  const [maxTier, setMaxTier] = useState<Tier>(prefs.default_max_tier);
  const [packs, setPacks] = useState(false); // per search, not a synced default
  const [byProvider, setByProvider] = useState<Map<string, ScoredAsset[]>>(new Map());
  const [statuses, setStatuses] = useState<ProviderStatus[]>([]);
  const [pending, setPending] = useState<string[]>([]);
  const [total, setTotal] = useState(0);
  const [hidden, setHidden] = useState(0);
  const [searched, setSearched] = useState("");
  const [elapsed, setElapsed] = useState(0);
  const [open, setOpen] = useState<ScoredAsset | null>(null);
  const [collections, setCollections] = useState<Collection[]>([]);
  const [reading, setReading] = useState<Reading | null>(null);
  const [runId, setRunId] = useState(0);
  const abortRef = useRef<AbortController | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const current = useRef(""); // the query of the search last started
  const lastRun = useRef(""); // its runKey
  const intentRef = useRef(0); // bumped per submit or chip removal: only the latest one's read is applied

  // the account's defaults arrive after first paint when signing in on a new device
  useEffect(() => { setMedia(prefs.default_media); setUseCase(prefs.default_use_case); setMaxTier(prefs.default_max_tier); },
    [prefs.default_media, prefs.default_use_case, prefs.default_max_tier]);

  const loadCollections = useCallback(() => { api.collections().then(setCollections).catch(() => undefined); }, []);
  useEffect(loadCollections, [loadCollections]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); inputRef.current?.focus(); inputRef.current?.select(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  /** Run one search exactly as given. The refs are set before the first await, so the filter effect below sees
   *  this search as current and doesn't start it a second time when a pick has just changed the media. */
  async function search(query: string, m: MediaType[], withPacks: boolean) {
    query = query.trim();
    if (!query) return;
    current.current = query;
    lastRun.current = runKey(query, m, useCase, maxTier, withPacks);
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    const providers = await api.providers().catch(() => []);
    if (ctrl.signal.aborted) return;
    const ids = providers.filter((p) => p.enabled && p.media_types.some((x) => m.includes(x))).map((p) => p.id);
    setPending(ids); setTotal(ids.length);
    setByProvider(new Map()); setStatuses([]); setHidden(0); setSearched(query); setElapsed(0); setRunId((n) => n + 1);
    const started = performance.now();
    try {
      await searchStream({ q: query, media: m, use: useCase, maxTier, limit: prefs.results_per_source, packs: withPacks }, (batch) => {
        setByProvider((prev) => new Map(prev).set(batch.status.provider, batch.results));
        setStatuses((prev) => [...prev, batch.status]);
        setPending((prev) => prev.filter((p) => p !== batch.status.provider));
        setHidden((h) => h + batch.hidden);
        setElapsed(performance.now() - started);
      }, ctrl.signal);
    } catch (err) {
      if (!ctrl.signal.aborted) onToast(err instanceof Error ? err.message : "Search failed");
    } finally {
      if (!ctrl.signal.aborted) { setPending([]); setElapsed(performance.now() - started); }
    }
  }

  /** Search what's typed. Category words in it ("sfx", "font") pick the media and show as chips; the same text
   *  isn't read twice, so Search after removing a chip keeps the word as a word. */
  async function submit(text = q) {
    text = text.trim();
    if (!text) return;
    const intent = ++intentRef.current;
    if (!needsParse(text, reading)) return search(text, media, packs);
    const parsed = await api.parseQuery(text).catch(() => null);
    if (intent !== intentRef.current) return; // a newer search or chip removal started meanwhile
    if (!parsed) return search(text, media, packs); // couldn't be read: every word is searched, as before
    const next = readQuery(parsed, media, reading, packs);
    setReading(next.reading); setMedia(next.media); setPacks(next.packs); setQ(next.reading.q);
    return search(next.reading.q, next.media, next.packs);
  }

  async function removePick(pick: QueryPick) {
    if (!reading) return;
    const intent = ++intentRef.current;
    const keep = [...reading.keep, pick.word];
    const parsed = await api.parseQuery(reading.original, keep).catch((err: unknown) => {
      onToast(err instanceof Error ? err.message : "Couldn't read the query");
      return null;
    });
    if (!parsed || intent !== intentRef.current) return;
    const next = dropPick(parsed, reading, keep);
    setReading(next.reading); setMedia(next.media); setPacks(next.packs); setQ(next.reading.q);
    return search(next.reading.q, next.media, next.packs);
  }

  // Verdicts depend on the use and filters, so changing them after a search re-runs it (unless that search is running).
  useEffect(() => {
    if (current.current && runKey(current.current, media, useCase, maxTier, packs) !== lastRun.current) void search(current.current, media, packs);
    /* eslint-disable-next-line react-hooks/exhaustive-deps */
  }, [useCase, maxTier, media, packs]);

  const results = interleave(byProvider);
  const busy = pending.length > 0;
  const failed = statuses.filter((s) => !s.ok).length;
  // The source list can fail to load while batches still arrive; never show "5 of 0" (the desktop does the same).
  const shown = Math.max(total, statuses.length);
  const toggleMedia = (m: MediaType) => {
    setReading(withoutPicks); // choosing media by hand takes over from the chips
    setMedia((prev) => (prev.includes(m) ? (prev.length > 1 ? prev.filter((x) => x !== m) : prev) : [...prev, m]));
  };
  const choosePacks = (on: boolean) => { setReading(withoutPicks); setPacks(on); };
  const isPreset = (p: Preset) => packs === p.packs && media.length === p.media.length && p.media.every((m) => media.includes(m));
  const applyPreset = (p: Preset) => { setReading(withoutPicks); setMedia([...p.media]); setPacks(p.packs); };
  const useLabel = USE_CASES.find((u) => u.id === useCase)!;
  const meta = searched
    ? `${statuses.length} of ${shown} sources reported · ${results.length} results${elapsed ? ` · ${(elapsed / 1000).toFixed(1)} s` : ""}`
    : "Search 20 open collections at once · Ctrl K";

  return (
    <div className="page page-search">
      <form className="lens" onSubmit={(e) => { e.preventDefault(); void submit(); }}>
        <Aperture total={shown} reported={statuses.length} failed={failed} busy={busy} />
        <div className="lens-field">
          <input ref={inputRef} className="lens-input" autoFocus placeholder="What are you looking for?"
                 value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search" />
          <div className="lens-meta mono">{meta}</div>
        </div>
        <button className="btn btn-primary btn-lg" type="submit"><Icon name="search" size={17} />Search</button>
      </form>

      <QueryChips picks={reading?.picks ?? []} onRemove={(p) => void removePick(p)} />

      <SourceSpectrum statuses={statuses} pending={pending} />

      <div className="filters">
        <div className="filter-group" role="group" aria-label="Media">
          <span className="eyebrow">Media</span>
          {MEDIA_TYPES.map((m) => (
            <button key={m.id} type="button" className="pill" aria-pressed={media.includes(m.id)} onClick={() => toggleMedia(m.id)}>{m.label}</button>
          ))}
          {PRESETS.map((p) => (
            <button key={p.id} type="button" className="pill" aria-pressed={isPreset(p)} title={p.hint} onClick={() => applyPreset(p)}>{p.label}</button>
          ))}
        </div>
        <div className="filter-group" role="group" aria-label="Packs">
          <span className="eyebrow">Packs</span>
          {PACKS_OPTIONS.map((o) => (
            <button key={o.label} type="button" className="pill" aria-pressed={packs === o.on} title={o.hint} onClick={() => choosePacks(o.on)}>{o.label}</button>
          ))}
        </div>
        <div className="filter-group" role="group" aria-label="Use">
          <span className="eyebrow">Use</span>
          {USE_CASES.map((u) => (
            <button key={u.id} type="button" className="pill" aria-pressed={useCase === u.id} title={u.hint} onClick={() => setUseCase(u.id)}>{u.label}</button>
          ))}
        </div>
        <div className="filter-group" role="group" aria-label="Show">
          <span className="eyebrow">Show</span>
          {SHOW_OPTIONS.map((t) => (
            <button key={t.id} type="button" className="pill" aria-pressed={maxTier === t.id} title={t.hint} onClick={() => setMaxTier(t.id)}>{t.label}</button>
          ))}
        </div>
      </div>

      {searched && (
        <div className="results-head">
          <h2>{maxTier === "green" ? "Clear" : maxTier === "yellow" ? "Clear or worth checking" : "Everything"} for {useLabel.label.toLowerCase()} use</h2>
          <span className="mono faint">{useLabel.hint}</span>
          {hidden > 0 && <span className="mono faint">· {hidden} hidden by this filter</span>}
        </div>
      )}

      {results.length > 0 ? (
        <ResultSections results={results} media={media} searchKey={String(runId)} onOpen={setOpen} />
      ) : searched && !busy ? (
        <Empty title="Nothing cleared the filter">Try “+ Check”, another use, or broader words.</Empty>
      ) : !searched ? (
        <div className="welcome">
          <h2>Every result is cleared for what you'll do with it.</h2>
          <p>The same photo can be clear for a demo site and blocked inside a template download. Pick the use, then search.</p>
          <div className="examples">
            {EXAMPLES.map((ex) => <button key={ex} type="button" className="pill" onClick={() => { setQ(ex); void submit(ex); }}>{ex}</button>)}
          </div>
        </div>
      ) : (
        <div className="grid">{Array.from({ length: 8 }, (_, i) => <div key={i} className="card skeleton" />)}</div>
      )}

      {open && (
        <AssetDrawer item={open} useCase={useCase} collections={collections} onClose={() => setOpen(null)}
                     onToast={onToast} onCollectionsChanged={loadCollections} />
      )}
    </div>
  );
}
