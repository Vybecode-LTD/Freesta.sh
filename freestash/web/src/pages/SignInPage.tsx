import { useEffect, useState } from "react";
import { Aperture } from "../components/Aperture";
import { Icon } from "../components/Icon";
import { api } from "../lib/api";
import { setSession } from "../lib/session";

type Mode = "signin" | "signup" | "forgot" | "reset";

function resetToken(): string | null {
  const m = /[?&]token=([^&]+)/.exec(location.hash);
  return location.hash.startsWith("#/reset") && m ? decodeURIComponent(m[1]) : null;
}

export function SignInPage({ signupOpen }: { signupOpen: boolean }) {
  const [mode, setMode] = useState<Mode>(() => (resetToken() ? "reset"
    : location.hash.startsWith("#/signup") && signupOpen ? "signup" : location.hash.startsWith("#/forgot") ? "forgot" : "signin"));
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [lit, setLit] = useState(0);

  useEffect(() => { // the aperture opens while the page settles: a quiet hint of what search looks like
    const t = setInterval(() => setLit((n) => (n >= 20 ? 20 : n + 1)), 90);
    return () => clearInterval(t);
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null); setNote(null);
    try {
      if (mode === "signin") setSession(await api.signIn(email, password));
      else if (mode === "signup") setSession(await api.signUp(email, password, name || undefined));
      else if (mode === "forgot") { await api.forgot(email); setNote("If that email has an account, a reset link is on its way. It works once, for an hour."); }
      else {
        await api.reset(resetToken() ?? "", password);
        history.replaceState(null, "", "#/search");
        setMode("signin"); setPassword(""); setNote("Password changed. Sign in with the new one.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  const title = { signin: "Sign in", signup: "Create your account", forgot: "Reset your password", reset: "Choose a new password" }[mode];
  const cta = { signin: "Sign in", signup: "Create account", forgot: "Send reset link", reset: "Set password" }[mode];

  return (
    <div className="signin">
      <section className="signin-brand">
        <div className="wordmark big">freesta<span>.sh</span></div>
        <Aperture total={20} reported={lit} failed={0} size={148} />
        <h1>Public-domain and openly licensed media, cleared for what you'll actually do with it.</h1>
        <ul className="signin-points">
          <li><Icon name="globe" size={17} />20 museums, archives and libraries searched at once</li>
          <li><Icon name="shield" size={17} />Every result cleared per use: demo, client, bundled, merch</li>
          <li><Icon name="sync" size={17} />One account on the web and the desktop app</li>
        </ul>
      </section>

      <section className="signin-panel">
        <form className="panel signin-card" onSubmit={submit}>
          <h2>{title}</h2>
          {mode === "signup" && (
            <label className="field"><span className="eyebrow">Name (optional)</span>
              <input className="input" autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} /></label>
          )}
          {mode !== "reset" && (
            <label className="field"><span className="eyebrow">Email</span>
              <input className="input" type="email" required autoComplete="email" autoFocus value={email} onChange={(e) => setEmail(e.target.value)} /></label>
          )}
          {mode !== "forgot" && (
            <label className="field"><span className="eyebrow">{mode === "reset" ? "New password" : "Password"}</span>
              <input className="input" type="password" required minLength={mode === "signin" ? 1 : 8}
                     autoComplete={mode === "signin" ? "current-password" : "new-password"}
                     placeholder={mode === "signin" ? "" : "8 characters or more"} value={password} onChange={(e) => setPassword(e.target.value)} /></label>
          )}
          {error && <p className="form-error" role="alert">{error}</p>}
          {note && <p className="form-note" role="status">{note}</p>}
          <button className="btn btn-primary btn-lg btn-block" type="submit" disabled={busy}>{busy ? "One moment…" : cta}</button>

          <div className="signin-alt">
            {mode === "signin" && <>
              <button type="button" className="link" onClick={() => { setMode("forgot"); setError(null); }}>Forgot your password?</button>
              {signupOpen && <span>New here? <button type="button" className="link" onClick={() => { setMode("signup"); setError(null); }}>Create an account</button></span>}
            </>}
            {mode !== "signin" && <button type="button" className="link" onClick={() => { setMode("signin"); setError(null); setNote(null); }}>
              <Icon name="back" size={14} />Back to sign in</button>}
          </div>
        </form>
        <p className="signin-foot muted">The desktop app signs in with this same account.</p>
      </section>
    </div>
  );
}
