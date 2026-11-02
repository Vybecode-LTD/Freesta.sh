import { useCallback, useEffect, useState } from "react";
import { Icon } from "../components/Icon";
import { ago, countCell, siteKeyStatus } from "../lib/admin";
import { api } from "../lib/api";
import type { AdminKey, AdminUser, AuditEntry, KeySpec, ProviderInfo, SiteSettings, UsageRow } from "../lib/types";
import { KeyHelp, Section } from "./SettingsPage";

type Toast = { onToast: (m: string) => void };
const msg = (e: unknown) => (e instanceof Error ? e.message : String(e));

/** Site administration (contract admin-shared-keys). Web only: parity.json says why. Not in the nav, so the two
 *  apps' navigation stays the same; admins reach it from Settings. Every write here goes to the audit log. */
export function AdminPage({ onToast }: Toast) {
  const [denied, setDenied] = useState<string | null>(null);
  useEffect(() => { api.siteSettings().catch((e) => setDenied(msg(e))); }, []);

  return (
    <div className="page page-settings page-admin">
      <header className="page-head">
        <div><h1>Site administration</h1>
          <p className="page-sub">The keys every member searches with, the limits on them, who can sign in, and a log of every change made here.</p></div>
      </header>
      {denied ? <p className="notice"><Icon name="warning" size={15} />{denied}</p> : (<>
        <KeysSection onToast={onToast} />
        <LimitsSection onToast={onToast} />
        <UsageSection />
        <UsersSection onToast={onToast} />
        <AuditSection />
      </>)}
    </div>
  );
}

function KeysSection({ onToast }: Toast) {
  const [keys, setKeys] = useState<AdminKey[]>([]);
  const [catalog, setCatalog] = useState<Record<string, KeySpec>>({});
  const [edits, setEdits] = useState<Record<string, string | null>>({});
  const [testing, setTesting] = useState<string | null>(null);

  useEffect(() => {
    api.adminKeys().then(setKeys).catch((e) => onToast(msg(e)));
    api.keyCatalog().then((c) => setCatalog(Object.fromEntries(c.map((k) => [k.name, k])))).catch(() => {});
  }, [onToast]);

  async function save() {
    try { setKeys(await api.saveAdminKeys(edits)); setEdits({}); onToast("Saved. Members' searches use these now."); }
    catch (e) { onToast(msg(e)); }
  }
  async function test(name: string) {
    setTesting(name);
    try {
      const r = await api.testAdminKey(name);
      onToast(r.ok ? `Works (${r.elapsed_ms} ms)` : `Failed: ${r.error}`);
      setKeys(await api.adminKeys());
    } catch (e) { onToast(msg(e)); } finally { setTesting(null); }
  }

  const stored = keys.filter((k) => k.source).length;
  const dirty = Object.keys(edits).length > 0;
  return (
    <Section id="site-keys" icon="key" title="Site keys" sub={<>Every member's search uses these unless they add their own. Stored encrypted; never shown again.
      <div className="mono faint keys-count">{stored} of {keys.length} covered</div></>}>
      <div className="key-list">
        {keys.map((k) => {
          const edit = edits[k.name];
          const status = edit === null ? { tone: "removing", label: "Will be removed" } : siteKeyStatus(k);
          const spec = catalog[k.name];
          return (
            <div key={k.name} className="key-row">
              <div className="key-top">
                <span className="key-provider">{k.provider_name}</span>
                <span className="key-label mono">{k.label}</span>
                <span className={`status s-${status.tone}`}>{status.label}</span>
              </div>
              <div className="key-input">
                <input className="input mono" type="password" autoComplete="off" spellCheck={false} aria-label={`${k.provider_name} ${k.label}`}
                       placeholder={k.source === "admin" ? `Stored key ending in ${k.hint}. Paste a new one to replace it.`
                         : k.source === "env" ? "Using the server's env key. Paste one to store it here instead." : `Paste the ${k.label}`}
                       value={edit ?? ""} onChange={(e) => setEdits((x) => ({ ...x, [k.name]: e.target.value }))} />
                {k.source && <button type="button" className="btn btn-sm" disabled={testing !== null || dirty} onClick={() => test(k.name)}
                                     title={dirty ? "Save first" : undefined}>{testing === k.name ? "Testing…" : "Test"}</button>}
                {k.source === "admin" && edit !== null && (
                  <button type="button" className="icon-btn" onClick={() => setEdits((x) => ({ ...x, [k.name]: null }))} aria-label={`Remove the stored ${k.provider_name} key`}>
                    <Icon name="trash" /></button>)}
              </div>
              {k.source && <p className="mono faint small">{[k.limits, testLine(k)].filter(Boolean).join(" · ")}</p>}
              {spec && !k.source && (spec.action === "openverse_register"
                ? <p className="muted small">Openverse has no sign-up page: press Register in your own Settings → API keys, show the pair there, and paste it here.</p>
                : <KeyHelp spec={spec} />)}
            </div>
          );
        })}
      </div>
      <div className="row"><button className="btn btn-primary" disabled={!dirty} onClick={save}>Save keys</button>
        {dirty && <button className="btn btn-ghost" onClick={() => setEdits({})}>Discard</button>}</div>
    </Section>
  );
}

function testLine(k: AdminKey): string {
  if (k.last_error && k.last_error_at && (!k.last_ok_at || Date.parse(k.last_error_at) > Date.parse(k.last_ok_at)))
    return `Last test failed ${ago(k.last_error_at)}: ${k.last_error}`;
  if (k.last_ok_at) return `Last test passed ${ago(k.last_ok_at)}`;
  return k.source === "admin" ? "Not tested yet" : "";
}

function LimitsSection({ onToast }: Toast) {
  const [site, setSite] = useState<SiteSettings | null>(null);
  const [draft, setDraft] = useState<SiteSettings | null>(null);
  const [providers, setProviders] = useState<ProviderInfo[]>([]);

  useEffect(() => {
    api.siteSettings().then((s) => { setSite(s); setDraft(s); }).catch(() => {});
    api.providers().then(setProviders).catch(() => {});
  }, []);

  if (!site || !draft) return null;
  const dirty = JSON.stringify(site) !== JSON.stringify(draft);
  const toggle = (id: string) => setDraft({ ...draft, disabled_providers: draft.disabled_providers.includes(id)
    ? draft.disabled_providers.filter((p) => p !== id) : [...draft.disabled_providers, id] });

  async function save() {
    if (!draft) return;
    try { const s = await api.saveSiteSettings(draft); setSite(s); setDraft(s); onToast("Saved"); } catch (e) { onToast(msg(e)); }
  }

  return (
    <Section id="limits" icon="shield" title="Limits and sources" sub="Applies to every member at once. Admins aren't capped.">
      <div className="field-grid">
        <label className="field"><span className="eyebrow">Searches per member, per hour</span>
          <input className="input" type="number" min={1} max={10000} value={draft.searches_per_hour}
                 onChange={(e) => setDraft({ ...draft, searches_per_hour: Number(e.target.value) || 1 })} /></label>
        <label className="check"><input type="checkbox" checked={draft.signup_open}
                                        onChange={(e) => setDraft({ ...draft, signup_open: e.target.checked })} />Anyone can create an account</label>
      </div>
      <div className="field">
        <span className="eyebrow">Sources</span>
        <div className="pills wrap" role="group" aria-label="Sources on or off">
          {providers.map((p) => (
            <button key={p.id} type="button" className="pill" aria-pressed={!draft.disabled_providers.includes(p.id)} onClick={() => toggle(p.id)}>{p.name}</button>
          ))}
        </div>
        <p className="muted small">A source that's off isn't searched for anyone. Lit means on.</p>
      </div>
      <div className="row"><button className="btn btn-primary" disabled={!dirty} onClick={save}>Save</button>
        {dirty && <button className="btn btn-ghost" onClick={() => setDraft(site)}>Discard</button>}</div>
    </Section>
  );
}

function UsageSection() {
  const [rows, setRows] = useState<UsageRow[]>([]);
  useEffect(() => { api.usage().then(setRows).catch(() => {}); }, []);
  return (
    <Section id="usage" icon="sync" title="Shared quota" sub="Searches sent to each keyed source on the site's key (UTC days). A member's own key costs the site nothing.">
      <div className="panel table-wrap">
        <table className="table">
          <thead><tr><th>Source</th><th>Today</th><th>This month</th><th>The source's limit</th></tr></thead>
          <tbody>{rows.map((u) => (
            <tr key={u.provider}><td className="nowrap">{u.provider_name}</td><td className="mono nowrap">{countCell(u.today)}</td>
              <td className="mono nowrap">{countCell(u.month)}</td><td className="muted">{u.limits ?? "—"}</td></tr>
          ))}</tbody>
        </table>
      </div>
    </Section>
  );
}

function UsersSection({ onToast }: Toast) {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [q, setQ] = useState("");
  const load = useCallback((query: string) => api.adminUsers(query).then(setUsers).catch((e) => onToast(msg(e))), [onToast]);
  useEffect(() => { void load(""); }, [load]);

  async function flip(u: AdminUser, flags: { is_admin?: boolean; disabled?: boolean }, confirmText: string) {
    if (!confirm(confirmText)) return;
    try { const next = await api.updateUser(u.id, flags); setUsers((list) => list.map((x) => (x.id === u.id ? next : x))); }
    catch (e) { onToast(msg(e)); }
  }

  return (
    <Section id="users" icon="user" title="Users" sub="Newest first. A disabled account can't sign in, and its open sessions stop working.">
      <form className="row" onSubmit={(e) => { e.preventDefault(); void load(q); }}>
        <input className="input grow" placeholder="Find by email or name" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Find users" />
        <button className="btn" type="submit"><Icon name="search" size={15} />Find</button>
      </form>
      <div className="panel table-wrap">
        <table className="table">
          <thead><tr><th>Account</th><th>Joined</th><th>Last seen</th><th>Role</th><th /></tr></thead>
          <tbody>{users.map((u) => (
            <tr key={u.id}>
              <td><div>{u.email}</div>{u.display_name && <div className="muted small">{u.display_name}</div>}</td>
              <td className="mono nowrap">{u.created_at?.slice(0, 10) ?? "—"}</td>
              <td className="mono nowrap">{ago(u.last_seen_at)}</td>
              <td className="nowrap">{u.disabled ? <span className="status s-removing">Disabled</span>
                : u.is_admin ? <span className="status s-set">{u.bootstrap ? "Admin · server-set" : "Admin"}</span>
                : <span className="status">Member</span>}</td>
              <td>{!u.bootstrap && (
                <div className="row nowrap">
                  <button className="btn btn-sm btn-ghost" onClick={() => flip(u, { is_admin: !u.is_admin },
                    u.is_admin ? `Make ${u.email} a member again?` : `Make ${u.email} an admin? They'll see and change everything here.`)}>
                    {u.is_admin ? "Remove admin" : "Make admin"}</button>
                  <button className="btn btn-sm btn-ghost" onClick={() => flip(u, { disabled: !u.disabled },
                    u.disabled ? `Let ${u.email} sign in again?` : `Disable ${u.email}? They're signed out everywhere until you turn it back on.`)}>
                    {u.disabled ? "Enable" : "Disable"}</button>
                </div>)}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
    </Section>
  );
}

const ACTIONS: Record<string, string> = { "keys.update": "Site keys", "settings.update": "Limits and sources", "user.update": "User" };

function AuditSection() {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [more, setMore] = useState(false);
  const load = useCallback(async (before?: string) => {
    const page = await api.audit(before);
    setEntries((list) => (before ? [...list, ...page] : page));
    setMore(page.length === 50);
  }, []);
  useEffect(() => { void load().catch(() => {}); }, [load]);

  return (
    <Section id="audit" icon="ledger" title="Audit log" sub="Every change made on this screen, newest first. Key values are never recorded, only that one was set or cleared.">
      <div className="panel table-wrap">
        <table className="table">
          <thead><tr><th>When</th><th>Who</th><th>What</th><th>Change</th></tr></thead>
          <tbody>{entries.map((a) => (
            <tr key={`${a.at}-${a.action}-${a.target ?? ""}`}>
              <td className="mono nowrap">{a.at.slice(0, 16).replace("T", " ")}</td>
              <td>{a.admin_email ?? "—"}</td>
              <td>{ACTIONS[a.action] ?? a.action}{a.target ? <div className="muted small">{a.target}</div> : null}</td>
              <td className="mono small">{Object.entries(a.detail).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(", ") || "none" : String(v)}`).join(" · ")}</td>
            </tr>
          ))}</tbody>
        </table>
        {entries.length === 0 && <p className="muted pad">Nothing yet.</p>}
      </div>
      {more && <div className="row"><button className="btn" onClick={() => void load(entries[entries.length - 1]?.at)}>Load more</button></div>}
    </Section>
  );
}
