import { useCallback, useEffect, useRef, useState } from "react";
import { AssetCard } from "../components/AssetCard";
import { AssetDrawer } from "../components/AssetDrawer";
import { api, searchStream } from "../lib/api";
import type { Collection, MediaType, ProviderStatus, ScoredAsset, Tier, UseCase } from "../lib/types";
import { MEDIA_TYPES, USE_CASES } from "../lib/types";

const TIER_OPTIONS: { id: Tier; label: string }[] = [
  { id: "green", label: "Green only" }, { id: "yellow", label: "+ Yellow" }, { id: "red", label: "Everything" },
];

function interleave(byProvider: Map<string, ScoredAsset[]>): ScoredAsset[] {
  const out: ScoredAsset[] = [];
  for (const tier of ["green", "yellow", "red"] as Tier[]) {
    const queues = [...byProvider.values()].map((list) => list.filter((s) => s.verdict.tier === tier));
    while (queues.some((q) => q.length)) for (const q of queues) { const next = q.shift(); if (next) out.push(next); }
  }
  return out;
}

export function SearchPage({ onToast }: { onToast: (m: string) => void }) {
  const [q, setQ] = useState("");
  const [media, setMedia] = useState<MediaType[]>(["image"]);
  const [useCase, setUseCase] = useState<UseCase>("demo");
  const [maxTier, setMaxTier] = useState<Tier>("yellow");
  const [byProvider, setByProvider] = useState<Map<string, ScoredAsset[]>>(new Map());
  const [statuses, setStatuses] = useState<ProviderStatus[]>([]);
  const [pending, setPending] = useState<string[]>([]);
  const [hidden, setHidden] = useState(0);
  const [searched, setSearched] = useState("");
  const [open, setOpen] = useState<ScoredAsset | null>(null);
  const [collections, setCollections] = useState<Collection[]>([]);
  const abortRef = useRef<AbortController | null>(null);

  const loadCollections = useCallback(() => { api.collections().then(setCollections).catch(() => undefined); }, []);
  useEffect(loadCollections, [loadCollections]);

  async function run(e?: React.FormEvent) {
    e?.preventDefault();
    const query = q.trim();
    if (!query) return;
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    const providers = await api.providers().catch(() => []);
    setPending(providers.filter((p) => p.enabled && p.media_types.some((m) => media.includes(m))).map((p) => p.id));
    setByProvider(new Map()); setStatuses([]); setHidden(0); setSearched(query);
    try {
      await searchStream({ q: query, media, use: useCase, maxTier, limit: 12 }, (batch) => {
        setByProvider((prev) => new Map(prev).set(batch.status.provider, batch.results));
        setStatuses((prev) => [...prev, batch.status]);
        setPending((prev) => prev.filter((p) => p !== batch.status.provider));
        setHidden((h) => h + batch.hidden);
      }, ctrl.signal);
    } catch (err) {
      if (!ctrl.signal.aborted) onToast(err instanceof Error ? err.message : "Search failed");
    } finally {
      if (!ctrl.signal.aborted) setPending([]);
    }
  }

  // Re-run when the use case or filters change after a search, since verdicts depend on them.
  useEffect(() => { if (searched) void run(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [useCase, maxTier, media]);

  const results = interleave(byProvider);
  const toggleMedia = (m: MediaType) =>
    setMedia((prev) => (prev.includes(m) ? (prev.length > 1 ? prev.filter((x) => x !== m) : prev) : [...prev, m]));

  return (
    <div className="page">
      <form className="searchbar" onSubmit={run}>
        <input className="input" autoFocus placeholder="Search ~20 open sources: “brutalist concrete”, “rain on tin roof”, “art deco poster”…"
               value={q} onChange={(e) => setQ(e.target.value)} />
        <button className="btn btn-primary" type="submit">Freestash</button>
      </form>

      <div className="controls">
        <div className="controls-row">
          <span className="label">Media</span>
          <div className="chips">
            {MEDIA_TYPES.map((m) => (
              <button key={m.id} type="button" className="chip" aria-pressed={media.includes(m.id)} onClick={() => toggleMedia(m.id)}>{m.label}</button>
            ))}
          </div>
        </div>
        <div className="controls-row">
          <span className="label">Use</span>
          <div className="segmented">
            {USE_CASES.map((u) => (
              <button key={u.id} type="button" aria-pressed={useCase === u.id} title={u.hint} onClick={() => setUseCase(u.id)}>{u.label}</button>
            ))}
          </div>
          <span className="use-hint">{USE_CASES.find((u) => u.id === useCase)?.hint}</span>
        </div>
        <div className="controls-row">
          <span className="label">Show</span>
          <div className="segmented">
            {TIER_OPTIONS.map((t) => (
              <button key={t.id} type="button" aria-pressed={maxTier === t.id} onClick={() => setMaxTier(t.id)}>{t.label}</button>
            ))}
          </div>
        </div>
      </div>

      {(statuses.length > 0 || pending.length > 0) && (
        <div className="sources">
          {statuses.map((s) => (
            <span key={s.provider} className={`src ${s.ok ? "" : "err"}`} title={s.error ?? `${s.elapsed_ms} ms`}>
              {s.provider} {s.ok ? <span className="n">{s.count}</span> : "✗"}
            </span>
          ))}
          {pending.map((p) => <span key={p} className="src wait">{p}</span>)}
          {hidden > 0 && <span className="src">{hidden} hidden by filter</span>}
        </div>
      )}

      {results.length > 0 ? (
        <div className="grid">{results.map((r) => <AssetCard key={r.uid} item={r} onOpen={setOpen} />)}</div>
      ) : searched && pending.length === 0 ? (
        <div className="empty"><strong>Nothing cleared the filter</strong>Try “+ Yellow”, another use case, or broader words.</div>
      ) : !searched ? (
        <div className="empty">
          <strong>Every result is scored for what you'll do with it</strong>
          The same photo can be green for a demo site and red inside a template download. Pick the use first.
        </div>
      ) : null}

      {open && (
        <AssetDrawer item={open} useCase={useCase} collections={collections} onClose={() => setOpen(null)}
                     onToast={onToast} onCollectionsChanged={loadCollections} />
      )}
    </div>
  );
}
