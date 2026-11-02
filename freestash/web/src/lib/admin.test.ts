import { describe, expect, it } from "vitest";
import { ago, countCell, memberKeyStatus, siteKeyStatus } from "./admin";
import type { AdminKey, KeyState } from "./types";

const state = (over: Partial<KeyState> = {}): KeyState => ({ name: "PEXELS_API_KEY", set: false, hint: null, updated_at: null, ...over });
const key = (over: Partial<AdminKey> = {}): AdminKey => ({
  name: "PEXELS_API_KEY", provider: "pexels", provider_name: "Pexels", label: "API key", limits: "200 an hour", optional: false,
  source: null, hint: null, updated_at: null, unreadable: false, last_ok_at: null, last_error: null, last_error_at: null, ...over,
});

describe("memberKeyStatus", () => {
  it("says when Freesta.sh's own key covers a source the member hasn't set", () => {
    expect(memberKeyStatus({ optional: false }, state({ site: true }), undefined)).toEqual({ tone: "site", label: "Freesta.sh's key" });
    expect(memberKeyStatus({ optional: false }, state({ site: false }), undefined)).toEqual({ tone: "missing", label: "Not set" });
    expect(memberKeyStatus({ optional: true }, state(), undefined)).toEqual({ tone: "optional", label: "Optional" });
  });

  it("the member's own key and a pending removal come first", () => {
    expect(memberKeyStatus({ optional: false }, state({ set: true, hint: "1234", site: true }), undefined))
      .toEqual({ tone: "set", label: "Yours · …1234" });
    expect(memberKeyStatus({ optional: false }, state({ set: true, hint: "1234" }), null)).toEqual({ tone: "removing", label: "Will be removed" });
  });
});

describe("siteKeyStatus", () => {
  it("names where the site's key comes from", () => {
    expect(siteKeyStatus(key({ source: "admin", hint: "9876" }))).toEqual({ tone: "set", label: "Stored · …9876" });
    expect(siteKeyStatus(key({ source: "env" }))).toEqual({ tone: "site", label: "From server env" });
    expect(siteKeyStatus(key())).toEqual({ tone: "missing", label: "Not set" });
    expect(siteKeyStatus(key({ optional: true }))).toEqual({ tone: "optional", label: "Optional" });
  });

  it("flags a key whose latest test failed, or that can't be decrypted", () => {
    const failing = key({ source: "admin", hint: "9876", last_ok_at: "2026-11-02T01:00:00Z", last_error: "401", last_error_at: "2026-11-02T02:00:00Z" });
    expect(siteKeyStatus(failing)).toEqual({ tone: "error", label: "Failing · …9876" });
    const recovered = { ...failing, last_ok_at: "2026-11-02T03:00:00Z" };
    expect(siteKeyStatus(recovered).tone).toBe("set");
    expect(siteKeyStatus(key({ source: "admin", hint: "9876", unreadable: true }))).toEqual({ tone: "error", label: "Can't decrypt · save again" });
  });
});

describe("countCell and ago", () => {
  it("shows the searches sent, and failures only when there are some", () => {
    expect(countCell({ calls: 41, errors: 2 })).toBe("41 · 2 failed");
    expect(countCell({ calls: 3, errors: 0 })).toBe("3");
  });

  it("reads times the way people say them", () => {
    const now = Date.parse("2026-11-02T12:00:00Z");
    expect(ago(null, now)).toBe("never");
    expect(ago("2026-11-02T11:59:30Z", now)).toBe("just now");
    expect(ago("2026-11-02T11:15:00Z", now)).toBe("45 min ago");
    expect(ago("2026-11-02T07:00:00Z", now)).toBe("5 h ago");
    expect(ago("2026-10-30T12:00:00Z", now)).toBe("3 days ago");
    expect(ago("2026-09-01T12:00:00Z", now)).toBe("2026-09-01");
  });
});
