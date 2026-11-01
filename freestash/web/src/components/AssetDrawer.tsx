import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { sidecarJson, sidecarName } from "../lib/sidecar";
import type { AssetDetail, Collection, ScoredAsset, UseCase } from "../lib/types";
import { USE_CASES } from "../lib/types";
import { MediaPreview, Verdict, download, formatBytes } from "./bits";
import { Icon } from "./Icon";

interface Props {
  item: ScoredAsset;
  useCase: UseCase;
  collections: Collection[];
  onClose: () => void;
  onToast: (msg: string) => void;
  onCollectionsChanged: () => void;
}

export function AssetDrawer({ item, useCase, collections, onClose, onToast, onCollectionsChanged }: Props) {
  const [detail, setDetail] = useState<AssetDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(item.asset.detail_required);
  const [project, setProject] = useState(() => localStorage.getItem("freestash.project") ?? "");
  const [collectionId, setCollectionId] = useState("");
  const [sidecar, setSidecar] = useState(() => localStorage.getItem("freestash.sidecar") !== "off");

  useEffect(() => {
    let alive = true;
    setLoadingDetail(true);
    api.asset(item.uid, useCase)
      .then((d) => alive && setDetail(d))
      .catch(() => undefined)
      .finally(() => alive && setLoadingDetail(false));
    return () => { alive = false; };
  }, [item.uid, useCase]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const asset = detail?.asset ?? item.asset;
  const verdict = detail?.verdict ?? item.verdict;
  const renditions = asset.renditions;
  const best = renditions[0];
  const blocked = verdict.tier === "red";

  async function take(fileUrl?: string) {
    const url = fileUrl ?? best?.url;
    try {
      localStorage.setItem("freestash.project", project);
      localStorage.setItem("freestash.sidecar", sidecar ? "on" : "off");
      const entry = await api.take({ uid: item.uid, asset, use_case: useCase, project: project || undefined, file_url: url });
      if (url) window.open(url, "_blank", "noopener");
      if (sidecar) download(sidecarName(url ?? null, asset.title), sidecarJson(asset, verdict, url ?? null, entry.retrieved_at), "application/json");
      onToast(`Recorded in your ledger${project ? ` under ${project}` : ""}`);
    } catch (e) {
      onToast(e instanceof Error ? e.message : "Couldn't record it");
    }
  }

  async function addToCollection() {
    if (!collectionId) return;
    await api.addToCollection(collectionId, { uid: item.uid, asset });
    onCollectionsChanged();
    onToast("Added to the collection");
  }

  function copy(text: string, what: string) {
    navigator.clipboard.writeText(text).then(() => onToast(`${what} copied`));
  }

  return (
    <>
      <div className="scrim" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-modal="true" aria-label={asset.title}>
        <div className="drawer-head">
          <Verdict tier={verdict.tier} size="lg" />
          <span className="mono faint drawer-uid">{item.uid}</span>
          <button className="icon-btn" onClick={onClose} aria-label="Close"><Icon name="close" /></button>
        </div>
        <div className="drawer-body">
          <div className={`hero m-${asset.media_type}`}><MediaPreview asset={asset} large /></div>

          <div>
            <h2 className="drawer-title">{asset.title}</h2>
            <div className="muted">{[asset.creator, asset.date].filter(Boolean).join(" · ") || "Unknown creator"}</div>
          </div>

          <dl className="kv">
            <dt>License</dt>
            <dd>{asset.license.url ? <a href={asset.license.url} target="_blank" rel="noreferrer">{asset.license.label}</a> : asset.license.label}</dd>
            <dt>Trust</dt><dd>{asset.trust}</dd>
            <dt>Source</dt>
            <dd>{asset.landing_url ? <a href={asset.landing_url} target="_blank" rel="noreferrer">{asset.source_name || asset.provider} ↗</a> : asset.provider}</dd>
            {asset.width && asset.height ? (<><dt>Size</dt><dd className="mono">{asset.width} × {asset.height}</dd></>) : null}
            {asset.license.raw ? (<><dt>As stated</dt><dd className="mono faint">{asset.license.raw}</dd></>) : null}
          </dl>

          <section>
            <h3 className="section-title">Clearance by use</h3>
            <div className="matrix">
              {USE_CASES.map((u) => {
                const v = detail?.verdicts[u.id] ?? (u.id === useCase ? verdict : null);
                if (!v) return null;
                return (
                  <div key={u.id} className={`matrix-row ${u.id === useCase ? "current" : ""}`}>
                    <span className="use">{u.label}</span>
                    <Verdict tier={v.tier} />
                    <ul>
                      {v.reasons.map((r) => <li key={r}>{r}</li>)}
                      {v.obligations.map((o) => <li key={o} className="ob">{o}</li>)}
                    </ul>
                  </div>
                );
              })}
            </div>
          </section>

          {verdict.attribution && (
            <section>
              <h3 className="section-title">Credit line</h3>
              <div className="attribution">{verdict.attribution}</div>
              <div className="row">
                <button className="btn btn-sm" onClick={() => copy(verdict.attribution!, "Credit line")}><Icon name="copy" size={15} />Copy text</button>
                {detail?.attribution_html && <button className="btn btn-sm" onClick={() => copy(detail.attribution_html, "HTML credit")}><Icon name="copy" size={15} />Copy HTML</button>}
              </div>
            </section>
          )}

          <section className="take">
            <h3 className="section-title">Take it</h3>
            <input className="input" placeholder="Project (groups credits), e.g. aurora-template"
                   value={project} onChange={(e) => setProject(e.target.value)} aria-label="Project" />
            <label className="check"><input type="checkbox" checked={sidecar} onChange={(e) => setSidecar(e.target.checked)} />
              Also save a <span className="mono">.license.json</span> next to the file</label>
            <button className="btn btn-primary btn-block" disabled={blocked || !best} onClick={() => take()}>
              {blocked ? "Blocked for this use" : <><Icon name="downloads" size={16} />Record and open file</>}
            </button>
            {collections.length > 0 && (
              <div className="row">
                <select className="input" value={collectionId} onChange={(e) => setCollectionId(e.target.value)} aria-label="Collection">
                  <option value="">Add to a collection…</option>
                  {collections.map((c) => <option key={c.id} value={c.id}>{c.name} ({c.use_case})</option>)}
                </select>
                <button className="btn" disabled={!collectionId} onClick={addToCollection}><Icon name="plus" size={15} />Add</button>
              </div>
            )}
          </section>

          <section>
            <h3 className="section-title">Files {loadingDetail && <span className="faint">· loading…</span>}</h3>
            {renditions.length ? (
              <div className="renditions">
                {renditions.map((r) => (
                  <a key={r.url + r.label} href={r.url} target="_blank" rel="noreferrer"
                     onClick={(e) => { if (!blocked) { e.preventDefault(); void take(r.url); } }}>
                    <span>{r.label}</span>
                    <span className="size">{r.width && r.height ? `${r.width}×${r.height}` : formatBytes(r.bytes)}</span>
                  </a>
                ))}
              </div>
            ) : <div className="faint">{loadingDetail ? "Fetching files…" : "No direct files; use the source page."}</div>}
            {asset.tips.map((t) => <p key={t} className="tip">{t}</p>)}
          </section>

          {asset.description && <section><h3 className="section-title">Description</h3><p className="muted">{asset.description}</p></section>}
        </div>
      </aside>
    </>
  );
}
