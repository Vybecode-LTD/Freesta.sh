import { useSyncExternalStore } from "react";

/** The signed-in account. One account works here and in the desktop app (same API, same token format). */
export interface SessionUser { id: string; email: string | null; display_name: string | null; created_at?: string | null }
export interface Session { token: string; user: SessionUser }

const KEY = "freestash.session";
const listeners = new Set<() => void>();

function read(): Session | null {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as Session) : null;
  } catch {
    return null;
  }
}

let current: Session | null = read();

export function getSession(): Session | null { return current; }
export function getToken(): string | null { return current?.token ?? null; }

export function setSession(next: Session | null): void {
  current = next;
  try {
    if (next) localStorage.setItem(KEY, JSON.stringify(next)); else localStorage.removeItem(KEY);
  } catch { /* storage unavailable: the session lasts for this tab */ }
  listeners.forEach((fn) => fn());
}

export function updateSessionUser(user: SessionUser): void {
  if (current) setSession({ ...current, user });
}

function subscribe(fn: () => void): () => void {
  listeners.add(fn);
  const onStorage = (e: StorageEvent) => { if (e.key === KEY) { current = read(); fn(); } };
  window.addEventListener("storage", onStorage); // signing out in one tab signs out the others
  return () => { listeners.delete(fn); window.removeEventListener("storage", onStorage); };
}

export function useSession(): Session | null {
  return useSyncExternalStore(subscribe, getSession, getSession);
}
