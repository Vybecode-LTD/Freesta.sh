import { ledgerPath, type LedgerQuery } from "./ledgerPages";
import { getSession, sessionEpoch, setSession, type Session, type SessionUser } from "./session";
import type {
  AdminKey, AdminUser, Asset, AssetDetail, AuditEntry, Collection, KeySpec, KeyState, LedgerEntry, MediaType, Prefs,
  ProviderInfo, ProviderStatus, ScoredAsset, SiteSettings, Tier, UsageRow, UseCase, Verdict,
} from "./types";

const BASE = import.meta.env.VITE_API_BASE ?? "";

export class ApiError extends Error {
  constructor(public status: number, public detail: unknown) {
    super(typeof detail === "string" ? detail : (detail as { message?: string })?.message ?? `HTTP ${status}`);
  }
}

/** The session cookie is HttpOnly: the browser attaches it, script never touches it. `include` also covers a
 *  VITE_API_BASE on another origin (the server's CORS allows credentials for its listed origins). */
const CREDENTIALS: RequestCredentials = "include";
/** Asks the auth routes for the cookie instead of a token in the body (the desktop leaves it out). */
const COOKIE_SESSION = { "X-Freestash-Session": "cookie" };

/** A 401 signs out only the session that made the request: a late answer for an old session (sent just before a
 *  password change) must not sign out the session that replaced it. */
function signOutIfStill(sentAt: number): void {
  if (getSession() && sessionEpoch() === sentAt) setSession(null);
}

async function req<T>(path: string, init: RequestInit = {}): Promise<T> {
  const sentAt = sessionEpoch();
  const h = new Headers(init.headers);
  if (init.body && !h.has("Content-Type")) h.set("Content-Type", "application/json");
  const res = await fetch(`${BASE}${path}`, { ...init, headers: h, credentials: CREDENTIALS });
  if (!res.ok) {
    let detail: unknown = res.statusText;
    try { detail = (await res.json()).detail; } catch { /* not JSON */ }
    if (res.status === 401) signOutIfStill(sentAt); // expired or revoked: back to sign-in
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  const type = res.headers.get("content-type") ?? "";
  return (type.includes("json") ? res.json() : res.text()) as Promise<T>;
}

const json = (body: unknown) => JSON.stringify(body);

export interface SearchParams {
  q: string; media: MediaType[]; use: UseCase; maxTier: Tier; providers?: string[]; limit?: number; page?: number;
}

export interface StreamBatch { status: ProviderStatus; hidden: number; results: ScoredAsset[] }

/** Server-sent events over fetch, so an aborted search can be cancelled mid-stream. */
export async function searchStream(p: SearchParams, onBatch: (b: StreamBatch) => void, signal: AbortSignal): Promise<void> {
  const qs = new URLSearchParams({ q: p.q, use: p.use, max_tier: p.maxTier, limit: String(p.limit ?? 12), page: String(p.page ?? 1) });
  p.media.forEach((m) => qs.append("media", m));
  p.providers?.forEach((x) => qs.append("providers", x));
  const sentAt = sessionEpoch();
  const res = await fetch(`${BASE}/api/search/stream?${qs}`, { headers: { Accept: "text/event-stream" }, credentials: CREDENTIALS, signal });
  if (res.status === 401) signOutIfStill(sentAt);
  if (!res.ok || !res.body) {
    const text = await res.text();
    let detail: unknown = text;
    try { detail = (JSON.parse(text) as { detail?: unknown }).detail ?? text; } catch { /* not JSON */ }
    throw new ApiError(res.status, detail); // e.g. the hourly search cap's own words
  }
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += value;
    let idx: number;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const chunk = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      const event = /^event: (.+)$/m.exec(chunk)?.[1];
      const data = /^data: (.*)$/m.exec(chunk)?.[1];
      if (event === "batch" && data) onBatch(JSON.parse(data) as StreamBatch);
      if (event === "done") return;
    }
  }
}

interface AuthResponse { token_type: "cookie"; user: SessionUser }
const toSession = (r: AuthResponse): Session => ({ user: r.user });

export const api = {
  health: () => req<{ ok: boolean; version: string; auth_mode: "none" | "accounts"; signup_open: boolean }>("/api/health"),

  // ---- account
  signIn: (email: string, password: string) =>
    req<AuthResponse>("/api/auth/login", { method: "POST", headers: COOKIE_SESSION, body: json({ email, password }) }).then(toSession),
  signUp: (email: string, password: string, display_name?: string) =>
    req<AuthResponse>("/api/auth/register", { method: "POST", headers: COOKIE_SESSION, body: json({ email, password, display_name }) }).then(toSession),
  me: () => req<SessionUser>("/api/auth/me"),
  updateProfile: (display_name: string) => req<SessionUser>("/api/auth/me", { method: "PATCH", body: json({ display_name }) }),
  changePassword: (current_password: string, new_password: string) =>
    req<AuthResponse>("/api/auth/change-password", { method: "POST", headers: COOKIE_SESSION, body: json({ current_password, new_password }) }).then(toSession),
  /** Clears this browser's cookie, then the local session, even if the server couldn't be reached. */
  signOut: () => req<void>("/api/auth/logout", { method: "POST" }).catch(() => undefined).finally(() => setSession(null)),
  signOutEverywhere: () => req<void>("/api/auth/logout-all", { method: "POST" }),
  forgot: (email: string) => req<{ ok: boolean }>("/api/auth/forgot", { method: "POST", body: json({ email }) }),
  reset: (token: string, new_password: string) => req<void>("/api/auth/reset", { method: "POST", body: json({ token, new_password }) }),
  prefs: () => req<{ data: Prefs; updated_at: string | null }>("/api/me/settings"),
  savePrefs: (data: Prefs) => req<{ data: Prefs; updated_at: string | null }>("/api/me/settings", { method: "PUT", body: json({ data }) }),
  keyCatalog: () => req<KeySpec[]>("/api/keys/catalog"),
  keys: () => req<{ keys: KeyState[] }>("/api/me/keys").then((r) => r.keys),
  saveKeys: (values: Record<string, string | null>) =>
    req<{ keys: KeyState[] }>("/api/me/keys", { method: "PUT", body: json({ values }) }).then((r) => r.keys),
  revealKey: (name: string) => req<{ name: string; value: string | null }>(`/api/me/keys/${encodeURIComponent(name)}`).then((r) => r.value),
  registerOpenverse: (email?: string) =>
    req<{ values: Record<string, string>; email: string; next: string }>("/api/keys/openverse/register", { method: "POST", body: json({ email }) }),

  // ---- library
  providers: () => req<ProviderInfo[]>("/api/providers"),
  pdCutoff: () => req<{ works: number; sound_recordings: number }>("/api/pd-cutoff"),
  asset: (uid: string, use: UseCase) => req<AssetDetail>(`/api/assets/${encodeURIComponent(uid)}?use=${use}`),
  checkLicense: (license: string, trust: string, media_type: MediaType, year?: number) =>
    req<{ recognized_as: { id: string; label: string; url?: string }; verdicts: Record<UseCase, Verdict> }>(
      "/api/license/check", { method: "POST", body: json({ license, trust, media_type, year: year || null }) }),
  collections: () => req<Collection[]>("/api/collections"),
  collection: (id: string) => req<Collection>(`/api/collections/${id}`),
  createCollection: (name: string, use_case: UseCase, description?: string) =>
    req<Collection>("/api/collections", { method: "POST", body: json({ name, use_case, description }) }),
  deleteCollection: (id: string) => req<void>(`/api/collections/${id}`, { method: "DELETE" }),
  addToCollection: (id: string, item: { uid: string; asset: Asset; note?: string }) =>
    req<Collection>(`/api/collections/${id}/items`, { method: "POST", body: json(item) }),
  removeFromCollection: (id: string, uid: string) =>
    req<void>(`/api/collections/${id}/items/${encodeURIComponent(uid)}`, { method: "DELETE" }),
  ledger: (q: LedgerQuery = {}) => req<LedgerEntry[]>(ledgerPath(q)),
  projects: () => req<string[]>("/api/ledger/projects"),
  take: (body: { uid: string; asset: Asset; use_case: UseCase; project?: string; file_url?: string }) =>
    req<LedgerEntry>("/api/ledger", { method: "POST", body: json(body) }),
  exportLedger: (format: "md" | "html" | "csv", project?: string) =>
    req<string>(`/api/ledger/export?format=${format}${project ? `&project=${encodeURIComponent(project)}` : ""}`),

  // ---- admin (contract admin-shared-keys); the server answers 403 to anyone else
  adminKeys: () => req<AdminKey[]>("/api/admin/keys"),
  saveAdminKeys: (values: Record<string, string | null>) => req<AdminKey[]>("/api/admin/keys", { method: "PUT", body: json({ values }) }),
  testAdminKey: (name: string) =>
    req<{ ok: boolean; elapsed_ms: number; error: string | null }>(`/api/admin/keys/${encodeURIComponent(name)}/test`, { method: "POST" }),
  siteSettings: () => req<SiteSettings>("/api/admin/settings"),
  saveSiteSettings: (changes: Partial<SiteSettings>) => req<SiteSettings>("/api/admin/settings", { method: "PUT", body: json(changes) }),
  usage: () => req<UsageRow[]>("/api/admin/usage"),
  adminUsers: (q?: string) => req<AdminUser[]>(`/api/admin/users${q ? `?q=${encodeURIComponent(q)}` : ""}`),
  updateUser: (id: string, flags: { is_admin?: boolean; disabled?: boolean }) =>
    req<AdminUser>(`/api/admin/users/${encodeURIComponent(id)}`, { method: "PATCH", body: json(flags) }),
  audit: (before?: string) => req<AuditEntry[]>(`/api/admin/audit${before ? `?before=${encodeURIComponent(before)}` : ""}`),
};
