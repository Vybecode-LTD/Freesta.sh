/** Pure helpers for the admin screen and the member key list (contract admin-shared-keys). */
import type { AdminKey, CuratedPack, KeySpec, KeyState, MediaType, UsageCount } from "./types";

export type KeyTone = "set" | "site" | "optional" | "missing" | "removing" | "error";
export interface KeyStatus { tone: KeyTone; label: string }

/** A member's own key row. `edit === null` means they've pressed remove and haven't saved yet. */
export function memberKeyStatus(spec: Pick<KeySpec, "optional">, st: KeyState | undefined, edit: string | null | undefined): KeyStatus {
  if (edit === null) return { tone: "removing", label: "Will be removed" };
  if (st?.set) return { tone: "set", label: `Yours · …${st.hint}` };
  if (st?.site) return { tone: "site", label: "Freesta.sh's key" };
  return spec.optional ? { tone: "optional", label: "Optional" } : { tone: "missing", label: "Not set" };
}

/** The site's key row on the admin screen: stored here, read from the server's env, or missing. */
export function siteKeyStatus(k: AdminKey): KeyStatus {
  if (k.unreadable) return { tone: "error", label: "Can't decrypt · save again" };
  if (k.source === "admin") {
    const failing = !!k.last_error_at && (!k.last_ok_at || Date.parse(k.last_error_at) > Date.parse(k.last_ok_at));
    return failing ? { tone: "error", label: `Failing · …${k.hint}` } : { tone: "set", label: `Stored · …${k.hint}` };
  }
  if (k.source === "env") return { tone: "site", label: "From server env" };
  return k.optional ? { tone: "optional", label: "Optional" } : { tone: "missing", label: "Not set" };
}

/** One cell of the shared-quota table: the searches sent, and how many failed when any did. */
export function countCell(c: UsageCount): string {
  return c.errors ? `${c.calls} · ${c.errors} failed` : String(c.calls);
}

export function ago(iso: string | null, now: number = Date.now()): string {
  if (!iso) return "never";
  const minutes = Math.floor((now - Date.parse(iso)) / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  if (minutes < 60 * 24) return `${Math.round(minutes / 60)} h ago`;
  if (minutes < 60 * 24 * 14) return `${Math.round(minutes / (60 * 24))} days ago`;
  return iso.slice(0, 10);
}

// ---- curated packs (contract github-and-curated-packs)

/** The licenses the form offers. The server takes any license it knows; an imported one shows as itself. */
export const CURATED_LICENSES: readonly { id: string; label: string }[] = [
  { id: "CC0-1.0", label: "CC0 1.0" }, { id: "CC-BY-4.0", label: "CC BY 4.0" }, { id: "CC-BY-3.0", label: "CC BY 3.0" },
  { id: "CC-BY-SA-4.0", label: "CC BY-SA 4.0" }, { id: "OFL-1.1", label: "SIL Open Font License 1.1" },
  { id: "MIT", label: "MIT License" }, { id: "Unlicense", label: "The Unlicense" },
];

export const licenseLabel = (id: string) => CURATED_LICENSES.find((l) => l.id === id)?.label ?? id;

/** The add/edit form's fields as typed: lists are comma-separated, the count is text until it's sent. */
export interface CuratedDraft {
  title: string; url: string; publisher: string; media_type: MediaType; license_id: string; license_checked_on: string;
  download_url: string; thumbnail_url: string; item_count: string; formats: string; tags: string; description: string;
}

/** Today as the server counts it (UTC): it refuses a check date in the future. */
export const utcDay = (now: Date = new Date()) => now.toISOString().slice(0, 10);

export function curatedDraft(p?: CuratedPack | null, today: string = utcDay()): CuratedDraft {
  return {
    title: p?.title ?? "", url: p?.url ?? "", publisher: p?.publisher ?? "", media_type: p?.media_type ?? "sprite",
    license_id: p?.license_id ?? "CC0-1.0", license_checked_on: p?.license_checked_on ?? today,
    download_url: p?.download_url ?? "", thumbnail_url: p?.thumbnail_url ?? "",
    item_count: p?.item_count != null ? String(p.item_count) : "", formats: (p?.formats ?? []).join(", "),
    tags: (p?.tags ?? []).join(", "), description: p?.description ?? "",
  };
}

const commaList = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);
const orNull = (s: string) => s.trim() || null;

export function draftToPack(d: CuratedDraft): CuratedPack {
  const count = Number(d.item_count.trim());
  return {
    id: null, title: d.title.trim(), url: d.url.trim(), publisher: d.publisher.trim(), license_id: d.license_id,
    license_checked_on: d.license_checked_on, media_type: d.media_type, download_url: orNull(d.download_url),
    thumbnail_url: orNull(d.thumbnail_url), item_count: d.item_count.trim() && Number.isFinite(count) ? count : null,
    formats: commaList(d.formats), tags: commaList(d.tags), description: orNull(d.description), updated_at: null,
  };
}

const REQUIRED = ["title", "url", "publisher", "license_id", "license_checked_on", "media_type"] as const;

/** The Import box: a JSON list of packs, or `{"packs": [...]}`. Only the shape is checked here; the server checks
 *  every field and saves nothing if a row is wrong. A list copied from this screen's API re-imports as it is. */
export function parseCuratedImport(text: string): { packs: CuratedPack[] } | { error: string } {
  let data: unknown;
  try { data = JSON.parse(text); } catch { return { error: "That isn't valid JSON." }; }
  const rows = Array.isArray(data) ? data : (data as { packs?: unknown } | null)?.packs;
  if (!Array.isArray(rows) || rows.length === 0) return { error: 'Paste a list of packs: [{…}, {…}] or {"packs": [{…}]}.' };
  if (rows.length > 500) return { error: "Import at most 500 packs at a time." };
  const packs: CuratedPack[] = [];
  for (const [i, row] of rows.entries()) {
    if (!row || typeof row !== "object" || Array.isArray(row)) return { error: `Row ${i + 1} isn't a pack.` };
    const r = row as Record<string, unknown>;
    const missing = REQUIRED.filter((f) => typeof r[f] !== "string" || !(r[f] as string).trim());
    if (missing.length) return { error: `Row ${i + 1} has no ${missing.join(", ")}.` };
    packs.push({ ...(r as unknown as CuratedPack), id: null, updated_at: null });
  }
  return { packs };
}

const FIELD_LABELS: Record<string, string> = {
  title: "Title", url: "Page URL", publisher: "Publisher", media_type: "Kind", license_id: "License",
  license_checked_on: "License checked on", download_url: "Download URL", thumbnail_url: "Preview image URL",
  item_count: "Files", formats: "Formats", tags: "Tags", description: "Description",
};

/** A 422's field errors in the form's own words: "Row 2, License: isn't a license Freesta.sh knows". */
export function validationText(detail: unknown): string | null {
  if (!Array.isArray(detail) || detail.length === 0) return null;
  return detail.map((d: { loc?: unknown[]; msg?: string }) => {
    const loc = (d.loc ?? []).filter((x) => x !== "body");
    const row = loc[0] === "packs" && typeof loc[1] === "number" ? `Row ${loc[1] + 1}, ` : "";
    const field = String(loc[loc.length - 1] ?? "");
    return `${row}${FIELD_LABELS[field] ?? field}: ${(d.msg ?? "invalid").replace(/^Value error, /, "")}`;
  }).join(" · ");
}
