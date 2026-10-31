import { accessToken, activeTeam } from "./auth";
import type {
  Asset, AssetDetail, Collection, LedgerEntry, MediaType, ProviderInfo, ProviderStatus, ScoredAsset, Tier, UseCase, Verdict,
} from "./types";

const BASE = import.meta.env.VITE_API_BASE ?? "";

export class ApiError extends Error {
  constructor(public status: number, public detail: unknown) {
    super(typeof detail === "string" ? detail : (detail as { message?: string })?.message ?? `HTTP ${status}`);
  }
}

async function headers(extra?: HeadersInit): Promise<Headers> {
  const h = new Headers(extra);
  const token = await accessToken();
  if (token) h.set("Authorization", `Bearer ${token}`);
  const team = activeTeam();
  if (team) h.set("X-Freestash-Team", team);
  return h;
}

async function req<T>(path: string, init: RequestInit = {}): Promise<T> {
  const h = await headers(init.headers);
  if (init.body && !h.has("Content-Type")) h.set("Content-Type", "application/json");
  const res = await fetch(`${BASE}${path}`, { ...init, headers: h });
  if (!res.ok) {
    let detail: unknown = res.statusText;
    try { detail = (await res.json()).detail; } catch { /* not JSON */ }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  const type = res.headers.get("content-type") ?? "";
  return (type.includes("json") ? res.json() : res.text()) as Promise<T>;
}

export interface SearchParams {
  q: string; media: MediaType[]; use: UseCase; maxTier: Tier; providers?: string[]; limit?: number; page?: number;
}

export interface StreamBatch { status: ProviderStatus; hidden: number; results: ScoredAsset[] }

/** Server-sent events over fetch (EventSource can't send an Authorization header). */
export async function searchStream(p: SearchParams, onBatch: (b: StreamBatch) => void, signal: AbortSignal): Promise<void> {
  const qs = new URLSearchParams({ q: p.q, use: p.use, max_tier: p.maxTier, limit: String(p.limit ?? 12), page: String(p.page ?? 1) });
  p.media.forEach((m) => qs.append("media", m));
  p.providers?.forEach((x) => qs.append("providers", x));
  const res = await fetch(`${BASE}/api/search/stream?${qs}`, { headers: await headers({ Accept: "text/event-stream" }), signal });
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

export const api = {
  me: () => req<{ id: string; email?: string; team_id?: string; teams: string[] }>("/api/me"),
  health: () => req<{ ok: boolean; version: string; auth_mode: string }>("/api/health"),
  providers: () => req<ProviderInfo[]>("/api/providers"),
  pdCutoff: () => req<{ works: number; sound_recordings: number }>("/api/pd-cutoff"),
  asset: (uid: string, use: UseCase) => req<AssetDetail>(`/api/assets/${encodeURIComponent(uid)}?use=${use}`),
  checkLicense: (license: string, trust: string, media_type: MediaType, year?: number) =>
    req<{ recognized_as: { id: string; label: string; url?: string }; verdicts: Record<UseCase, Verdict> }>(
      "/api/license/check", { method: "POST", body: JSON.stringify({ license, trust, media_type, year: year || null }) }),
  collections: () => req<Collection[]>("/api/collections"),
  collection: (id: string) => req<Collection>(`/api/collections/${id}`),
  createCollection: (name: string, use_case: UseCase, description?: string) =>
    req<Collection>("/api/collections", { method: "POST", body: JSON.stringify({ name, use_case, description }) }),
  deleteCollection: (id: string) => req<void>(`/api/collections/${id}`, { method: "DELETE" }),
  addToCollection: (id: string, item: { uid: string; asset: Asset; note?: string }) =>
    req<Collection>(`/api/collections/${id}/items`, { method: "POST", body: JSON.stringify(item) }),
  removeFromCollection: (id: string, uid: string) =>
    req<void>(`/api/collections/${id}/items/${encodeURIComponent(uid)}`, { method: "DELETE" }),
  ledger: (project?: string) => req<LedgerEntry[]>(`/api/ledger${project ? `?project=${encodeURIComponent(project)}` : ""}`),
  projects: () => req<string[]>("/api/ledger/projects"),
  take: (body: { uid: string; asset: Asset; use_case: UseCase; project?: string; file_url?: string }) =>
    req<LedgerEntry>("/api/ledger", { method: "POST", body: JSON.stringify(body) }),
  exportLedger: (format: "md" | "html" | "csv", project?: string) =>
    req<string>(`/api/ledger/export?format=${format}${project ? `&project=${encodeURIComponent(project)}` : ""}`),
};
