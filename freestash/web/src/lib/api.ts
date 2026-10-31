import { getToken, setSession, type Session, type SessionUser } from "./session";
import type {
  Asset, AssetDetail, Collection, KeySpec, KeyState, LedgerEntry, MediaType, Prefs, ProviderInfo, ProviderStatus,
  ScoredAsset, Tier, UseCase, Verdict,
} from "./types";

const BASE = import.meta.env.VITE_API_BASE ?? "";

export class ApiError extends Error {
  constructor(public status: number, public detail: unknown) {
    super(typeof detail === "string" ? detail : (detail as { message?: string })?.message ?? `HTTP ${status}`);
  }
}

function headers(extra?: HeadersInit): Headers {
  const h = new Headers(extra);
  const token = getToken();
  if (token) h.set("Authorization", `Bearer ${token}`);
  return h;
}

async function req<T>(path: string, init: RequestInit = {}): Promise<T> {
  const h = headers(init.headers);
  if (init.body && !h.has("Content-Type")) h.set("Content-Type", "application/json");
  const res = await fetch(`${BASE}${path}`, { ...init, headers: h });
  if (!res.ok) {
    let detail: unknown = res.statusText;
    try { detail = (await res.json()).detail; } catch { /* not JSON */ }
    if (res.status === 401 && getToken()) setSession(null); // expired or revoked: back to sign-in
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

/** Server-sent events over fetch (EventSource can't send an Authorization header). */
export async function searchStream(p: SearchParams, onBatch: (b: StreamBatch) => void, signal: AbortSignal): Promise<void> {
  const qs = new URLSearchParams({ q: p.q, use: p.use, max_tier: p.maxTier, limit: String(p.limit ?? 12), page: String(p.page ?? 1) });
  p.media.forEach((m) => qs.append("media", m));
  p.providers?.forEach((x) => qs.append("providers", x));
  const res = await fetch(`${BASE}/api/search/stream?${qs}`, { headers: headers({ Accept: "text/event-stream" }), signal });
  if (res.status === 401 && getToken()) setSession(null);
  if (!res.ok || !res.body) throw new ApiError(res.status, await res.text());
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

interface AuthResponse { access_token: string; user: SessionUser }
const toSession = (r: AuthResponse): Session => ({ token: r.access_token, user: r.user });

export const api = {
  health: () => req<{ ok: boolean; version: string; auth_mode: "none" | "accounts"; signup_open: boolean }>("/api/health"),

  // ---- account
  signIn: (email: string, password: string) =>
    req<AuthResponse>("/api/auth/login", { method: "POST", body: json({ email, password }) }).then(toSession),
  signUp: (email: string, password: string, display_name?: string) =>
    req<AuthResponse>("/api/auth/register", { method: "POST", body: json({ email, password, display_name }) }).then(toSession),
  me: () => req<SessionUser>("/api/auth/me"),
  updateProfile: (display_name: string) => req<SessionUser>("/api/auth/me", { method: "PATCH", body: json({ display_name }) }),
  changePassword: (current_password: string, new_password: string) =>
    req<AuthResponse>("/api/auth/change-password", { method: "POST", body: json({ current_password, new_password }) }).then(toSession),
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
  ledger: (project?: string) => req<LedgerEntry[]>(`/api/ledger${project ? `?project=${encodeURIComponent(project)}` : ""}`),
  projects: () => req<string[]>("/api/ledger/projects"),
  take: (body: { uid: string; asset: Asset; use_case: UseCase; project?: string; file_url?: string }) =>
    req<LedgerEntry>("/api/ledger", { method: "POST", body: json(body) }),
  exportLedger: (format: "md" | "html" | "csv", project?: string) =>
    req<string>(`/api/ledger/export?format=${format}${project ? `&project=${encodeURIComponent(project)}` : ""}`),
};
