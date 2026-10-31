import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { AssetDetail, Collection, ScoredAsset, UseCase } from "../lib/types";
import { USE_CASES } from "../lib/types";
import { MediaPreview, TierBadge, formatBytes } from "./bits";

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

  async function take(fileUrl?: string) {
    try {
      localStorage.setItem("freestash.project", project);
      await api.take({ uid: item.uid, asset, use_case: useCase, project: project || undefined, file_url: fileUrl ?? best?.url });
      onToast(`Recorded in the ledger${project ? ` under ${project}` : ""}`);
      if (fileUrl ?? best?.url) window.open(fileUrl ?? best?.url, "_blank", "noopener");
    } catch (e) {
      onToast(e instanceof Error ? e.message : "Couldn't record it");
    }
  }

  async function addToCollection() {
    if (!collectionId) return;
    await api.addToCollection(collectionId, { uid: item.uid, asset });
    onCollectionsChanged();
    onToast("Added to collection");
  }

  function copy(text: string, what: string) {
    navigator.clipboard.writeText(text).then(() => onToast(`${what} copied`));
  }

  return (
    <>
      <div className="scrim" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-label={asset.title}>
        <div className="drawer-head">
          <div className="row"><TierBadge tier={verdict.tier} /><span className="faint mono">{item.uid}</span></div>
          <button className="btn btn-ghost btn-sm" onClick={onClose}>Close ✕</button>
        </div>
        <div className="drawer-body">
          <div className={`hero ${asset.media_type === "icon" ? "icon" : ""}`}><MediaPreview asset={asset} large /></div>

          <div>
            <h2 style={{ margin: "0 0 4px", fontSize: 20, letterSpacing: "-0.02em" }}>{asset.title}</h2>
            <div className="muted">{[asset.creator, asset.date].filter(Boolean).join(" · ") || "Unknown creator"}</div>
          </div>

          <dl className="kv">
            <dt>License</dt>
            <dd>{asset.license.url ? <a href={asset.license.url} target="_blank" rel="noreferrer">{asset.license.label}</a> : asset.license.label}</dd>
            <dt>Trust</dt><dd>{asset.trust}</dd>
            <dt>Source</dt>
            <dd>{asset.landing_url ? <a href={asset.landing_url} target="_blank" rel="noreferrer">{asset.source_name || asset.provider} ↗</a> : asset.provider}</dd>
            {asset.width && asset.height ? (<><dt>Size</dt><dd>{asset.width} × {asset.height}</dd></>) : null}
            {asset.license.raw ? (<><dt>As stated</dt><dd className="mono faint">{asset.license.raw}</dd></>) : null}
          </dl>

          <section>
            <h3 className="section-title">Verdict by use case</h3>
            <div className="matrix">
              {USE_CASES.map((u) => {
                const v = detail?.verdicts[u.id] ?? (u.id === useCase ? verdict : null);
                if (!v) return null;
                return (
                  <div key={u.id} className={`matrix-row ${u.id === useCase ? "current" : ""}`}>
                    <span className="use">{u.label}</span>
                    <TierBadge tier={v.tier} />
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
              <h3 className="section-title">Attribution</h3>
              <div className="attribution">{verdict.attribution}</div>
              <div className="row" style={{ marginTop: 8 }}>
                <button className="btn btn-sm" onClick={() => copy(verdict.attribution!, "Credit line")}>Copy text</button>
                {detail?.attribution_html && <button className="btn btn-sm" onClick={() => copy(detail.attribution_html, "HTML credit")}>Copy HTML</button>}
              </div>
            </section>
          )}

          <section className="take">
            <h3 className="section-title" style={{ margin: 0 }}>Take it</h3>
            <div className="row">
              <input className="input" style={{ flex: 1 }} placeholder="Project (groups credits), e.g. aurora-template"
                     value={project} onChange={(e) => setProject(e.target.value)} />
              <button className="btn btn-primary" disabled={verdict.tier === "red" || !best} onClick={() => take()}>
                {verdict.tier === "red" ? "Red for this use" : "Record + open file"}
              </button>
            </div>
            {collections.length > 0 && (
              <div className="row">
                <select className="input" style={{ flex: 1 }} value={collectionId} onChange={(e) => setCollectionId(e.target.value)}>
                  <option value="">Add to collection…</option>
                  {collections.map((c) => <option key={c.id} value={c.id}>{c.name} ({c.use_case})</option>)}
                </select>
                <button className="btn" disabled={!collectionId} onClick={addToCollection}>Add</button>
              </div>
            )}
          </section>

          <section>
            <h3 className="section-title">Files {loadingDetail && <span className="faint">· loading…</span>}</h3>
            {renditions.length ? (
              <div className="renditions">
                {renditions.map((r) => (
                  <a key={r.url + r.label} href={r.url} target="_blank" rel="noreferrer"
                     onClick={(e) => { if (verdict.tier !== "red") { e.preventDefault(); take(r.url); } }}>
                    <span>{r.label}</span>
                    <span className="size">{r.width && r.height ? `${r.width}×${r.height}` : formatBytes(r.bytes)}</span>
                  </a>
                ))}
              </div>
            ) : <div className="faint">{loadingDetail ? "Fetching files…" : "No direct files; use the source page."}</div>}
            {asset.tips.map((t) => <p key={t} className="faint" style={{ fontSize: 12.5 }}>💡 {t}</p>)}
          </section>

          {asset.description && <section><h3 className="section-title">Description</h3><p className="muted" style={{ margin: 0 }}>{asset.description}</p></section>}
        </div>
      </aside>
    </>
  );
}
