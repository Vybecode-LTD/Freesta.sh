/** Pure helpers for the admin screen and the member key list (contract admin-shared-keys). */
import type { AdminKey, KeySpec, KeyState, UsageCount } from "./types";

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
