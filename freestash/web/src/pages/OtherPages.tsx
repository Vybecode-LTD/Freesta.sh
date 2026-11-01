import { useEffect, useRef, useState } from "react";
import { AssetCard } from "../components/AssetCard";
import { AssetDrawer } from "../components/AssetDrawer";
import { Empty, PageHead, Verdict, download } from "../components/bits";
import { Icon } from "../components/Icon";
import { api } from "../lib/api";
import { nextCursor } from "../lib/ledgerPages";
import { sidecarFromEntry, sidecarName } from "../lib/sidecar";
import type { Collection, LedgerEntry, MediaType, ProviderInfo, ScoredAsset, Trust, UseCase, Verdict as V } from "../lib/types";
import { MEDIA_TYPES, USE_CASES } from "../lib/types";

type Toast = { onToast: (m: string) => void };
const msg = (e: unknown) => (e instanceof Error ? e.message : String(e));

// ===================================================================== Collections
export function CollectionsPage({ onToast }: Toast) {
  const [list, setList] = useState<Collection[] | null>(null);
  const [active, setActive] = useState<Collection | null>(null);
  const [name, setName] = useState("");
  const [useCase, setUseCase] = useState<UseCase>("demo");
  const [open, setOpen] = useState<ScoredAsset | null>(null);

  const load = () => api.collections().then(setList).catch((e) => onToast(msg(e)));
  useEffect(() => { void load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function create(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    await api.createCollection(name.trim(), useCase);
    setName(""); void load();
  }

  async function openCollection(id: string) { setActive(await api.collection(id)); }

  function copyCredits(c: Collection) {
    const lines = (c.items ?? []).map((i) => `- ${i.verdict.attribution ?? i.asset.title}`);
    navigator.clipboard.writeText(`# Credits — ${c.name}\n\n${lines.join("\n")}\n`).then(() => onToast("Credits copied"));
  }

  if (active) {
    const items: ScoredAsset[] = (active.items ?? []).map((i) => ({ uid: i.uid, asset: i.asset, verdict: i.verdict as V }));
    return (
      <div className="page">
        <button className="btn btn-ghost btn-sm back" onClick={() => setActive(null)}><Icon name="back" size={15} />All collections</button>
        <PageHead title={active.name} sub={<>Cleared for <strong>{active.use_case}</strong> use · {active.item_count} item{active.item_count === 1 ? "" : "s"}</>}>
          <button className="btn" onClick={() => copyCredits(active)}><Icon name="copy" size={15} />Copy credits</button>
          <button className="btn btn-danger" onClick={async () => { if (confirm(`Delete “${active.name}”? Its items stay in your ledger.`)) { await api.deleteCollection(active.id); setActive(null); void load(); } }}>
            <Icon name="trash" size={15} />Delete</button>
        </PageHead>
        {items.length ? <div className="grid">{items.map((r) => <AssetCard key={r.uid} item={r} onOpen={setOpen} />)}</div>
          : <Empty title="Empty for now">Open a search result and choose “Add to a collection”.</Empty>}
        {open && <AssetDrawer item={open} useCase={active.use_case} collections={list ?? []} onClose={() => setOpen(null)}
                              onToast={onToast} onCollectionsChanged={() => openCollection(active.id)} />}
      </div>
    );
  }

  return (
    <div className="page">
      <PageHead title="Collections" sub="Boards for a project. Every item is cleared for the collection's use, and they sync to the desktop app." />
      <form className="panel inline-form" onSubmit={create}>
        <input className="input grow" placeholder="New collection, e.g. Aurora template — hero images"
               value={name} onChange={(e) => setName(e.target.value)} aria-label="Collection name" />
        <select className="input" value={useCase} onChange={(e) => setUseCase(e.target.value as UseCase)} aria-label="Use">
          {USE_CASES.map((u) => <option key={u.id} value={u.id}>{u.label}</option>)}
        </select>
        <button className="btn btn-primary" type="submit"><Icon name="plus" size={16} />Create</button>
      </form>
      <div className="coll-grid">
        {(list ?? []).map((c) => (
          <button key={c.id} className="panel coll" onClick={() => openCollection(c.id)}>
            <Icon name="collections" size={20} />
            <span className="coll-name">{c.name}</span>
            <span className="mono faint">{c.use_case} · {c.item_count} item{c.item_count === 1 ? "" : "s"}</span>
          </button>
        ))}
      </div>
      {list && !list.length && <Empty title="No collections yet">Create one above, then add search results to it.</Empty>}
    </div>
  );
}

// ===================================================================== Ledger pages
/** One ledger query, a page at a time. `more` is null once the last page is in. */
function useLedgerPages(project: string, files: boolean, onToast: (m: string) => void) {
  const [entries, setEntries] = useState<LedgerEntry[] | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const query = useRef(0); // a page that lands after the query changed is dropped

  useEffect(() => {
    const id = ++query.current;
    setEntries(null);
    setCursor(null);
    api.ledger({ project: project || undefined, files })
      .then((page) => { if (id === query.current) { setEntries(page); setCursor(nextCursor(page)); } })
      .catch((e) => onToast(msg(e)));
  }, [project, files, onToast]);

  async function more() {
    if (!cursor || busy) return;
    const id = query.current;
    setBusy(true);
    try {
      const page = await api.ledger({ project: project || undefined, files, before: cursor });
      if (id === query.current) { setEntries((e) => [...(e ?? []), ...page]); setCursor(nextCursor(page)); }
    } catch (e) { onToast(msg(e)); } finally { setBusy(false); }
  }

  return { entries, more: cursor ? more : null, busy };
}

function LoadMore({ more, busy }: { more: (() => void) | null; busy: boolean }) {
  if (!more) return null;
  return <div className="load-more"><button className="btn" onClick={more} disabled={busy}>{busy ? "Loading…" : "Load more"}</button></div>;
}

// ===================================================================== Downloads
/** The browser downloads files itself; this is every file taken on any of your devices, with its provenance. */
export function DownloadsPage({ onToast }: Toast) {
  const { entries, more, busy } = useLedgerPages("", true, onToast);
  const files = entries ?? [];

  return (
    <div className="page">
      <PageHead title="Downloads" sub="Every file you've taken, on the web or in the desktop app, newest first. Re-download it or save its license file." />
      <div className="dl-list">
        {files.map((e) => {
          const side = sidecarFromEntry(e);
          return (
            <div key={e.id} className="panel dl">
              <Verdict tier={e.tier} />
              <div className="dl-main">
                <div className="dl-title">{e.title}</div>
                <div className="mono faint">{e.provider} · {e.license_label} · {e.use_case}{e.project ? ` · ${e.project}` : ""} · {e.retrieved_at.slice(0, 10)}</div>
              </div>
              <a className="btn btn-sm" href={e.file_url!} target="_blank" rel="noreferrer"><Icon name="downloads" size={15} />File</a>
              <button className="btn btn-sm" disabled={!side} title={side ? "" : "Recorded before license files existed"}
                      onClick={() => side && download(sidecarName(e.file_url ?? null, e.title), side, "application/json")}>
                <Icon name="file" size={15} />.license.json</button>
            </div>
          );
        })}
      </div>
      <LoadMore more={more} busy={busy} />
      {entries && !files.length && <Empty title="Nothing downloaded yet">Open a search result and choose “Record and open file”.</Empty>}
    </div>
  );
}

// ===================================================================== Ledger
export function LedgerPage({ onToast }: Toast) {
  const [projects, setProjects] = useState<string[]>([]);
  const [project, setProject] = useState("");
  const { entries, more, busy } = useLedgerPages(project, false, onToast);

  useEffect(() => { api.projects().then(setProjects).catch(() => undefined); }, []);

  async function exportAs(fmt: "md" | "html" | "csv") {
    const body = await api.exportLedger(fmt, project || undefined);
    const name = { md: "ATTRIBUTION.md", html: "credits.html", csv: "freestash-ledger.csv" }[fmt];
    download(project ? `${project}-${name}` : name, body);
  }

  return (
    <div className="page">
      <PageHead title="License ledger" sub="Everything you've taken, with the license as it stood that day. Nothing here is ever edited.">
        <select className="input" value={project} onChange={(e) => setProject(e.target.value)} aria-label="Project">
          <option value="">All projects</option>
          {projects.map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
        <button className="btn" onClick={() => exportAs("md")}>ATTRIBUTION.md</button>
        <button className="btn" onClick={() => exportAs("html")}>Credits HTML</button>
        <button className="btn" onClick={() => exportAs("csv")}>CSV</button>
      </PageHead>
      <div className="panel table-wrap">
        <table className="table">
          <thead><tr><th>Clearance</th><th>Taken</th><th>Project</th><th>Title</th><th>License</th><th>Use</th><th>Source</th></tr></thead>
          <tbody>
            {(entries ?? []).map((e) => (
              <tr key={e.id}>
                <td><Verdict tier={e.tier} /></td>
                <td className="mono faint">{e.retrieved_at.slice(0, 10)}</td>
                <td>{e.project ?? "—"}</td>
                <td>{e.title}{e.creator && <div className="faint">{e.creator}</div>}</td>
                <td>{e.license_url ? <a href={e.license_url} target="_blank" rel="noreferrer">{e.license_label}</a> : e.license_label}</td>
                <td>{e.use_case}</td>
                <td>{e.landing_url ? <a href={e.landing_url} target="_blank" rel="noreferrer">{e.provider} ↗</a> : e.provider}</td>
              </tr>
            ))}
            {entries && !entries.length && <tr><td colSpan={7} className="faint table-empty">Nothing recorded yet.</td></tr>}
          </tbody>
        </table>
      </div>
      <LoadMore more={more} busy={busy} />
    </div>
  );
}

// ===================================================================== License check
export function LicenseCheckPage() {
  const [text, setText] = useState("");
  const [trust, setTrust] = useState<Trust>("unknown");
  const [media, setMedia] = useState<MediaType>("image");
  const [year, setYear] = useState("");
  const [result, setResult] = useState<Awaited<ReturnType<typeof api.checkLicense>> | null>(null);
  const [cutoff, setCutoff] = useState<{ works: number; sound_recordings: number } | null>(null);
  useEffect(() => { api.pdCutoff().then(setCutoff).catch(() => undefined); }, []);

  async function check(e: React.FormEvent) {
    e.preventDefault();
    if (text.trim()) setResult(await api.checkLicense(text.trim(), trust, media, year ? Number(year) : undefined));
  }

  return (
    <div className="page page-narrow">
      <PageHead title="License check" sub={<>Paste any license name, SPDX id or URL and see where it lands for each use.
        {cutoff && <> US public domain today: works from <strong>{cutoff.works}</strong> and earlier, recordings from <strong>{cutoff.sound_recordings}</strong> and earlier.</>}</>} />
      <form className="panel check-form" onSubmit={check}>
        <input className="input input-lg" placeholder="CC BY-SA 4.0 · https://unsplash.com/license · OFL-1.1 · Public domain"
               value={text} onChange={(e) => setText(e.target.value)} aria-label="License" />
        <div className="row wrap">
          <select className="input" value={trust} onChange={(e) => setTrust(e.target.value as Trust)} aria-label="Asserted by">
            {["unknown", "institution", "government", "curated", "community", "uploader"].map((t) => <option key={t} value={t}>Asserted by: {t}</option>)}
          </select>
          <select className="input" value={media} onChange={(e) => setMedia(e.target.value as MediaType)} aria-label="Media">
            {MEDIA_TYPES.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
          </select>
          <input className="input year" placeholder="Year (optional)" value={year} inputMode="numeric"
                 onChange={(e) => setYear(e.target.value.replace(/\D/g, ""))} aria-label="Year" />
          <button className="btn btn-primary" type="submit"><Icon name="shield" size={16} />Check</button>
        </div>
      </form>
      {result && (
        <>
          <p className="recognized">Recognized as <strong>{result.recognized_as.label}</strong> <span className="mono faint">({result.recognized_as.id})</span></p>
          <div className="matrix">
            {USE_CASES.map((u) => {
              const v = result.verdicts[u.id];
              return (
                <div key={u.id} className="matrix-row">
                  <span className="use">{u.label}</span><Verdict tier={v.tier} />
                  <ul>{v.reasons.map((r) => <li key={r}>{r}</li>)}{v.obligations.map((o) => <li key={o} className="ob">{o}</li>)}</ul>
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}

// ===================================================================== Sources
export function SourcesPage() {
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  useEffect(() => { api.providers().then(setProviders).catch(() => undefined); }, []);
  const on = providers.filter((p) => p.enabled).length;
  return (
    <div className="page">
      <PageHead title="Sources" sub={`${on} of ${providers.length} sources are on for you. Sources that need a key turn on when you add it in Settings.`} />
      <div className="source-grid">
        {providers.map((p) => (
          <div key={p.id} className={`panel source ${p.enabled ? "on" : "off"}`}>
            <div className="source-head">
              <span className={`dot ${p.enabled ? "on" : ""}`} aria-hidden="true" />
              <a href={p.homepage} target="_blank" rel="noreferrer" className="source-name">{p.name}</a>
              <span className="mono faint">{p.verified_live ? "verified" : "from docs"}</span>
            </div>
            <div className="mono faint">{p.media_types.join(" · ")}</div>
            {p.notes.length > 0 && <p className="source-notes">{p.notes.join(" ")}</p>}
            {!p.enabled && p.key_setting && <a className="link" href="#/settings?keys">Add a {p.name} key in Settings →</a>}
          </div>
        ))}
      </div>
    </div>
  );
}
