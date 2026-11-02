import { useEffect, useState } from "react";
import { useToast } from "./components/bits";
import { Icon, type IconName } from "./components/Icon";
import { api } from "./lib/api";
import { PrefsProvider } from "./lib/prefs";
import { showsSignIn } from "./lib/gate";
import { updateSessionUser, useSession } from "./lib/session";
import { AdminPage } from "./pages/AdminPage";
import { CollectionsPage, DownloadsPage, LedgerPage, LicenseCheckPage, SourcesPage } from "./pages/OtherPages";
import { SearchPage } from "./pages/SearchPage";
import { SettingsPage } from "./pages/SettingsPage";
import { SignInPage } from "./pages/SignInPage";

type Route = "search" | "collections" | "downloads" | "ledger" | "check" | "sources" | "settings" | "admin";
// Same screens, same order, same names as the desktop app's nav rail (shared/parity.json).
const NAV: { group: string; items: { id: Route; label: string; icon: IconName }[] }[] = [
  { group: "Library", items: [
    { id: "search", label: "Search", icon: "search" }, { id: "collections", label: "Collections", icon: "collections" },
    { id: "downloads", label: "Downloads", icon: "downloads" }, { id: "ledger", label: "Ledger", icon: "ledger" },
  ] },
  { group: "Tools", items: [
    { id: "check", label: "License check", icon: "shield" }, { id: "sources", label: "Sources", icon: "globe" },
    { id: "settings", label: "Settings", icon: "settings" },
  ] },
];
// Site administration is web-only and reached from Settings, not the nav (parity.json `admin`).
const ROUTES: Route[] = [...NAV.flatMap((g) => g.items.map((i) => i.id)), "admin"];

function routeFromHash(): Route {
  const h = window.location.hash.replace(/^#\//, "").split("?")[0] as Route;
  return ROUTES.includes(h) ? h : "search";
}

export default function App() {
  const [health, setHealth] = useState<{ auth_mode: "none" | "accounts"; signup_open: boolean } | null>(null);
  const [offline, setOffline] = useState(false);
  const [hash, setHash] = useState(window.location.hash);
  const session = useSession();

  useEffect(() => { api.health().then(setHealth).catch(() => setOffline(true)); }, []);
  useEffect(() => {
    const onHash = () => setHash(window.location.hash);
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  if (offline) return <div className="boot"><strong>Can't reach the Freesta.sh server.</strong><span className="muted">Check your connection and reload.</span></div>;
  if (!health) return <div className="boot" aria-busy="true" />;

  const accountMode = health.auth_mode === "accounts";
  return (
    <PrefsProvider accountMode={accountMode} signedIn={!!session}>
      {showsSignIn(accountMode, !!session, hash) ? <SignInPage signupOpen={health.signup_open} /> : <Shell accountMode={accountMode} />}
    </PrefsProvider>
  );
}

function Shell({ accountMode }: { accountMode: boolean }) {
  const [route, setRoute] = useState<Route>(routeFromHash);
  const [toast, setToast] = useToast();
  const session = useSession();

  useEffect(() => {
    const onHash = () => setRoute(routeFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  // Refresh who's signed in once per load: an admin made or unmade since the last sign-in shows up here.
  useEffect(() => { if (accountMode) api.me().then(updateSessionUser).catch(() => {}); }, [accountMode]);

  const name = session?.user.display_name || session?.user.email?.split("@")[0] || "This computer";

  return (
    <div className="shell">
      <aside className="rail">
        <a className="wordmark" href="#/search" aria-label="Freesta.sh home">freesta<span>.sh</span></a>
        <nav className="nav" aria-label="Main">
          {NAV.map((g) => (
            <div key={g.group} className="nav-group">
              <span className="eyebrow nav-eyebrow">{g.group}</span>
              {g.items.map((i) => (
                <a key={i.id} href={`#/${i.id}`} className="nav-link" aria-current={route === i.id ? "page" : undefined}>
                  <Icon name={i.icon} />{i.label}
                </a>
              ))}
            </div>
          ))}
        </nav>
        <a className="acct" href="#/settings">
          <span className="acct-name">{name}</span>
          <span className="acct-sync mono"><b aria-hidden="true" />{accountMode ? "synced · web + desktop" : "local engine"}</span>
        </a>
      </aside>
      <main className="main" id="main">
        {route === "search" && <SearchPage onToast={setToast} />}
        {route === "collections" && <CollectionsPage onToast={setToast} />}
        {route === "downloads" && <DownloadsPage onToast={setToast} />}
        {route === "ledger" && <LedgerPage onToast={setToast} />}
        {route === "check" && <LicenseCheckPage />}
        {route === "sources" && <SourcesPage />}
        {route === "settings" && <SettingsPage onToast={setToast} accountMode={accountMode} />}
        {route === "admin" && <AdminPage onToast={setToast} />}
      </main>
      {toast && <div className="toast" role="status">{toast}</div>}
    </div>
  );
}
