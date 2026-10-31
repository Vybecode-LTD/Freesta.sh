import type { ScoredAsset } from "../lib/types";
import { MediaPreview, TierBadge } from "./bits";

export function AssetCard({ item, onOpen }: { item: ScoredAsset; onOpen: (item: ScoredAsset) => void }) {
  const { asset, verdict } = item;
  return (
    <button className="card" onClick={() => onOpen(item)} title={verdict.reasons[0] ?? ""}>
      <div className={`card-media ${asset.media_type === "icon" ? "icon" : ""}`}>
        <MediaPreview asset={asset} />
      </div>
      <TierBadge tier={verdict.tier} />
      <div className="card-body">
        <div className="card-title">{asset.title}</div>
        <div className="card-meta">
          <span>{asset.source_name || asset.provider}</span>
          <span>{asset.media_type}</span>
        </div>
        <div><span className="lic">{asset.license.label}</span></div>
      </div>
    </button>
  );
}
