import type { FeatureRecord, TemperatureRecord } from "../../../lib/analogue";

/** Histogram of the ordinary Earth windows' terrain index against the reference, with the selected site marked.
 *  It answers "is 98 special?" at a glance: when most bars sit near 100, a high index mostly means gentle land. */
export function OrdinaryHistogram({ scores, value, siteName, referenceName }: { scores: number[]; value: number; siteName: string; referenceName: string }) {
  const bins = 10;
  const counts = Array.from({ length: bins }, (_, i) => scores.filter((s) => (i === bins - 1 ? s >= i * 10 : s >= i * 10 && s < (i + 1) * 10)).length);
  const peak = Math.max(1, ...counts);
  const W = 560, H = 132, left = 8, right = 8, top = 22, bottom = 26;
  const bw = (W - left - right) / bins;
  const x = (v: number) => left + (Math.min(100, Math.max(0, v)) / 100) * (W - left - right);
  const y = (c: number) => top + (1 - c / peak) * (H - top - bottom);
  const mine = Math.min(bins - 1, Math.floor(value / 10));
  const above = scores.filter((s) => s >= value - 1e-9).length;
  return (
    <figure className="chart ordinary-chart" data-testid="ordinary-chart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Histogram of ${scores.length} ordinary Earth windows' terrain index against ${referenceName}. ${siteName} scores ${value.toFixed(0)}; ${above} ordinary windows score as high or higher.`}>
        {counts.map((c, i) => (
          <g key={i}>
            <rect x={left + i * bw + 2} y={y(c)} width={bw - 4} height={H - bottom - y(c)} className={i === mine ? "hist-bar is-mine" : "hist-bar"} />
            {c > 0 && <text x={left + i * bw + bw / 2} y={y(c) - 4} textAnchor="middle" className="chart-tick">{c}</text>}
          </g>
        ))}
        <line x1={x(value)} x2={x(value)} y1={top - 14} y2={H - bottom} className="hist-marker" />
        <text x={Math.min(W - right, Math.max(left + 40, x(value)))} y={top - 16} textAnchor={value > 80 ? "end" : "middle"} className="chart-label site">{siteName.split(" (")[0].split(",")[0]} · {value.toFixed(0)}</text>
        <line x1={left} x2={W - right} y1={H - bottom} y2={H - bottom} className="chart-axis" />
        {[0, 25, 50, 75, 100].map((t) => <text key={t} x={x(t)} y={H - 8} textAnchor={t === 0 ? "start" : t === 100 ? "end" : "middle"} className="chart-tick">{t}</text>)}
      </svg>
      <figcaption>Terrain similarity index of {scores.length} ordinary Earth land windows scored against {referenceName} the same way. Bar heights are window counts.</figcaption>
    </figure>
  );
}

const unitOf = (u: string) => (u === "degrees" ? "°" : " m");

/** One row per scored measurement: Earth and reference ranges on a shared axis, then the difference in plain words. */
export function MeasureRows({ features, siteName, referenceName, detailed }: { features: FeatureRecord[]; siteName: string; referenceName: string; detailed: boolean }) {
  const scored = features.filter((f) => f.role === "scored" && f.distance != null && f.earth && f.planet);
  return (
    <div className="measure-rows" data-testid="measure-rows">
      {scored.map((f) => {
        const u = unitOf(f.units);
        const isRel = f.feature === "relative_elevation";
        // Slope: median and 90th percentile. Relative elevation: its median is 0 by definition, so show the 90th percentile height.
        const e = f.earth!, p = f.planet!;
        const max = Math.max(e.p90 ?? 0, p.p90 ?? 0, 1) * 1.08;
        const pos = (v: number | null) => `${(100 * Math.max(0, v ?? 0)) / max}%`;
        const share = f.d_over_tau != null ? Math.round(100 * f.d_over_tau) : null;
        return (
          <div className="measure-row" key={f.feature}>
            <div className="measure-head">
              <strong>{isRel ? "Relief (relative elevation)" : "Slope"}</strong>
              <span className="muted">{isRel ? "how high the upper 10% of ground stands above the window’s middle" : "median steepness, and the steepest 10% of ground"}</span>
            </div>
            {[["earth", siteName, e] as const, ["ref", referenceName, p] as const].map(([k, name, w]) => (
              <div className={`measure-bar-row ${k}`} key={k}>
                <span className="measure-name">{name.split(" (")[0].split(",")[0]}</span>
                <span className="measure-track">
                  <span className="measure-span" style={{ left: isRel ? "0%" : pos(w.median), width: isRel ? pos(w.p90) : `calc(${pos(w.p90)} - ${pos(w.median)})` }} />
                  {!isRel && <span className="measure-dot" style={{ left: pos(w.median) }} />}
                </span>
                <span className="measure-val mono">{isRel ? `${(w.p90 ?? 0).toFixed(0)}${u}` : `${(w.median ?? 0).toFixed(1)}° · ${(w.p90 ?? 0).toFixed(1)}°`}</span>
              </div>
            ))}
            <p className="measure-diff">
              Whole distributions differ by <b className="mono">{f.distance!.toFixed(isRel ? 1 : 2)}{u}</b>
              {share != null && <> — {share}% of the typical difference between two ordinary Earth landscapes ({f.tau!.toFixed(isRel ? 0 : 1)}{u})</>}
              {f.resolvable === false && <>, inside the measurement floor</>}.
              {detailed && f.similarity != null && <span className="muted"> Similarity {f.similarity.toFixed(4)} × weight {f.weight.toFixed(2)} = {f.contribution?.toFixed(2)} points.</span>}
            </p>
          </div>
        );
      })}
    </div>
  );
}

/** Day and night surface temperature as a dumbbell per site, the reference highlighted. Context only. */
export function TemperatureChart({ rows, highlight, reference }: {
  rows: { id: string; name: string; rec: TemperatureRecord | null }[]; highlight: string; reference: { name: string; rec: TemperatureRecord | null } | null;
}) {
  const all = [...rows.filter((r) => r.rec), ...(reference?.rec ? [{ id: "__ref", name: reference.name, rec: reference.rec }] : [])];
  if (!all.length) return null;
  const vals = all.flatMap((r) => [r.rec!.day_c ?? 0, r.rec!.night_c ?? 0]);
  const lo = Math.floor(Math.min(...vals, 0) / 10) * 10 - 10, hi = Math.ceil(Math.max(...vals) / 10) * 10 + 10;
  const W = 560, left = 132, right = 14, rowH = 26, top = 8;
  const H = top + all.length * rowH + 26;
  const x = (v: number) => left + ((v - lo) / (hi - lo)) * (W - left - right);
  const ticks = Array.from({ length: Math.floor((hi - lo) / 20) + 1 }, (_, i) => lo + i * 20);
  return (
    <figure className="chart temp-chart" data-testid="temperature-chart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Median night and day surface temperature in degrees Celsius for ${all.length} sites`}>
        {ticks.map((t) => <g key={t}><line x1={x(t)} x2={x(t)} y1={top} y2={H - 22} className="chart-grid" /><text x={x(t)} y={H - 6} textAnchor="middle" className="chart-tick">{t}°</text></g>)}
        {all.map((r, i) => {
          const yy = top + i * rowH + rowH / 2;
          const cls = r.id === "__ref" ? "is-ref" : r.id === highlight ? "is-mine" : "";
          return (
            <g key={r.id} className={`temp-row ${cls}`}>
              <text x={left - 8} y={yy + 4} textAnchor="end" className="chart-label">{r.name.split(" (")[0].split(",")[0]}</text>
              <line x1={x(r.rec!.night_c ?? 0)} x2={x(r.rec!.day_c ?? 0)} y1={yy} y2={yy} className="temp-span" />
              <circle cx={x(r.rec!.night_c ?? 0)} cy={yy} r={4.5} className="temp-night" />
              <circle cx={x(r.rec!.day_c ?? 0)} cy={yy} r={4.5} className="temp-day" />
            </g>
          );
        })}
      </svg>
      <figcaption><span className="key key-night" /> night (≈ 01:30–02:30 local) <span className="key key-day" /> day (≈ 13:30–14:30 local), medians in °C. Earth: Aqua MODIS 1 km average over the window; Mars: MEDA beside the rover.</figcaption>
    </figure>
  );
}
