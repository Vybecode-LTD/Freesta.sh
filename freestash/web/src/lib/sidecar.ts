import type { Asset, LedgerEntry, Verdict } from "./types";

/**
 * The `.license.json` provenance file. Same format as the CLI (download.py) and the desktop app (Sidecar.cs),
 * so `freestash audit` reads all three. A browser can't hash a cross-origin file, so sha256 is null here.
 */
export function sidecarJson(asset: Asset, verdict: Verdict, fileUrl: string | null, retrievedAt: string, sha256?: string | null): string {
  const fileName = fileUrl ? decodeURIComponent(new URL(fileUrl).pathname.split("/").pop() || "file") : asset.title;
  return JSON.stringify({
    freestash_sidecar: 1,
    file: fileName,
    sha256: sha256 ?? null,
    retrieved_at: retrievedAt,
    source_url: fileUrl,
    landing_url: asset.landing_url ?? null,
    license: asset.license,
    trust: asset.trust,
    use_case: verdict.use_case,
    tier: verdict.tier,
    attribution: verdict.attribution ?? null,
    obligations: verdict.obligations,
    reasons: verdict.reasons,
    asset: { ...asset, renditions: asset.renditions.filter((r) => r.url === fileUrl) },
  }, null, 2);
}

export function sidecarName(fileUrl: string | null, title: string): string {
  const base = fileUrl ? decodeURIComponent(new URL(fileUrl).pathname.split("/").pop() || "") : "";
  return `${base || title.replace(/[^\w.-]+/g, "-").slice(0, 60)}.license.json`;
}

export function sidecarFromEntry(e: LedgerEntry): string | null {
  const asset = e.snapshot?.asset;
  const verdict = e.snapshot?.verdict;
  return asset && verdict ? sidecarJson(asset, verdict, e.file_url ?? null, e.retrieved_at, e.sha256) : null;
}
