import { createClient, type Session, type SupabaseClient } from "@supabase/supabase-js";

export const AUTH_MODE = (import.meta.env.VITE_AUTH_MODE ?? "none") as "none" | "supabase";

let client: SupabaseClient | null = null;

export function supabase(): SupabaseClient {
  if (!client) {
    const url = import.meta.env.VITE_SUPABASE_URL;
    const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY;
    if (!url || !key) throw new Error("VITE_SUPABASE_URL and VITE_SUPABASE_PUBLISHABLE_KEY are required in supabase mode");
    client = createClient(url, key);
  }
  return client;
}

export async function accessToken(): Promise<string | null> {
  if (AUTH_MODE !== "supabase") return null;
  const { data } = await supabase().auth.getSession();
  return data.session?.access_token ?? null;
}

export async function currentSession(): Promise<Session | null> {
  if (AUTH_MODE !== "supabase") return null;
  return (await supabase().auth.getSession()).data.session;
}

const TEAM_KEY = "freestash.team";
export function activeTeam(): string | null {
  try { return localStorage.getItem(TEAM_KEY); } catch { return null; }
}
export function setActiveTeam(id: string): void {
  try { localStorage.setItem(TEAM_KEY, id); } catch { /* storage unavailable */ }
}
