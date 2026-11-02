import { useEffect, useMemo, useState } from "react";
import { Icon } from "../components/Icon";
import { api } from "../lib/api";
import { usePrefs } from "../lib/prefs";
import { setSession, updateSessionUser, useSession } from "../lib/session";
import type { KeySpec, KeyState, MediaType, Prefs } from "../lib/types";
import { ACCENTS, MEDIA_TYPES, SHOW_OPTIONS, USE_CASES } from "../lib/types";

type Toast = { onToast: (m: string) => void };
const msg = (e: unknown) => (e instanceof Error ? e.message : String(e));

function Section({ id, icon, title, sub, children }: { id: string; icon: Parameters<typeof Icon>[0]["name"]; title: string; sub: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="panel settings-section" id={id}>
      <div className="settings-intro">
        <h2><Icon name={icon} size={18} />{title}</h2>
        <div className="muted">{sub}</div>
      </div>
      <div className="settings-body">{children}</div>
    </section>
  );
}

export function SettingsPage({ onToast, accountMode }: Toast & { accountMode: boolean }) {
  const { prefs, save, preview } = usePrefs();
  const [draft, setDraft] = useState<Prefs>(prefs);
  const [catalog, setCatalog] = useState<KeySpec[]>([]);
  const [keyStates, setKeyStates] = useState<Record<string, KeyState>>({});
  const [edits, setEdits] = useState<Record<string, string | null>>({});
  const [revealed, setRevealed] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => setDraft(prefs), [prefs]);
  useEffect(() => {
    api.keyCatalog().then(setCatalog).catch((e) => onToast(msg(e)));
    if (accountMode) api.keys().then((ks) => setKeyStates(Object.fromEntries(ks.map((k) => [k.name, k])))).catch(() => undefined);
  }, [accountMode, onToast]);
  useEffect(() => { if (location.hash.includes("keys")) document.getElementById("keys")?.scrollIntoView(); }, [catalog.length]);
  useEffect(() => () => preview(prefs.theme, prefs.accent), []); // eslint-disable-line react-hooks/exhaustive-deps

  const prefsDirty = JSON.stringify(draft) !== JSON.stringify(prefs);
  const keyChanges = useMemo(() => Object.fromEntries(Object.entries(edits).filter(([, v]) => v === null || v.trim() !== "")), [edits]);
  const dirty = prefsDirty || Object.keys(keyChanges).length > 0;
  const set = <K extends keyof Prefs>(k: K, v: Prefs[K]) => setDraft((d) => ({ ...d, [k]: v }));

  async function saveAll() {
    setBusy(true);
    try {
      if (prefsDirty) await save(draft);
      if (Object.keys(keyChanges).length) {
        const ks = await api.saveKeys(keyChanges);
        setKeyStates(Object.fromEntries(ks.map((k) => [k.name, k])));
        setEdits({}); setRevealed({});
      }
      onToast("Saved. Your other devices pick it up next time they load.");
    } catch (e) { onToast(msg(e)); } finally { setBusy(false); }
  }

  function revert() { setDraft(prefs); setEdits({}); setRevealed({}); preview(prefs.theme, prefs.accent); }

  async function reveal(name: string) {
    if (revealed[name] !== undefined) { setRevealed(({ [name]: _, ...rest }) => rest); return; }
    try {
      const value = await api.revealKey(name);
      if (value) setRevealed((r) => ({ ...r, [name]: value }));
    } catch (e) { onToast(msg(e)); }
  }

  async function registerOpenverse() {
    setBusy(true);
    try {
      const r = await api.registerOpenverse();
      const ks = await api.keys();
      setKeyStates(Object.fromEntries(ks.map((k) => [k.name, k])));
      onToast(r.next);
    } catch (e) { onToast(msg(e)); } finally { setBusy(false); }
  }

  const setCount = catalog.filter((k) => keyStates[k.name]?.set).length;

  return (
    <div className="page page-settings">
      <header className="page-head">
        <div><h1>Settings</h1><p className="page-sub">Your account, provider keys, search defaults and look. Everything here follows you to the desktop app.</p></div>
      </header>

      {accountMode ? <AccountSection onToast={onToast} /> : (
        <Section id="account" icon="user" title="This computer" sub="Accounts are off on this server.">
          <p className="muted">This server runs with <span className="mono">FREESTASH_AUTH_MODE=none</span>: one local user, keys from its <span className="mono">.env</span> file. The hosted app at freesta.sh has accounts.</p>
        </Section>
      )}

      <Section id="keys" icon="key" title="API keys" sub={<>All free. Sources without a key stay off; everything else works without any.
        {accountMode && <div className="mono faint keys-count">{setCount} of {catalog.length} set · encrypted in your account</div>}</>}>
        <div className="key-list">
          {catalog.map((spec) => {
            const st = keyStates[spec.name];
            const edit = edits[spec.name];
            const shown = revealed[spec.name];
            const value = edit ?? shown ?? "";
            const status = edit === null ? "removing" : st?.set ? "set" : spec.optional ? "optional" : "missing";
            return (
              <div key={spec.name} className="key-row">
                <div className="key-top">
                  <span className="key-provider">{spec.provider_name}</span>
                  <span className="key-label mono">{spec.label}</span>
                  <span className={`status s-${status}`}>{status === "set" ? `Set · …${st?.hint}` : status === "removing" ? "Will be removed" : status === "optional" ? "Optional" : "Not set"}</span>
                </div>
                <div className="key-input">
                  <input className="input mono" type={shown !== undefined && edit === undefined ? "text" : "password"} autoComplete="off" spellCheck={false}
                         disabled={!accountMode} aria-label={`${spec.provider_name} ${spec.label}`}
                         placeholder={st?.set ? `Saved key ending in ${st.hint}. Paste a new one to replace it.` : `Paste your ${spec.label}`}
                         value={value ?? ""} onChange={(e) => setEdits((x) => ({ ...x, [spec.name]: e.target.value }))} />
                  {st?.set && edit === undefined && (
                    <button type="button" className="icon-btn" onClick={() => reveal(spec.name)} aria-label={shown !== undefined ? "Hide key" : "Show key"}>
                      <Icon name={shown !== undefined ? "eyeOff" : "eye"} /></button>)}
                  {st?.set && edit !== null && (
                    <button type="button" className="icon-btn" onClick={() => setEdits((x) => ({ ...x, [spec.name]: null }))} aria-label="Remove key">
                      <Icon name="trash" /></button>)}
                </div>
                <KeyHelp spec={spec} onRegister={accountMode ? registerOpenverse : undefined} busy={busy} />
              </div>
            );
          })}
        </div>
      </Section>

      <Section id="defaults" icon="search" title="Search defaults" sub="What a new search starts with, on the web and the desktop.">
        <div className="field-grid">
          <label className="field"><span className="eyebrow">Use</span>
            <select className="input" value={draft.default_use_case} onChange={(e) => set("default_use_case", e.target.value as Prefs["default_use_case"])}>
              {USE_CASES.map((u) => <option key={u.id} value={u.id}>{u.label}: {u.hint}</option>)}
            </select></label>
          <label className="field"><span className="eyebrow">Show</span>
            <select className="input" value={draft.default_max_tier} onChange={(e) => set("default_max_tier", e.target.value as Prefs["default_max_tier"])}>
              {SHOW_OPTIONS.map((t) => <option key={t.id} value={t.id}>{t.label}: {t.hint}</option>)}
            </select></label>
          <label className="field"><span className="eyebrow">Results per source</span>
            <input className="input" type="number" min={1} max={50} value={draft.results_per_source}
                   onChange={(e) => set("results_per_source", Math.min(50, Math.max(1, Number(e.target.value) || 12)))} /></label>
        </div>
        <div className="field"><span className="eyebrow">Media</span>
          <div className="pills">{MEDIA_TYPES.map((m) => {
            const on = draft.default_media.includes(m.id);
            const toggle = (id: MediaType) => set("default_media", on ? (draft.default_media.length > 1 ? draft.default_media.filter((x) => x !== id) : draft.default_media) : [...draft.default_media, id]);
            return <button key={m.id} type="button" className="pill" aria-pressed={on} onClick={() => toggle(m.id)}>{m.label}</button>;
          })}</div></div>
      </Section>

      <Section id="appearance" icon="sun" title="Appearance" sub="Previews instantly. Saved to your account.">
        <div className="theme-cards">
          {(["dark", "light"] as const).map((t) => (
            <button key={t} type="button" className={`theme-card t-${t}`} aria-pressed={draft.theme === t}
                    onClick={() => { set("theme", t); preview(t, draft.accent); }}>
              <span className="theme-swatch" data-theme={t}><i /><i /><i /></span>
              <span><strong>{t === "dark" ? "Glass" : "Frost"}</strong><span className="muted">{t === "dark" ? "Cold glass on near-black." : "Frosted glass on cool white."}</span></span>
            </button>
          ))}
        </div>
        <div className="field"><span className="eyebrow">Accent</span>
          <div className="accents">{ACCENTS.map((a) => (
            <button key={a.id} type="button" className="accent-chip" data-accent={a.id} aria-pressed={draft.accent === a.id}
                    onClick={() => { set("accent", a.id); preview(draft.theme, a.id); }}><i />{a.label}</button>
          ))}</div></div>
      </Section>

      <div className={`savebar ${dirty ? "show" : ""}`} role="region" aria-label="Unsaved changes">
        <span className="muted"><Icon name="sync" size={16} />{dirty ? "Unsaved changes" : "Everything saved"}</span>
        <button className="btn btn-ghost" onClick={revert} disabled={!dirty || busy}>Revert</button>
        <button className="btn btn-primary" onClick={saveAll} disabled={!dirty || busy}><Icon name="check" size={16} />Save changes</button>
      </div>
    </div>
  );
}

/** The help under every key field: the exact page, what to do there, the free limits, and anything broken right now. */
export function KeyHelp({ spec, onRegister, busy }: { spec: KeySpec; onRegister?: () => void; busy?: boolean }) {
  return (
    <div className="key-help">
      {spec.notice && <p className="notice"><Icon name="warning" size={15} />{spec.notice}</p>}
      {spec.action === "openverse_register" ? (
        <div className="row wrap">
          <button type="button" className="btn btn-sm" disabled={!onRegister || busy} onClick={onRegister}><Icon name="sparkle" size={15} />Register with Openverse</button>
          <a className="link" href={spec.url} target="_blank" rel="noreferrer">About Openverse credentials ↗</a>
        </div>
      ) : (
        <a className="key-link" href={spec.url} target="_blank" rel="noreferrer">
          <Icon name="external" size={15} />Get this key at <span className="mono">{spec.url_label}</span></a>
      )}
      <ol className="key-steps">{spec.steps.map((s) => <li key={s}>{s}</li>)}</ol>
      <p className="key-foot muted">{spec.unlocks}{spec.limits && <> <span className="mono faint">· Free: {spec.limits}</span></>}</p>
    </div>
  );
}

function AccountSection({ onToast }: Toast) {
  const session = useSession();
  const [name, setName] = useState(session?.user.display_name ?? "");
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");

  async function saveName() {
    try { updateSessionUser(await api.updateProfile(name)); onToast("Name updated"); } catch (e) { onToast(msg(e)); }
  }
  async function changePassword(e: React.FormEvent) {
    e.preventDefault();
    try { setSession(await api.changePassword(current, next)); setCurrent(""); setNext(""); onToast("Password changed. Other devices will ask you to sign in again."); }
    catch (err) { onToast(msg(err)); }
  }
  async function everywhere() {
    if (!confirm("Sign out on every device, including the desktop app?")) return;
    // Sign out here only once the server confirms: if the request failed, other devices are still signed in.
    try { await api.signOutEverywhere(); setSession(null); } catch (e) { onToast(`Couldn't sign out everywhere: ${msg(e)}`); }
  }

  return (
    <Section id="account" icon="user" title="Account" sub={<>Signed in as <strong>{session?.user.email}</strong>. The desktop app uses this same account.</>}>
      <div className="field-grid">
        <label className="field"><span className="eyebrow">Display name</span>
          <div className="row"><input className="input grow" value={name} onChange={(e) => setName(e.target.value)} />
            <button className="btn" onClick={saveName} disabled={name === (session?.user.display_name ?? "")}>Save</button></div></label>
      </div>
      <form className="field" onSubmit={changePassword}>
        <span className="eyebrow">Change password</span>
        <div className="row wrap">
          <input className="input grow" type="password" autoComplete="current-password" placeholder="Current password" value={current} onChange={(e) => setCurrent(e.target.value)} aria-label="Current password" />
          <input className="input grow" type="password" autoComplete="new-password" placeholder="New password (8+ characters)" value={next} onChange={(e) => setNext(e.target.value)} aria-label="New password" />
          <button className="btn" type="submit" disabled={!current || next.length < 8}>Change</button>
        </div>
      </form>
      <div className="row wrap">
        <button className="btn" onClick={() => void api.signOut()}><Icon name="signOut" size={16} />Sign out</button>
        <button className="btn btn-ghost" onClick={everywhere}>Sign out everywhere</button>
      </div>
    </Section>
  );
}
