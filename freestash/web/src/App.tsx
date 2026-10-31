import { useEffect, useState } from "react";
import { useToast } from "./components/bits";
import { api } from "./lib/api";
import { AUTH_MODE, currentSession, setActiveTeam, supabase } from "./lib/auth";
import { CollectionsPage, LedgerPage, LicenseCheckPage, SourcesPage } from "./pages/OtherPages";
import { SearchPage } from "./pages/SearchPage";

type Route = "search" | "collections" | "ledger" | "check" | "sources";
const ROUTES: { id: Route; label: string }[] = [
  { id: "search", label: "Search" }, { id: "collections", label: "Collections" }, { id: "ledger", label: "Ledger" },
  { id: "check", label: "License check" }, { id: "sources", label: "Sources" },
];

function routeFromHash(): Route {
  const h = window.location.hash.replace("#/", "") as Route;
  return ROUTES.some((r) => r.id === h) ? h : "search";
}

function Login() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  async function send(e: React.FormEvent) {
    e.preventDefault();
    const { error } = await supabase().auth.signInWithOtp({ email, options: { emailRedirectTo: window.location.origin } });
    if (error) setErr(error.message); else setSent(true);
  }
  return (
    <div className="login">
      <form className="panel" onSubmit={send}>
        <div className="brand"><span className="brand-dot" />Freestash</div>
        <p className="muted" style={{ margin: 0 }}>Sign in with your work email. We'll send a magic link.</p>
        {sent ? <p>Check your inbox for the link.</p> : (
          <>
            <input className="input" type="email" required placeholder="you@studio.com" value={email} onChange={(e) => setEmail(e.target.value)} />
            <button className="btn btn-primary" type="submit">Send magic link</button>
          </>
        )}
        {err && <p style={{ color: "var(--red)", margin: 0 }}>{err}</p>}
      </form>
    </div>
  );
}

export default function App() {
  const [route, setRoute] = useState<Route>(routeFromHash);
  const [authed, setAuthed] = useState(AUTH_MODE === "none");
  const [checking, setChecking] = useState(AUTH_MODE === "supabase");
  const [teamError, setTeamError] = useState<string | null>(null);
  const [toast, setToast] = useToast();

  useEffect(() => {
    const onHash = () => setRoute(routeFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  useEffect(() => {
    if (AUTH_MODE !== "supabase") return;
    currentSession().then((s) => { setAuthed(!!s); setChecking(false); });
    const { data } = supabase().auth.onAuthStateChange((_e, s) => setAuthed(!!s));
    return () => data.subscription.unsubscribe();
  }, []);

  useEffect(() => {
    if (!authed || AUTH_MODE !== "supabase") return;
    api.me().then((me) => me.team_id && setActiveTeam(me.team_id)).catch((e) => setTeamError(e.message));
  }, [authed]);

  if (checking) return null;
  if (!authed) return <Login />;

  const go = (r: Route) => { window.location.hash = `#/${r}`; };

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand"><span className="brand-dot" />Freestash</div>
        <nav className="nav">
          {ROUTES.map((r) => (
            <button key={r.id} aria-current={route === r.id ? "page" : undefined} onClick={() => go(r.id)}>{r.label}</button>
          ))}
        </nav>
        <span className="spacer" />
        {AUTH_MODE === "supabase" && <button className="btn btn-ghost btn-sm" onClick={() => supabase().auth.signOut()}>Sign out</button>}
      </header>
      {teamError ? (
        <div className="page"><div className="empty"><strong>Almost there</strong>{teamError}</div></div>
      ) : (
        <main>
          {route === "search" && <SearchPage onToast={setToast} />}
          {route === "collections" && <CollectionsPage onToast={setToast} />}
          {route === "ledger" && <LedgerPage onToast={setToast} />}
          {route === "check" && <LicenseCheckPage />}
          {route === "sources" && <SourcesPage />}
        </main>
      )}
      {toast && <div className="toast">{toast}</div>}
    </div>
  );
}
