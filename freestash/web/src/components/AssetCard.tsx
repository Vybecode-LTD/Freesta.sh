import { packBadge } from "../lib/results";
import type { ScoredAsset } from "../lib/types";
import { MediaPreview, Verdict } from "./bits";

export function AssetCard({ item, onOpen }: { item: ScoredAsset; onOpen: (item: ScoredAsset) => void }) {
  const { asset, verdict } = item;
  const meta = [asset.source_name || asset.provider, asset.year ?? asset.date].filter(Boolean).join(" · ");
  return (
    <button className="card" onClick={() => onOpen(item)} title={verdict.reasons[0] ?? ""}>
      <div className={`card-media m-${asset.media_type}`}>
        <MediaPreview asset={asset} />
        {asset.is_pack && <span className="pack-badge">{packBadge(asset)}</span>}
      </div>
      <div className="card-plate">
        <div className="card-title">{asset.title}</div>
        <div className="card-meta">{meta || asset.media_type}</div>
        <div className="card-foot">
          <Verdict tier={verdict.tier} />
          <span className="lic" title={asset.license.label}>{asset.license.label}</span>
        </div>
      </div>
    </button>
  );
}
