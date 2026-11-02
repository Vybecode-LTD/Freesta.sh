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
  sha256?: string | null; snapshot?: { asset?: Asset; verdict?: Verdict };
}

/** Mirrors freestash.providers.keys.KeySpec: where to get one provider credential. */
export interface KeySpec {
  name: string; setting: string; provider: string; provider_name: string; label: string; url: string; url_label: string;
  steps: string[]; limits: string | null; unlocks: string; optional: boolean; notice: string | null; action: string | null;
}
export interface KeyState { name: string; set: boolean; hint: string | null; updated_at: string | null; site?: boolean }

export type Theme = "dark" | "light";
export type Accent = "sodium" | "iris" | "teal" | "cobalt";

/** Mirrors freestash.accounts.UserPrefs: what follows the account between web and desktop. */
export interface Prefs {
  default_use_case: UseCase; default_max_tier: Tier; default_media: MediaType[]; results_per_source: number;
  theme: Theme; accent: Accent;
}

export const DEFAULT_PREFS: Prefs = {
  default_use_case: "demo", default_max_tier: "yellow", default_media: ["image"], results_per_source: 12,
  theme: "dark", accent: "sodium",
};

export const ACCENTS: { id: Accent; label: string }[] = [
  { id: "sodium", label: "Sodium" }, { id: "iris", label: "Iris" }, { id: "teal", label: "Teal" }, { id: "cobalt", label: "Cobalt" },
];

/** The verdict words both apps use. GREEN/YELLOW/RED stay the engine's names. */
export const TIER_WORD: Record<Tier, string> = { green: "Clear", yellow: "Check", red: "Blocked" };

export const SHOW_OPTIONS: { id: Tier; label: string; hint: string }[] = [
  { id: "green", label: "Clear", hint: "Only results that are clear for this use" },
  { id: "yellow", label: "+ Check", hint: "Also results to check before you use them" },
  { id: "red", label: "All", hint: "Everything, including blocked results" },
];

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

// ---- the admin screen (contract admin-shared-keys); only admins can read these
export interface AdminKey {
  name: string; provider: string; provider_name: string; label: string; limits: string | null; optional: boolean;
  source: "admin" | "env" | null; hint: string | null; updated_at: string | null; unreadable: boolean;
  last_ok_at: string | null; last_error: string | null; last_error_at: string | null;
}
export interface SiteSettings { signup_open: boolean; searches_per_hour: number; disabled_providers: string[] }
export interface UsageCount { calls: number; errors: number }
export interface UsageRow { provider: string; provider_name: string; limits: string | null; today: UsageCount; month: UsageCount }
export interface AdminUser {
  id: string; email: string; display_name: string | null; created_at: string | null; last_seen_at: string | null;
  is_admin: boolean; disabled: boolean;
}
export interface AuditEntry { at: string; admin_email: string | null; action: string; target: string | null; detail: Record<string, unknown> }
