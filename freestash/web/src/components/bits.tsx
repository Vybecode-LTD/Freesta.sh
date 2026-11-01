import { useEffect, useState } from "react";
import type { Asset, Tier } from "../lib/types";
import { TIER_WORD } from "../lib/types";

/** Verdict as a glowing dot plus its word (Clear / Check / Blocked). */
export function Verdict({ tier, size = "sm" }: { tier: Tier; size?: "sm" | "lg" }) {
  return <span className={`verdict v-${tier} ${size}`}><b aria-hidden="true" />{TIER_WORD[tier]}</span>;
}

/** Load a webfont from a URL once per family so font results render in their own face. */
const loaded = new Set<string>();
export function useFontFace(asset: Asset): string | undefined {
  const family = asset.media_type === "font" ? `freestash-${asset.source_id}` : undefined;
  const [ready, setReady] = useState(family ? loaded.has(family) : false);
  useEffect(() => {
    if (!family || !asset.preview_url || loaded.has(family)) return;
    const face = new FontFace(family, `url(${asset.preview_url})`);
    face.load().then((f) => { document.fonts.add(f); loaded.add(family); setReady(true); }).catch(() => undefined);
  }, [family, asset.preview_url]);
  return family && ready ? family : undefined;
}

export function MediaPreview({ asset, large = false }: { asset: Asset; large?: boolean }) {
  const family = useFontFace(asset);
  const src = (large ? asset.preview_url : asset.thumbnail_url) || asset.thumbnail_url || asset.preview_url;
  if (asset.media_type === "font") {
    return <div className="font-sample" style={{ fontFamily: family ?? "var(--sans)" }}>{large ? "The quick brown fox jumps over the lazy dog" : "Aa Gg 123"}</div>;
  }
  if (asset.media_type === "audio") {
    const audioSrc = asset.preview_url || asset.renditions[0]?.url;
    return audioSrc ? <audio controls preload="none" src={audioSrc} onClick={(e) => e.stopPropagation()} /> : <span className="placeholder">audio</span>;
  }
  if (src) return <FallbackImg src={src} alt={asset.title} label={asset.media_type} />;
  return <span className="placeholder">{asset.media_type}</span>;
}

/** Some hosts block hotlinked previews (bot shields, CORP headers). Show a clean placeholder instead of a broken image. */
function FallbackImg({ src, alt, label }: { src: string; alt: string; label: string }) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [src]);
  if (failed) return <span className="placeholder" title="The source blocked this preview; open the source page">{label} · preview blocked</span>;
  return <img src={src} alt="" aria-label={alt} loading="lazy" referrerPolicy="no-referrer" onError={() => setFailed(true)} />;
}

export function formatBytes(n?: number | null): string {
  if (!n) return "";
  if (n > 1e9) return `${(n / 1e9).toFixed(1)} GB`;
  if (n > 1e6) return `${(n / 1e6).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(n / 1e3))} KB`;
}

export function useToast(): [string | null, (msg: string) => void] {
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => {
    if (!msg) return;
    const t = setTimeout(() => setMsg(null), 2800);
    return () => clearTimeout(t);
  }, [msg]);
  return [msg, setMsg];
}

export function download(filename: string, body: string, type = "text/plain") {
  const url = URL.createObjectURL(new Blob([body], { type }));
  const a = Object.assign(document.createElement("a"), { href: url, download: filename });
  a.click();
  URL.revokeObjectURL(url);
}

/** Page header shared by every screen: title, one plain sentence, optional actions on the right. */
export function PageHead({ title, sub, children }: { title: string; sub?: React.ReactNode; children?: React.ReactNode }) {
  return (
    <header className="page-head">
      <div><h1>{title}</h1>{sub && <p className="page-sub">{sub}</p>}</div>
      {children && <div className="page-actions">{children}</div>}
    </header>
  );
}

export function Empty({ title, children }: { title: string; children?: React.ReactNode }) {
  return <div className="empty"><strong>{title}</strong>{children}</div>;
}
