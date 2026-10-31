import { useEffect, useState } from "react";
import { AssetCard } from "../components/AssetCard";
import { AssetDrawer } from "../components/AssetDrawer";
import { TierBadge, download } from "../components/bits";
import { api } from "../lib/api";
import type { Collection, LedgerEntry, MediaType, ProviderInfo, ScoredAsset, Trust, UseCase, Verdict } from "../lib/types";
import { MEDIA_TYPES, USE_CASES } from "../lib/types";

type Toast = { onToast: (m: string) => void };

// ===================================================================== Collections
export function CollectionsPage({ onToast }: Toast) {
  const [list, setList] = useState<Collection[]>([]);
  const [active, setActive] = useState<Collection | null>(null);
  const [name, setName] = useState("");
  const [useCase, setUseCase] = useState<UseCase>("demo");
  const [open, setOpen] = useState<ScoredAsset | null>(null);

  const load = () => api.collections().then(setList).catch((e) => onToast(String(e.message ?? e)));
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
    const items: ScoredAsset[] = (active.items ?? []).map((i) => ({ uid: i.uid, asset: i.asset, verdict: i.verdict as Verdict }));
    return (
      <div className="page">
        <button className="btn btn-ghost btn-sm" onClick={() => setActive(null)}>← All collections</button>
        <h1 style={{ marginTop: 12 }}>{active.name}</h1>
        <p className="page-sub">Scored for <strong>{active.use_case}</strong> · {active.item_count} item(s)</p>
        <div className="row" style={{ marginBottom: 18 }}>
          <button className="btn" onClick={() => copyCredits(active)}>Copy credits</button>
          <button className="btn" onClick={async () => { if (confirm("Delete this collection?")) { await api.deleteCollection(active.id); setActive(null); void load(); } }}>Delete</button>
        </div>
        {items.length ? <div className="grid">{items.map((r) => <AssetCard key={r.uid} item={r} onOpen={setOpen} />)}</div>
          : <div className="empty"><strong>Empty for now</strong>Add results from the search drawer.</div>}
        {open && <AssetDrawer item={open} useCase={active.use_case} collections={list} onClose={() => setOpen(null)}
                              onToast={onToast} onCollectionsChanged={() => openCollection(active.id)} />}
      </div>
    );
  }

  return (
    <div className="page">
      <h1>Collections</h1>
      <p className="page-sub">Shared boards for a project. Every item is scored for the collection's use case.</p>
      <form className="row panel" style={{ marginBottom: 18 }} onSubmit={create}>
        <input className="input" style={{ flex: 1, minWidth: 220 }} placeholder="New collection, e.g. Aurora template — hero images"
               value={name} onChange={(e) => setName(e.target.value)} />
        <select className="input" style={{ width: 160 }} value={useCase} onChange={(e) => setUseCase(e.target.value as UseCase)}>
          {USE_CASES.map((u) => <option key={u.id} value={u.id}>{u.label}</option>)}
        </select>
        <button className="btn btn-primary" type="submit">Create</button>
      </form>
      <div className="list">
        {list.map((c) => (
          <div key={c.id} className="panel coll">
            <div><strong>{c.name}</strong><div className="faint">{c.use_case} · {c.item_count} item(s)</div></div>
            <button className="btn btn-sm" onClick={() => openCollection(c.id)}>Open</button>
          </div>
        ))}
        {!list.length && <div className="empty"><strong>No collections yet</strong>Create one above, then add search results to it.</div>}
      </div>
    </div>
  );
}

// ===================================================================== Ledger
export function LedgerPage({ onToast }: Toast) {
  const [entries, setEntries] = useState<LedgerEntry[]>([]);
  const [projects, setProjects] = useState<string[]>([]);
  const [project, setProject] = useState("");

  useEffect(() => { api.projects().then(setProjects).catch(() => undefined); }, []);
  useEffect(() => { api.ledger(project || undefined).then(setEntries).catch((e) => onToast(String(e.message ?? e))); }, [project, onToast]);

  async function exportAs(fmt: "md" | "html" | "csv") {
    const body = await api.exportLedger(fmt, project || undefined);
    const name = { md: "ATTRIBUTION.md", html: "credits.html", csv: "freestash-ledger.csv" }[fmt];
    download(project ? `${project}-${name}` : name, body);
  }

  return (
    <div className="page">
      <h1>License ledger</h1>
      <p className="page-sub">Every asset the team has taken, with the license as it stood that day. Append-only.</p>
      <div className="row" style={{ marginBottom: 16 }}>
        <select className="input" style={{ width: 240 }} value={project} onChange={(e) => setProject(e.target.value)}>
          <option value="">All projects</option>
          {projects.map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
        <span style={{ flex: 1 }} />
        <button className="btn" onClick={() => exportAs("md")}>ATTRIBUTION.md</button>
        <button className="btn" onClick={() => exportAs("html")}>Credits HTML</button>
        <button className="btn" onClick={() => exportAs("csv")}>CSV</button>
      </div>
      <div className="panel" style={{ padding: 0, overflowX: "auto" }}>
        <table className="table">
          <thead><tr><th /><th>Taken</th><th>Project</th><th>Title</th><th>License</th><th>Use</th><th>Source</th></tr></thead>
          <tbody>
            {entries.map((e) => (
              <tr key={e.id}>
                <td><TierBadge tier={e.tier} /></td>
                <td className="mono faint">{e.retrieved_at.slice(0, 10)}</td>
                <td>{e.project ?? "—"}</td>
                <td>{e.title}{e.creator && <div className="faint">{e.creator}</div>}</td>
                <td>{e.license_url ? <a href={e.license_url} target="_blank" rel="noreferrer">{e.license_label}</a> : e.license_label}</td>
                <td>{e.use_case}</td>
                <td>{e.landing_url ? <a href={e.landing_url} target="_blank" rel="noreferrer">{e.provider} ↗</a> : e.provider}</td>
              </tr>
            ))}
            {!entries.length && <tr><td colSpan={7} className="faint" style={{ padding: 30, textAlign: "center" }}>Nothing recorded yet.</td></tr>}
          </tbody>
        </table>
      </div>
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
    <div className="page" style={{ maxWidth: 980 }}>
      <h1>License check</h1>
      <p className="page-sub">Paste any license name, SPDX id, or URL and see where it lands for each use.
        {cutoff && <> US public domain today: works from <strong>{cutoff.works}</strong> and earlier, recordings from <strong>{cutoff.sound_recordings}</strong> and earlier.</>}</p>
      <form className="panel" style={{ display: "grid", gap: 12, marginBottom: 18 }} onSubmit={check}>
        <input className="input" placeholder="CC BY-SA 4.0 · https://unsplash.com/license · OFL-1.1 · Public domain"
               value={text} onChange={(e) => setText(e.target.value)} />
        <div className="row">
          <select className="input" style={{ width: 200 }} value={trust} onChange={(e) => setTrust(e.target.value as Trust)}>
            {["unknown", "institution", "government", "curated", "community", "uploader"].map((t) => <option key={t} value={t}>Asserted by: {t}</option>)}
          </select>
          <select className="input" style={{ width: 160 }} value={media} onChange={(e) => setMedia(e.target.value as MediaType)}>
            {MEDIA_TYPES.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
          </select>
          <input className="input" style={{ width: 150 }} placeholder="Year (optional)" value={year} onChange={(e) => setYear(e.target.value.replace(/\D/g, ""))} />
          <button className="btn btn-primary" type="submit">Check</button>
        </div>
      </form>
      {result && (
        <>
          <p>Recognized as <strong>{result.recognized_as.label}</strong> <span className="mono faint">({result.recognized_as.id})</span></p>
          <div className="matrix">
            {USE_CASES.map((u) => {
              const v = result.verdicts[u.id];
              return (
                <div key={u.id} className="matrix-row">
                  <span className="use">{u.label}</span><TierBadge tier={v.tier} />
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
  return (
    <div className="page">
      <h1>Sources</h1>
      <p className="page-sub">Keys are optional for most sources. Ones marked “docs” were built from documentation and get verified once a key is added.</p>
      <div className="panel" style={{ padding: 0, overflowX: "auto" }}>
        <table className="table">
          <thead><tr><th>Source</th><th>Media</th><th>Status</th><th>Verified</th><th>Notes</th></tr></thead>
          <tbody>
            {providers.map((p) => (
              <tr key={p.id}>
                <td><a href={p.homepage} target="_blank" rel="noreferrer"><strong>{p.name}</strong></a><div className="mono faint">{p.id}</div></td>
                <td>{p.media_types.join(", ")}</td>
                <td>{p.enabled ? <span className="tier tier-green">on</span> : (
                  <span>
                    <span className="tier tier-red">off</span>{" "}
                    {p.key_signup_url && <a href={p.key_signup_url} target="_blank" rel="noreferrer" className="faint">get {p.key_setting?.toUpperCase()} ↗</a>}
                  </span>)}</td>
                <td className="mono">{p.verified_live ? "live" : "docs"}</td>
                <td className="faint" style={{ maxWidth: 420 }}>{p.notes.join(" ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
