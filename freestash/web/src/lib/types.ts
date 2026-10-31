// Mirrors src/freestash/models.py. Keep in sync when the Python models change.

export type MediaType = "image" | "audio" | "video" | "texture" | "hdri" | "model" | "font" | "icon";
export type UseCase = "reference" | "demo" | "client" | "bundled" | "merch";
export type Tier = "green" | "yellow" | "red";
export type Trust = "institution" | "government" | "curated" | "community" | "uploader" | "unknown";

export interface LicenseInfo { id: string; label: string; url?: string | null; raw?: string | null }
export interface Rendition { url: string; label: string; width?: number | null; height?: number | null; mime?: string | null; bytes?: number | null }

export interface Asset {
  provider: string;
  source_id: string;
  title: string;
  media_type: MediaType;
  license: LicenseInfo;
  trust: Trust;
  landing_url?: string | null;
  source_name?: string | null;
  creator?: string | null;
  creator_url?: string | null;
  thumbnail_url?: string | null;
  preview_url?: string | null;
  renditions: Rendition[];
  width?: number | null;
  height?: number | null;
  duration_seconds?: number | null;
  date?: string | null;
  year?: number | null;
  tags: string[];
  description?: string | null;
  attribution_hint?: string | null;
  notes: string[];
  tips: string[];
  detail_required: boolean;
  extra: Record<string, unknown>;
}

export interface Verdict { use_case: UseCase; tier: Tier; reasons: string[]; obligations: string[]; attribution?: string | null }
export interface ScoredAsset { uid: string; asset: Asset; verdict: Verdict }
export interface ProviderStatus { provider: string; ok: boolean; count: number; total?: number | null; error?: string | null; elapsed_ms: number }

export interface AssetDetail {
  uid: string;
  asset: Asset;
  verdict: Verdict;
  verdicts: Record<UseCase, Verdict>;
  attribution_html: string;
}

export interface ProviderInfo {
  id: string; name: string; homepage: string; media_types: MediaType[]; enabled: boolean;
  key_setting?: string | null; key_optional: boolean; key_signup_url?: string | null; verified_live: boolean; notes: string[];
}

export interface Collection {
  id: string; name: string; description?: string | null; use_case: UseCase; team_id?: string | null;
  created_at?: string | null; item_count: number;
  items?: { uid: string; asset: Asset; verdict: Verdict; note?: string | null; added_at?: string | null }[];
}

export interface LedgerEntry {
  id: string; asset_uid: string; provider: string; title: string; creator?: string | null; landing_url?: string | null;
  file_url?: string | null; license_id: string; license_label: string; license_url?: string | null; trust: Trust;
  use_case: UseCase; tier: Tier; attribution?: string | null; project?: string | null; retrieved_at: string;
}

export const MEDIA_TYPES: { id: MediaType; label: string }[] = [
  { id: "image", label: "Images" }, { id: "audio", label: "Audio" }, { id: "video", label: "Video" },
  { id: "texture", label: "Textures" }, { id: "hdri", label: "HDRIs" }, { id: "model", label: "3D" },
  { id: "font", label: "Fonts" }, { id: "icon", label: "Icons" },
];

export const USE_CASES: { id: UseCase; label: string; hint: string }[] = [
  { id: "reference", label: "Reference", hint: "Mood boards and internal reference. Never shipped or shown." },
  { id: "demo", label: "Demo", hint: "Demo/preview sites and mockups. Files aren't handed to customers." },
  { id: "client", label: "Client", hint: "A commercial client deliverable or production site." },
  { id: "bundled", label: "Bundled", hint: "Ships inside a product: template download, factory library, app." },
  { id: "merch", label: "Merch", hint: "Printed or pressed onto goods for sale." },
];
