import { useSyncExternalStore } from "react";

/** The signed-in account. One account works here and in the desktop app. The website's sign-in token lives in an
 *  HttpOnly cookie the server sets, so no script here can read it (contract web-cookie-session). What's kept in
 *  localStorage is only who is signed in: it draws the shell at once and lets other tabs follow a sign-out. */
export interface SessionUser { id: string; email: string | null; display_name: string | null; created_at?: string | null; is_admin?: boolean }
export interface Session { user: SessionUser }

const KEY = "freestash.session";
const listeners = new Set<() => void>();
let epoch = 0;

/** Only a whole session counts: a stored `{}` or `{"user":null}` would let the shell render and then crash on `user`. */
function isSession(v: unknown): v is Session {
  const s = v as Session | null;
  return !!s && typeof s.user === "object" && s.user !== null && typeof s.user.id === "string";
}

function read(): Session | null {
  try {
    const raw = localStorage.getItem(KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : null;
    if (parsed && typeof parsed === "object" && "token" in parsed) {
      // Saved before the cookie (PR #5): a readable token with no cookie behind it. Forget it; sign in once more.
      localStorage.removeItem(KEY);
      return null;
    }
    return isSession(parsed) ? { user: parsed.user } : null;
  } catch {
    return null;
  }
}

let current: Session | null = read();

export function getSession(): Session | null { return current; }

/** Bumped on every sign-in, sign-out and account change, so a late 401 can tell whether it's about this session. */
export function sessionEpoch(): number { return epoch; }

/** A non-secret id for each session written. After a password change the user is identical, and an identical
 *  value fires no `storage` event: other tabs would keep their epoch, and a late 401 there (sent with the revoked
 *  cookie) would sign every tab out (PR #5 review). */
function generation(): string {
  return `${Date.now().toString(36)}.${Math.random().toString(36).slice(2)}`;
}

export function setSession(next: Session | null): void {
  current = next ? { user: next.user } : null;
  epoch += 1;
  try {
    if (current) localStorage.setItem(KEY, JSON.stringify({ ...current, gen: generation() })); else localStorage.removeItem(KEY);
  } catch { /* storage unavailable: the session lasts for this tab */ }
  listeners.forEach((fn) => fn());
}

export function updateSessionUser(user: SessionUser): void {
  if (current) setSession({ user });
}

function subscribe(fn: () => void): () => void {
  listeners.add(fn);
  const onStorage = (e: StorageEvent) => { if (e.key === KEY) { current = read(); epoch += 1; fn(); } };
  window.addEventListener("storage", onStorage); // signing out in one tab signs out the others
  return () => { listeners.delete(fn); window.removeEventListener("storage", onStorage); };
}

export function useSession(): Session | null {
  return useSyncExternalStore(subscribe, getSession, getSession);
}
