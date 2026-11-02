import { describe, expect, it } from "vitest";
import { sidecarFromEntry, sidecarJson, sidecarName } from "./sidecar";
import type { Asset, LedgerEntry, Verdict } from "./types";

const asset: Asset = {
  provider: "cleveland", source_id: "1930.851", title: "Lighthouse Village", media_type: "image",
  license: { id: "CC0-1.0", label: "CC0 1.0", url: "https://creativecommons.org/publicdomain/zero/1.0/" },
  trust: "institution", landing_url: "https://clevelandart.org/art/1930.851", renditions: [
    { url: "https://openaccess-cdn.clevelandart.org/1930.851/1930.851_web.jpg", label: "web" },
    { url: "https://openaccess-cdn.clevelandart.org/1930.851/1930.851_full.tif", label: "full" },
  ], tags: [], notes: [], tips: [], detail_required: false, extra: {},
  is_pack: false, item_count: null, formats: [], member_licenses: [], members_checked: null,
};
const verdict: Verdict = { use_case: "client", tier: "green", reasons: ["CC0"], obligations: [], attribution: "Lighthouse Village, CC0" };

describe("sidecar", () => {
  it("matches the CLI and desktop format (freestash_sidecar: 1) and keeps only the taken rendition", () => {
    const url = asset.renditions[0].url;
    const json = JSON.parse(sidecarJson(asset, verdict, url, "2026-10-31T12:00:00Z"));
    expect(Object.keys(json)).toEqual(["freestash_sidecar", "file", "sha256", "retrieved_at", "source_url", "landing_url",
      "license", "trust", "use_case", "tier", "attribution", "obligations", "reasons", "asset"]);
    expect(json).toMatchObject({ freestash_sidecar: 1, file: "1930.851_web.jpg", sha256: null, tier: "green", use_case: "client" });
    expect(json.asset.renditions).toHaveLength(1);
  });

  it("names the file after the download, or the title when there is no file", () => {
    expect(sidecarName(asset.renditions[0].url, "x")).toBe("1930.851_web.jpg.license.json");
    expect(sidecarName(null, "Lighthouse Village / 1929")).toBe("Lighthouse-Village-1929.license.json");
  });

  it("survives a file name with a stray % (one such URL used to break the whole Downloads page)", () => {
    const odd = "https://example.org/files/100%25%20cotton-100%.jpg";
    expect(sidecarName(odd, "x")).toBe("100%25%20cotton-100%.jpg.license.json");
    const entry = { file_url: odd, retrieved_at: "2026-11-01T00:00:00Z", sha256: null, snapshot: { asset, verdict } } as unknown as LedgerEntry;
    expect(JSON.parse(sidecarFromEntry(entry)!).file).toBe("100%25%20cotton-100%.jpg");
  });

  it("rebuilds a sidecar from a ledger entry's snapshot, and declines without one", () => {
    const entry = { id: "1", asset_uid: "cleveland:1930.851", provider: "cleveland", title: "t", license_id: "CC0-1.0",
      license_label: "CC0 1.0", trust: "institution", use_case: "client", tier: "green", retrieved_at: "2026-10-31T12:00:00Z",
      file_url: asset.renditions[0].url, sha256: "abc" } as LedgerEntry;
    expect(sidecarFromEntry(entry)).toBeNull();
    expect(JSON.parse(sidecarFromEntry({ ...entry, snapshot: { asset, verdict } })!).sha256).toBe("abc");
  });
});
