// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest";

describe("session", () => {
  beforeEach(() => { localStorage.clear(); vi.resetModules(); });

  it("persists, notifies, and clears", async () => {
    const s = await import("./session");
    expect(s.getSession()).toBeNull();
    s.setSession({ token: "t1", user: { id: "u", email: "ada@example.com", display_name: null } });
    expect(s.getToken()).toBe("t1");
    expect(JSON.parse(localStorage.getItem("freestash.session")!).token).toBe("t1");
    s.updateSessionUser({ id: "u", email: "ada@example.com", display_name: "Ada" });
    expect(s.getSession()?.user.display_name).toBe("Ada");
    s.setSession(null);
    expect(localStorage.getItem("freestash.session")).toBeNull();
  });

  it("restores a saved session on load and survives corrupt storage", async () => {
    localStorage.setItem("freestash.session", JSON.stringify({ token: "saved", user: { id: "u", email: null, display_name: null } }));
    expect((await import("./session")).getToken()).toBe("saved");
    vi.resetModules();
    localStorage.setItem("freestash.session", "{not json");
    expect((await import("./session")).getSession()).toBeNull();
  });

  it("an expired session (401) signs the user out", async () => {
    const s = await import("./session");
    const { api } = await import("./api");
    s.setSession({ token: "stale", user: { id: "u", email: null, display_name: null } });
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "expired" }), { status: 401, headers: { "content-type": "application/json" } })));
    await expect(api.collections()).rejects.toThrow("expired");
    expect(s.getSession()).toBeNull();
    vi.unstubAllGlobals();
  });

  it("ignores a saved value that isn't a whole session (the shell would crash reading user)", async () => {
    for (const bad of [{}, { token: "x" }, { token: "x", user: null }, { token: 7, user: {} }]) {
      vi.resetModules();
      localStorage.setItem("freestash.session", JSON.stringify(bad));
      expect((await import("./session")).getSession()).toBeNull();
    }
  });

  it("a late 401 for an old token doesn't sign out the session that replaced it", async () => {
    const s = await import("./session");
    const { api } = await import("./api");
    s.setSession({ token: "old", user: { id: "u", email: null, display_name: null } });
    let answer: (r: Response) => void = () => {};
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((resolve) => { answer = resolve; })));
    const inFlight = api.collections(); // sent with the old token...
    s.setSession({ token: "new", user: { id: "u", email: null, display_name: null } }); // ...then the password changed
    answer(new Response(JSON.stringify({ detail: "revoked" }), { status: 401, headers: { "content-type": "application/json" } }));
    await expect(inFlight).rejects.toThrow("revoked");
    expect(s.getToken()).toBe("new");
    vi.unstubAllGlobals();
  });
});
