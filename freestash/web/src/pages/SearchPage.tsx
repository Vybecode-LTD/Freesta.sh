import { useCallback, useEffect, useRef, useState } from "react";
import { Aperture, SourceSpectrum } from "../components/Aperture";
import { AssetCard } from "../components/AssetCard";
import { AssetDrawer } from "../components/AssetDrawer";
import { Empty } from "../components/bits";
import { Icon } from "../components/Icon";
import { api, searchStream } from "../lib/api";
import { usePrefs } from "../lib/prefs";
import type { Collection, MediaType, ProviderStatus, ScoredAsset, Tier, UseCase } from "../lib/types";
import { MEDIA_TYPES, SHOW_OPTIONS, USE_CASES } from "../lib/types";

const EXAMPLES = ["lighthouse", "weathered concrete", "rain on a tin roof", "art deco poster", "botanical engraving"];

function interleave(byProvider: Map<string, ScoredAsset[]>): ScoredAsset[] {
  const out: ScoredAsset[] = [];
  for (const tier of ["green", "yellow", "red"] as Tier[]) {
    const queues = [...byProvider.values()].map((list) => list.filter((s) => s.verdict.tier === tier));
    while (queues.some((q) => q.length)) for (const q of queues) { const next = q.shift(); if (next) out.push(next); }
  }
  return out;
}

export function SearchPage({ onToast }: { onToast: (m: string) => void }) {
  const { prefs } = usePrefs();
  const [q, setQ] = useState("");
  const [media, setMedia] = useState<MediaType[]>(prefs.default_media);
  const [useCase, setUseCase] = useState<UseCase>(prefs.default_use_case);
  const [maxTier, setMaxTier] = useState<Tier>(prefs.default_max_tier);
  const [byProvider, setByProvider] = useState<Map<string, ScoredAsset[]>>(new Map());
  const [statuses, setStatuses] = useState<ProviderStatus[]>([]);
  const [pending, setPending] = useState<string[]>([]);
  const [total, setTotal] = useState(0);
  const [hidden, setHidden] = useState(0);
  const [searched, setSearched] = useState("");
  const [elapsed, setElapsed] = useState(0);
  const [open, setOpen] = useState<ScoredAsset | null>(null);
  const [collections, setCollections] = useState<Collection[]>([]);
  const abortRef = useRef<AbortController | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

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

  async function run(query = q) {
    query = query.trim();
    if (!query) return;
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    const providers = await api.providers().catch(() => []);
    const ids = providers.filter((p) => p.enabled && p.media_types.some((m) => media.includes(m))).map((p) => p.id);
    setPending(ids); setTotal(ids.length);
    setByProvider(new Map()); setStatuses([]); setHidden(0); setSearched(query); setElapsed(0);
    const started = performance.now();
    try {
      await searchStream({ q: query, media, use: useCase, maxTier, limit: prefs.results_per_source }, (batch) => {
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

  // Verdicts depend on the use and filters, so changing them after a search re-runs it.
  useEffect(() => { if (searched) void run(searched); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [useCase, maxTier, media]);

  const results = interleave(byProvider);
  const busy = pending.length > 0;
  const failed = statuses.filter((s) => !s.ok).length;
  const toggleMedia = (m: MediaType) =>
    setMedia((prev) => (prev.includes(m) ? (prev.length > 1 ? prev.filter((x) => x !== m) : prev) : [...prev, m]));
  const useLabel = USE_CASES.find((u) => u.id === useCase)!;
  const meta = searched
    ? `${statuses.length} of ${total} sources reported · ${results.length} results${elapsed ? ` · ${(elapsed / 1000).toFixed(1)} s` : ""}`
    : "Search 20 open collections at once · Ctrl K";

  return (
    <div className="page page-search">
      <form className="lens" onSubmit={(e) => { e.preventDefault(); void run(); }}>
        <Aperture total={total} reported={statuses.length} failed={failed} busy={busy} />
        <div className="lens-field">
          <input ref={inputRef} className="lens-input" autoFocus placeholder="What are you looking for?"
                 value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search" />
          <div className="lens-meta mono">{meta}</div>
        </div>
        <button className="btn btn-primary btn-lg" type="submit"><Icon name="search" size={17} />Search</button>
      </form>

      <SourceSpectrum statuses={statuses} pending={pending} />

      <div className="filters">
        <div className="filter-group" role="group" aria-label="Media">
          <span className="eyebrow">Media</span>
          {MEDIA_TYPES.map((m) => (
            <button key={m.id} type="button" className="pill" aria-pressed={media.includes(m.id)} onClick={() => toggleMedia(m.id)}>{m.label}</button>
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
        <div className="grid">{results.map((r) => <AssetCard key={r.uid} item={r} onOpen={setOpen} />)}</div>
      ) : searched && !busy ? (
        <Empty title="Nothing cleared the filter">Try “+ Check”, another use, or broader words.</Empty>
      ) : !searched ? (
        <div className="welcome">
          <h2>Every result is cleared for what you'll do with it.</h2>
          <p>The same photo can be clear for a demo site and blocked inside a template download. Pick the use, then search.</p>
          <div className="examples">
            {EXAMPLES.map((ex) => <button key={ex} type="button" className="pill" onClick={() => { setQ(ex); void run(ex); }}>{ex}</button>)}
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
