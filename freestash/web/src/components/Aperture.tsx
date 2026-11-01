import type { ProviderStatus } from "../lib/types";

/**
 * The signature element: one tick per source being searched, lit as each source reports (red if it failed),
 * with the count in the middle. The federated search, made visible. Desktop: Controls/ApertureRing.cs.
 */
export function Aperture({ total, reported, failed, size = 66, busy = false }: {
  total: number; reported: number; failed: number; size?: number; busy?: boolean;
}) {
  const n = Math.max(total, 1);
  const c = size / 2;
  const r1 = size * 0.33;
  const r2 = size * 0.44;
  const ticks = Array.from({ length: n }, (_, i) => {
    const a = (i / n) * Math.PI * 2 - Math.PI / 2;
    const state = total === 0 ? "idle" : i < reported - failed ? "lit" : i < reported ? "fail" : "wait";
    return (
      <line key={i} className={`ap-tick ${state}`} x1={c + Math.cos(a) * r1} y1={c + Math.sin(a) * r1}
            x2={c + Math.cos(a) * r2} y2={c + Math.sin(a) * r2} style={{ animationDelay: `${i * 70}ms` }} />
    );
  });
  return (
    <svg className={`aperture ${busy ? "busy" : ""}`} width={size} height={size} viewBox={`0 0 ${size} ${size}`}
         role="img" aria-label={total ? `${reported} of ${total} sources reported` : "Ready to search"}>
      <circle className="ap-ring" cx={c} cy={c} r={c - 1.5} />
      {ticks}
      {total ? (
        <text x={c} y={c} className="ap-count" textAnchor="middle" dominantBaseline="central">{String(reported).padStart(2, "0")}</text>
      ) : <circle className="ap-core" cx={c} cy={c} r={size * 0.045} />}
    </svg>
  );
}

/** One column per source: how long it took, relative to the slowest. Pending sources shimmer. */
export function SourceSpectrum({ statuses, pending }: { statuses: ProviderStatus[]; pending: string[] }) {
  const slowest = Math.max(1, ...statuses.map((s) => s.elapsed_ms));
  const cols = [
    ...statuses.map((s) => ({ id: s.provider, w: Math.max(0.06, s.elapsed_ms / slowest), state: s.ok ? "ok" : "err",
                              title: s.ok ? `${s.provider}: ${s.count} results in ${(s.elapsed_ms / 1000).toFixed(1)} s` : `${s.provider}: ${s.error ?? "failed"}` })),
    ...pending.map((id) => ({ id, w: 1, state: "wait", title: `${id}: waiting` })),
  ];
  if (!cols.length) return null;
  return (
    <div className="spectrum" role="list" aria-label="Sources">
      {cols.map((col) => (
        <div key={col.id} className={`spec ${col.state}`} role="listitem" title={col.title}>
          <i><b style={{ width: `${col.w * 100}%` }} /></i>
          <span>{col.id.replace("_", " ")}</span>
        </div>
      ))}
    </div>
  );
}
