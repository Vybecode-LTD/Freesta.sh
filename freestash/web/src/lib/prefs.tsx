import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api } from "./api";
import { DEFAULT_PREFS, type Accent, type Prefs, type Theme } from "./types";

const CACHE = "freestash.prefs";

function cached(): Prefs {
  try {
    const raw = localStorage.getItem(CACHE);
    if (raw) return { ...DEFAULT_PREFS, ...(JSON.parse(raw) as Partial<Prefs>) };
  } catch { /* storage unavailable */ }
  const light = typeof matchMedia === "function" && matchMedia("(prefers-color-scheme: light)").matches;
  return { ...DEFAULT_PREFS, theme: light ? "light" : "dark" };
}

export function applyAppearance(theme: Theme, accent: Accent): void {
  const el = document.documentElement;
  el.dataset.theme = theme;
  el.dataset.accent = accent;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", theme === "light" ? "#EDF1F6" : "#06090E");
}

interface PrefsCtx {
  prefs: Prefs;
  synced: boolean; // false until the account's copy has loaded (or in local mode)
  save: (next: Prefs) => Promise<void>;
  preview: (theme: Theme, accent: Accent) => void;
}

const Ctx = createContext<PrefsCtx | null>(null);

/** Preferences follow the account: loaded from /api/me/settings, cached locally so the first paint is right. */
export function PrefsProvider({ accountMode, signedIn, children }: { accountMode: boolean; signedIn: boolean; children: ReactNode }) {
  const [prefs, setPrefs] = useState<Prefs>(cached);
  const [synced, setSynced] = useState(false);

  useEffect(() => { applyAppearance(prefs.theme, prefs.accent); }, [prefs.theme, prefs.accent]);

  useEffect(() => {
    if (!accountMode || !signedIn) { setSynced(!accountMode); return; }
    let alive = true;
    api.prefs().then((r) => {
      if (!alive) return;
      setPrefs(r.data);
      try { localStorage.setItem(CACHE, JSON.stringify(r.data)); } catch { /* ignore */ }
      setSynced(true);
    }).catch(() => undefined);
    return () => { alive = false; };
  }, [accountMode, signedIn]);

  const save = useCallback(async (next: Prefs) => {
    const stored = accountMode && signedIn ? (await api.savePrefs(next)).data : next;
    setPrefs(stored);
    try { localStorage.setItem(CACHE, JSON.stringify(stored)); } catch { /* ignore */ }
  }, [accountMode, signedIn]);

  const preview = useCallback((theme: Theme, accent: Accent) => applyAppearance(theme, accent), []);

  return <Ctx.Provider value={{ prefs, synced, save, preview }}>{children}</Ctx.Provider>;
}

export function usePrefs(): PrefsCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("usePrefs outside PrefsProvider");
  return ctx;
}
