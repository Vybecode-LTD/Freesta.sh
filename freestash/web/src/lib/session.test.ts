// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const ADA = { id: "u", email: "ada@example.com", display_name: null };
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

describe("session", () => {
  beforeEach(() => { localStorage.clear(); vi.resetModules(); });
  afterEach(() => { vi.unstubAllGlobals(); });

  it("persists who is signed in, never a token, and clears", async () => {
    const s = await import("./session");
    expect(s.getSession()).toBeNull();
    s.setSession({ user: ADA });
    const stored = JSON.parse(localStorage.getItem("freestash.session")!);
    expect(stored.user).toEqual(ADA);
    expect(Object.keys(stored).sort()).toEqual(["gen", "user"]);
    s.updateSessionUser({ ...ADA, display_name: "Ada" });
    expect(s.getSession()?.user.display_name).toBe("Ada");
    s.setSession(null);
    expect(localStorage.getItem("freestash.session")).toBeNull();
  });

  it("a replacement session changes what's stored even for the same user, so other tabs hear about it", async () => {
    // PR #5 review: after a password change the user is identical; an identical value fires no `storage` event,
    // and another tab's late 401 (sent with the revoked cookie) would sign every tab out.
    const s = await import("./session");
    s.setSession({ user: ADA });
    const before = localStorage.getItem("freestash.session");
    s.setSession({ user: ADA });
    const after = localStorage.getItem("freestash.session");
    expect(after).not.toBe(before);
    expect(after).not.toMatch(/token/);
    expect(JSON.parse(after!).user).toEqual(ADA);
  });

  it("restores a saved session on load and survives corrupt storage", async () => {
    localStorage.setItem("freestash.session", JSON.stringify({ user: ADA }));
    expect((await import("./session")).getSession()?.user.email).toBe("ada@example.com");
    vi.resetModules();
    localStorage.setItem("freestash.session", "{not json");
    expect((await import("./session")).getSession()).toBeNull();
  });

  it("forgets a session saved with a readable token (before the cookie)", async () => {
    localStorage.setItem("freestash.session", JSON.stringify({ token: "eyJ.old.token", user: ADA }));
    expect((await import("./session")).getSession()).toBeNull();
    expect(localStorage.getItem("freestash.session")).toBeNull();
  });

  it("ignores a saved value that isn't a whole session (the shell would crash reading user)", async () => {
    for (const bad of [{}, { user: null }, { user: {} }, { user: { id: 7 } }, "x"]) {
      vi.resetModules();
      localStorage.setItem("freestash.session", JSON.stringify(bad));
      expect((await import("./session")).getSession()).toBeNull();
    }
  });

  it("an expired session (401) signs the user out", async () => {
    const s = await import("./session");
    const { api } = await import("./api");
    s.setSession({ user: ADA });
    vi.stubGlobal("fetch", vi.fn(async () => json({ detail: "expired" }, 401)));
    await expect(api.collections()).rejects.toThrow("expired");
    expect(s.getSession()).toBeNull();
  });

  it("a late 401 for an old session doesn't sign out the session that replaced it", async () => {
    const s = await import("./session");
    const { api } = await import("./api");
    s.setSession({ user: ADA });
    let answer: (r: Response) => void = () => {};
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((resolve) => { answer = resolve; })));
    const inFlight = api.collections(); // sent with the old cookie...
    s.setSession({ user: { ...ADA, display_name: "after the password change" } }); // ...then the password changed
    answer(json({ detail: "revoked" }, 401));
    await expect(inFlight).rejects.toThrow("revoked");
    expect(s.getSession()?.user.display_name).toBe("after the password change");
  });

  it("sends the cookie, asks for one at sign-in, and sends no Authorization header", async () => {
    const s = await import("./session");
    const { api } = await import("./api");
    const fetchMock = vi.fn(async () => json({ token_type: "cookie", user: ADA }));
    vi.stubGlobal("fetch", fetchMock);
    s.setSession(await api.signIn("ada@example.com", "correct horse battery"));
    expect(s.getSession()).toEqual({ user: ADA });
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    const headers = new Headers(init.headers);
    expect(url).toBe("/api/auth/login");
    expect(init.credentials).toBe("include");
    expect(headers.get("X-Freestash-Session")).toBe("cookie");
    expect(headers.has("Authorization")).toBe(false);
  });

  it("a refused search stream shows the server's words, not its JSON (the hourly cap, PR #6)", async () => {
    const { searchStream } = await import("./api");
    vi.stubGlobal("fetch", vi.fn(async () => json({ detail: "You've reached this hour's limit of 60 searches." }, 429)));
    const run = searchStream({ q: "x", media: ["image"], use: "demo", maxTier: "yellow" }, () => {}, new AbortController().signal);
    await expect(run).rejects.toThrow(/^You've reached this hour's limit of 60 searches\.$/);
  });

  it("a refused stream with an empty body falls back to the status text, and keeps a plain-text body (PR #6 review)", async () => {
    const { searchStream } = await import("./api");
    const run = (r: Response) => {
      vi.stubGlobal("fetch", vi.fn(async () => r));
      return searchStream({ q: "x", media: ["image"], use: "demo", maxTier: "yellow" }, () => {}, new AbortController().signal);
    };
    await expect(run(new Response("", { status: 503, statusText: "Service Unavailable" }))).rejects.toThrow(/^Service Unavailable$/);
    await expect(run(new Response("Bad gateway at the edge", { status: 502 }))).rejects.toThrow(/^Bad gateway at the edge$/);
  });

  it("sign out clears the cookie on the server, and signs out here even if that fails", async () => {
    const s = await import("./session");
    const { api } = await import("./api");
    s.setSession({ user: ADA });
    const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    await api.signOut();
    expect(fetchMock.mock.calls[0][0]).toBe("/api/auth/logout");
    expect(s.getSession()).toBeNull();

    s.setSession({ user: ADA });
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("offline"); }));
    await api.signOut();
    expect(s.getSession()).toBeNull();
  });
});
