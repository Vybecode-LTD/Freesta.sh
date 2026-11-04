import { describe, expect, it } from "vitest";
import {
  ago, countCell, curatedDraft, draftToPack, licenseLabel, memberKeyStatus, parseCuratedImport, siteKeyStatus, utcDay,
  validationText,
} from "./admin";
import type { AdminKey, CuratedPack, KeyState } from "./types";

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

const curated: CuratedPack = {
  id: "p1", title: "Space Kit", url: "https://kenney.nl/assets/space-kit", publisher: "Kenney", license_id: "CC0-1.0",
  license_checked_on: "2026-11-04", media_type: "model", download_url: null, thumbnail_url: null, item_count: 90,
  formats: ["glb", "fbx"], tags: ["space"], description: null, updated_at: "2026-11-04T12:00:00+00:00",
};

describe("curated packs", () => {
  it("a draft round-trips a pack, and an empty one starts on today in UTC", () => {
    expect(draftToPack(curatedDraft(curated))).toEqual({ ...curated, id: null, updated_at: null });
    const blank = curatedDraft(null, "2026-11-04");
    expect([blank.license_id, blank.license_checked_on, blank.media_type, blank.item_count]).toEqual(["CC0-1.0", "2026-11-04", "sprite", ""]);
    expect(utcDay(new Date("2026-11-04T23:30:00-05:00"))).toBe("2026-11-05"); // the server's day, not the browser's
  });

  it("sends lists without blanks, empty fields as null and no count unless one was typed", () => {
    const p = draftToPack({ ...curatedDraft(null, "2026-11-04"), title: " Tiny Ski ", formats: "png, , svg ,", tags: "",
      item_count: "  ", download_url: "  " });
    expect([p.title, p.formats, p.tags, p.item_count, p.download_url]).toEqual(["Tiny Ski", ["png", "svg"], [], null, null]);
    expect(draftToPack({ ...curatedDraft(), item_count: "12" }).item_count).toBe(12);
  });

  it("an import takes a list or {packs}, names the row that's wrong, and drops ids", () => {
    const row = { ...curated };
    expect(parseCuratedImport(JSON.stringify([row]))).toEqual({ packs: [{ ...curated, id: null, updated_at: null }] });
    expect("packs" in parseCuratedImport(JSON.stringify({ packs: [row, row] }))).toBe(true);
    expect(parseCuratedImport("not json")).toEqual({ error: "That isn't valid JSON." });
    expect(parseCuratedImport("[]")).toHaveProperty("error");
    expect(parseCuratedImport(JSON.stringify([row, { ...row, url: " ", publisher: undefined }])))
      .toEqual({ error: "Row 2 has no url, publisher." });
    expect(parseCuratedImport(JSON.stringify([row, 3]))).toEqual({ error: "Row 2 isn't a pack." });
  });

  it("says a 422 in the form's own words", () => {
    expect(validationText([{ loc: ["body", "url"], msg: "Value error, must be an https:// address" }]))
      .toBe("Page URL: must be an https:// address");
    expect(validationText([{ loc: ["body", "packs", 1, "license_id"], msg: "Value error, isn't a license Freesta.sh knows: '?'" }]))
      .toBe("Row 2, License: isn't a license Freesta.sh knows: '?'");
    expect(validationText("Admins only.")).toBeNull();
    expect([licenseLabel("CC0-1.0"), licenseLabel("CC-BY-SA-3.0")]).toEqual(["CC0 1.0", "CC-BY-SA-3.0"]);
  });
});
