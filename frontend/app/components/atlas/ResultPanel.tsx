"use client";

import Link from "next/link";
import { Fragment, useEffect, useId, useRef, useState } from "react";
import { apiV3, safeExternalUrl, type Site } from "../../../lib/api";
import { ROLE_TEXT, STATE_TEXT, STATUS_TEXT, type CandidateV3, type CompareMode, type CompareV3, type ContextV3, type DataRole, type DistributionPair, type FeatureRecord, type ResultDetail } from "../../../lib/analogue";
import { coords, num, pct } from "../../../lib/format";
import { useKeyed } from "../../../lib/hooks";
import FormulaList from "../FormulaList";
import TeX from "../TeX";
import { useDetailMode } from "../../../lib/detail";
import { MeasureRows, OrdinaryHistogram, TemperatureChart } from "./Charts";
import { StandingBar } from "./ResultsList";

const unitOf = (units: string) => (units === "degrees" ? "°" : " m");
const fmt = (v: number | null | undefined, units: string, digits?: number) => (v == null ? "—" : `${v.toFixed(digits ?? (units === "degrees" ? 2 : 1))}${unitOf(units)}`);

/** Quantile functions of the two windows; the shaded band between them has area W1. */
function QuantileChart({ pair, earthName, referenceName, feature }: { pair: DistributionPair; earthName: string; referenceName: string; feature?: FeatureRecord }) {
  const width = 320, height = 150, left = 42, right = 8, top = 10, bottom = 26;
  const values = [...pair.earth, ...pair.planet];
  let lo = Math.min(...values), hi = Math.max(...values);
  if (hi - lo < 1e-6) { lo -= 1; hi += 1; }
  const x = (u: number) => left + u * (width - left - right);
  const y = (v: number) => top + (1 - (v - lo) / (hi - lo)) * (height - top - bottom);
  const line = (vals: number[]) => vals.map((v, i) => `${i ? "L" : "M"}${x(pair.u[i]).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const band = `${line(pair.earth)} ${pair.planet.map((_, i) => pair.planet.length - 1 - i).map((i) => `L${x(pair.u[i]).toFixed(1)},${y(pair.planet[i]).toFixed(1)}`).join(" ")} Z`;
  const unit = unitOf(pair.units).trim();
  const label = feature?.label ?? pair.feature;
  return (
    <figure className="chart">
      <figcaption><strong>{label}</strong><span>{feature?.role === "scored" ? "scored" : "diagnostic, not counted"} · 60 m grid · shaded area (W₁){feature?.distance != null ? `: ${fmt(feature.distance, pair.units)}` : ""}</span></figcaption>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${label}: quantile functions of ${earthName} and ${referenceName}. Wasserstein distance ${feature?.distance ?? "not available"} ${unit}.`}>
        <line x1={left} x2={width - right} y1={height - bottom} y2={height - bottom} className="chart-axis" />
        <line x1={left} x2={left} y1={top} y2={height - bottom} className="chart-axis" />
        <path d={band} className="w1-band" />
        <path d={line(pair.planet)} className="q-line q-ref" />
        <path d={line(pair.earth)} className="q-line q-site" />
        <text x={left - 4} y={y(hi) + 4} textAnchor="end" className="chart-tick">{num(hi, "", hi > 100 ? 0 : 1)}</text>
        <text x={left - 4} y={y(lo)} textAnchor="end" className="chart-tick">{num(lo, "", Math.abs(lo) > 100 ? 0 : 1)}</text>
        <text x={left} y={height - 8} className="chart-tick">0</text>
        <text x={width - right} y={height - 8} textAnchor="end" className="chart-tick">1 (share of cells)</text>
        <text x={left + 6} y={top + 10} className="chart-label site">{earthName}</text>
        <text x={left + 6} y={top + 22} className="chart-label ref">{referenceName}</text>
        <text x={width - right} y={top + 10} textAnchor="end" className="chart-tick">{unit}</text>
      </svg>
    </figure>
  );
}

export function WhyThisData({ open, onClose, roleIds, profileId, siteName }: { open: boolean; onClose: () => void; roleIds: string[]; profileId: string; siteName: string }) {
  const ref = useRef<HTMLDialogElement | null>(null);
  const roles = useKeyed(open ? "roles" : null, () => apiV3.dataRoles());
  const titleId = useId();
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);
  const shown = (roles.data ?? []).filter((r) => roleIds.includes(r.id)).sort((a, b) => roleIds.indexOf(a.id) - roleIds.indexOf(b.id));
  return (
    <dialog ref={ref} className="why-dialog" aria-labelledby={titleId} onClose={onClose} onCancel={onClose} data-testid="why-dialog">
      <div className="why-head">
        <h2 id={titleId}>Why this data?</h2>
        <button type="button" className="icon-button" onClick={onClose} aria-label="Close">×</button>
      </div>
      <p className="muted">What each product measures, why it matters here, where it enters the calculation and what it cannot tell you about {siteName}.</p>
      {roles.loading && <p>Loading data roles…</p>}
      {roles.error && <p role="alert">Data roles could not be loaded: {roles.error}</p>}
      <div className="why-list">
        {shown.map((r) => <RoleCard key={r.id} role={r} profileId={profileId} />)}
      </div>
    </dialog>
  );
}

export function RoleCard({ role, profileId }: { role: DataRole; profileId?: string }) {
  const href = safeExternalUrl(role.source_url);
  const why = (profileId && role.why[profileId]) || role.why.terrain_analogy || Object.values(role.why)[0];
  return (
    <article className={`role-card role-${role.role}`} data-testid={`role-${role.id}`}>
      <header><h3>{role.label}</h3><span className={`role-badge role-badge-${role.role}`}>{ROLE_TEXT[role.role]}</span></header>
      <p className="role-product">{role.product}</p>
      <dl>
        <dt>Measures</dt><dd>{role.measures}</dd>
        <dt>Why here</dt><dd>{why}</dd>
        <dt>Resolution</dt><dd>native {role.native_resolution}; analysis {role.analysis_resolution}</dd>
        <dt>Dates</dt><dd>{role.dates}</dd>
        <dt>Footprint</dt><dd>{role.footprint}</dd>
        <dt>Used in</dt><dd>{role.used_in.join("; ")}</dd>
        <dt>Cannot establish</dt><dd>{role.cannot_establish.join("; ")}</dd>
      </dl>
      {href && <p className="small"><a href={href} target="_blank" rel="noreferrer noopener">Official source</a>{role.doi && <> · DOI {role.doi}</>}</p>}
    </article>
  );
}

function downloadJson(detail: ResultDetail, name: string) {
  const blob = new Blob([JSON.stringify(detail, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function FullEvidence({ detail, onBack }: { detail: ResultDetail; onBack?: () => void }) {
  const c = detail.candidate, comp = detail.comparison;
  const terrain = c.families.find((f) => f.family === "terrain");
  const featureBy = new Map((terrain?.features ?? []).map((f) => [f.feature, f]));
  const cal = detail.calibration as { synthetic_negatives?: Record<string, { index_vs_jezero: number | null; expectation?: string }>; rules?: Record<string, number> };
  const e = detail.earth_window, r = detail.reference_window;
  return (
    <div className="full-evidence-body">
      <section>
        <h3>Comparison definition</h3>
        <dl className="kv">
          <dt>Earth AOI (E)</dt><dd>{e.name} · {e.aoi_id} · centre {coords(e.center[1], e.center[0])} · {e.width_m / 1000} × {e.height_m / 1000} km</dd>
          <dt>Reference AOI (P)</dt><dd>{r.name} · {r.aoi_id} · centre {r.body === "moon" ? "90° S (polar stereographic)" : coords(r.center[1], r.center[0])} · {r.width_m / 1000} × {r.height_m / 1000} km</dd>
          <dt>Task (T)</dt><dd>{comp.profile.label}: {comp.profile.question}</dd>
          <dt>Epoch (H)</dt><dd>Present-day surface form from DEMs (SRTM February 2000; CTX stereo 2006 onward; LOLA 2009 onward). Not the ancient Jezero lake.</dd>
          <dt>Method (V)</dt><dd className="mono">{comp.method_version} · {comp.terrain_method}</dd>
          <dt>Profile state</dt><dd>{STATE_TEXT[c.state]} · {comp.profile_state_reason}</dd>
        </dl>
        <p className="muted small">{comp.comparison_definition}</p>
      </section>

      <section>
        <h3>Formulas and parameters</h3>
        <FormulaList tex={comp.formulas_tex ?? {}} />
        <dl className="kv params">{Object.entries(comp.parameters).map(([k, v]) => <Fragment key={k}><dt className="mono">{k}</dt><dd>{v}</dd></Fragment>)}</dl>
      </section>

      <section>
        <h3>Per-feature calculation (60 m grid)</h3>
        <div className="table-scroll" tabIndex={0} role="region" aria-label="Scrollable data table">
          <table className="feature-table calc-table" data-testid="calc-table">
            <caption className="sr-only">Distances, tolerances, similarities and contributions</caption>
            <thead><tr><th scope="col">Feature</th><th scope="col">Earth median · p90</th><th scope="col">Reference median · p90</th><th scope="col"><span className="g">d</span> (W1)</th><th scope="col"><span className="g">τ</span></th><th scope="col"><span className="g">d/τ</span></th><th scope="col"><span className="g">s</span></th><th scope="col"><span className="g">a</span></th><th scope="col">points</th><th scope="col"><span className="g">δ</span> floor</th></tr></thead>
            <tbody>
              {(terrain?.features ?? []).map((f) => (
                <tr key={f.feature} className={f.role === "diagnostic" ? "is-diagnostic" : ""}>
                  <th scope="row">{f.label}<span className="muted small">{f.role === "scored" ? "scored" : `diagnostic (same construct as ${f.redundant_with})`}</span></th>
                  <td className="mono">{fmt(f.earth?.median, f.units)} · {fmt(f.earth?.p90, f.units)}</td>
                  <td className="mono">{fmt(f.planet?.median, f.units)} · {fmt(f.planet?.p90, f.units)}</td>
                  <td className="mono">{fmt(f.distance, f.units, 3)}</td>
                  <td className="mono">{fmt(f.tau, f.units)}</td>
                  <td className="mono">{f.d_over_tau?.toFixed(3) ?? "—"}</td>
                  <td className="mono">{f.similarity?.toFixed(4) ?? "—"}</td>
                  <td className="mono">{f.role === "scored" ? f.weight.toFixed(2) : "0"}</td>
                  <td className="mono">{f.contribution?.toFixed(2) ?? "—"}</td>
                  <td className="mono">{fmt(f.delta, f.units)}{f.resolvable === false ? " ✓ within" : ""}</td>
                </tr>
              ))}
            </tbody>
            <tfoot><tr><th scope="row" colSpan={8}>Terrain score: sum of the points{c.observed_index != null ? ", which is the terrain similarity index" : ""}</th><td className="mono" colSpan={2}>{terrain?.score != null ? `${(terrain.score * 100).toFixed(2)}` : "not scored"}{c.observed_index != null ? ` → ${c.observed_index.toFixed(2)}` : ""}</td></tr></tfoot>
          </table>
        </div>
        <TeX tex={String.raw`s = \exp\!\left[-\ln 2\left(\tfrac{d}{\tau}\right)^{2}\right], \qquad \text{points} = 100\,a\,s`} />
        <p className="muted small">A difference at or below δ cannot be told from what moving the reference window 2 km, or changing the Earth elevation model, does on its own.</p>
      </section>

      <section>
        <h3>Distributions</h3>
        <div className="chart-grid">
          {detail.distributions.map((p) => <QuantileChart key={p.feature} pair={p} earthName={e.name} referenceName={r.name} feature={featureBy.get(p.feature)} />)}
        </div>
      </section>

      <section>
        <h3>Evidence families, weights and eligibility</h3>
        <div className="table-scroll" tabIndex={0} role="region" aria-label="Scrollable data table">
          <table className="feature-table" data-testid="family-table">
            <caption className="sr-only">Planned evidence families for this profile</caption>
            <thead><tr><th scope="col">Family</th><th scope="col">w (planned)</th><th scope="col">Eligible</th><th scope="col">Status</th><th scope="col">S</th><th scope="col">Reason</th></tr></thead>
            <tbody>{c.families.map((f) => (
              <tr key={f.family}>
                <th scope="row">{f.label}{f.task_critical && <span className="crit">task-critical</span>}</th>
                <td className="mono">{f.weight > 0 ? pct(f.weight) : "—"}</td>
                <td>{f.eligible ? "yes" : "no"}</td>
                <td><span className={`status status-${f.status}`}>{STATUS_TEXT[f.status]}</span></td>
                <td className="mono">{f.score != null ? f.score.toFixed(3) : "—"}</td>
                <td className="small">{f.reason}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
        <p><strong>Evidence coverage:</strong> {pct(c.evidence_coverage)} of the planned {comp.profile.label} weight. <strong>Critical gates:</strong> {Object.entries(c.critical_gates).map(([k, v]) => `${k.replaceAll("_", " ")} ${v ? "passed" : "missing"}`).join(" · ")}.</p>
      </section>

      <section>
        <h3>Masks and quality</h3>
        <dl className="kv">
          <dt>Earth DEM</dt><dd>{e.dem ? `${e.dem.product}.${e.dem.version} · ${e.dem.provider}${e.dem.doi ? ` · DOI ${e.dem.doi}` : ""}` : "—"}</dd>
          <dt>Earth source file</dt><dd className="mono break">{e.source_file} · SHA-256 {e.source_sha256}</dd>
          <dt>Built-up exclusion</dt><dd>{e.exclusion ? `${(e.exclusion as Record<string, string>).rule}; ${pct(e.excluded_fraction_60m ?? 0, 2)} of 60 m cells excluded` : "none applied"}</dd>
          <dt>Valid cells (60 m)</dt><dd>{e.coverage_60m ? Object.entries(e.coverage_60m).map(([k, v]) => `${k.replaceAll("_", " ")} ${pct(v, 1)}`).join(" · ") : "—"}</dd>
          <dt>Reference DEM</dt><dd>{r.dem ? `${r.dem.product} · ${r.dem.provider}` : "—"} · SHA-256 <span className="mono break">{r.source_sha256}</span></dd>
        </dl>
      </section>

      {c.sensitivity && (
        <section>
          <h3>Sensitivity</h3>
          <p className="muted small">{c.sensitivity.notice}</p>
          <div className="table-scroll" tabIndex={0} role="region" aria-label="Scrollable data table">
            <table className="feature-table" data-testid="sensitivity-table">
              <caption className="sr-only">Index under each scenario</caption>
              <thead><tr><th scope="col">Scenario</th><th scope="col">Index</th></tr></thead>
              <tbody>{c.sensitivity.scenarios.map((s) => <tr key={s.id}><th scope="row">{s.label}</th><td className="mono">{s.index?.toFixed(2) ?? "—"}</td></tr>)}</tbody>
            </table>
          </div>
          <p>Index range across scenarios: {c.sensitivity.index_range?.join("–")}. Sites whose ranges overlap are not put in order.</p>
        </section>
      )}

      <section>
        <h3>Tolerances and resolution floor</h3>
        <div className="table-scroll" tabIndex={0} role="region" aria-label="Scrollable data table">
          <table className="feature-table" data-testid="tolerance-table">
            <thead><tr><th scope="col">Feature</th><th scope="col"><span className="g">τ</span> (60 m)</th><th scope="col"><span className="g">τ</span> leave one tile out</th><th scope="col"><span className="g">δ</span> placement</th><th scope="col"><span className="g">δ</span> DEM</th><th scope="col"><span className="g">δ</span> combined</th><th scope="col"><span className="g">τ ≥ 3δ</span></th></tr></thead>
            <tbody>{comp.tolerances.map((t) => (
              <tr key={t.feature} className={t.role === "diagnostic" ? "is-diagnostic" : ""}>
                <th scope="row">{t.feature.replaceAll("_", " ")} {t.role === "diagnostic" && <span className="muted small">(diagnostic)</span>}</th>
                <td className="mono">{fmt(t.tau, t.units)}</td><td className="mono">{fmt(t.leave_one_tile_out[0], t.units)}–{fmt(t.leave_one_tile_out[1], t.units)}</td>
                <td className="mono">{fmt(t.delta_placement, t.units)}</td><td className="mono">{fmt(t.delta_dem, t.units)}</td><td className="mono">{fmt(t.delta, t.units)}</td>
                <td>{t.noise_condition_passed ? "yes" : "no"}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
        <p className="muted small">τ is the median W1 between all pairs of 88 unselected Earth land windows (Earth terrain contrast). δ for this reference combines moving the reference window 2 km and changing the Earth DEM product; a feature is scored only when τ ≥ 3δ. Neither is fitted to expert labels.</p>
        {cal.synthetic_negatives && (
          <p className="small"><strong>Synthetic checks against the Jezero window:</strong> {Object.entries(cal.synthetic_negatives).map(([k, v]) => `${k.replaceAll("_", " ")} ${v.index_vs_jezero ?? "—"}`).join(" · ")}. A gentle fractal surface with similar slope and relief distributions scores high, which shows that distributions ignore spatial arrangement.</p>
        )}
      </section>

      {comp.discrimination && (
        <section data-testid="discrimination">
          <h3>Discrimination checks</h3>
          <p>{comp.discrimination.interpretation}</p>
          {comp.discrimination.background && (
            <p className="small">Against {comp.reference_name}, {comp.discrimination.background.count} unselected Earth windows have a median index of {comp.discrimination.background.median_index.toFixed(1)};
              {" "}{pct(comp.discrimination.background.share_at_or_above["90"])} score 90 or more and {pct(comp.discrimination.background.share_at_or_above["99"])} score 99 or more.
              {c.background_share != null && <> {pct(c.background_share)} score at least as high as this window.</>}</p>
          )}
          <ul className="small">
            {Object.entries(comp.discrimination.single_feature).map(([f, v]) => <li key={f}>{f.replaceAll("_", " ")} alone: {pct(v["90"])} of background windows at 90 or more</li>)}
            {Object.entries(comp.discrimination.alternative_tolerances).map(([k, v]) => <li key={k}>{k === "phase5_tau" ? "an earlier version’s tolerances" : k === "tau_x0.5" ? "half the tolerances" : "double the tolerances"}: {pct(v["90"])} at 90 or more</li>)}
            {Object.entries(comp.discrimination.leave_one_region_out_tau).map(([f, r]) => <li key={f}>τ for {f.replaceAll("_", " ")} with one region left out: {r[0]}–{r[1]}{f === "slope" ? "°" : " m"}</li>)}
            {comp.discrimination.top_five_order_stable_across_regions != null && <li>Order of the five highest candidates {comp.discrimination.top_five_order_stable_across_regions ? "unchanged" : "changes"} when the tolerance is recomputed with each region left out</li>}
          </ul>
          {comp.discrimination.population && <p className="muted small">{comp.discrimination.population.caveat} {comp.discrimination.notice}</p>}
        </section>
      )}

      {c.literature_context && (
        <section className="literature">
          <h3>Literature context (not a measurement of this window)</h3>
          <p>{String(c.literature_context.summary ?? "")}</p>
          <p className="muted small">{c.literature_context.scope}</p>
          {c.literature_context.sources.length > 0 && <ul className="small">{c.literature_context.sources.map((s) => { const href = safeExternalUrl(s.url); return <li key={s.id}>{href ? <a href={href} target="_blank" rel="noreferrer noopener">{s.title}</a> : s.title}</li>; })}</ul>}
        </section>
      )}

      <section>
        <h3>Limitations</h3>
        <ul>
          <li>{comp.profile.scope_line}</li>
          {comp.profile.not_assessed.map((n) => <li key={n}>Not assessed: {n}.</li>)}
          {comp.physical_limits.map((n) => <li key={n}>{n}</li>)}
          <li>{comp.validation_status}</li>
        </ul>
      </section>

      <section>
        <h3>Sources and reproducibility</h3>
        <ul className="small">{detail.sources.map((s) => { const href = safeExternalUrl(s.url); return <li key={s.role}>{s.label}: {href ? <a href={href} target="_blank" rel="noreferrer noopener">{s.product}</a> : s.product}</li>; })}</ul>
        <dl className="kv small">{Object.entries(detail.reproducibility).map(([k, v]) => <Fragment key={k}><dt>{k.replaceAll("_", " ")}</dt><dd className="mono break">{Array.isArray(v) ? v.join(" · ") : v && typeof v === "object" ? Object.entries(v as Record<string, unknown>).map(([kk, vv]) => `${kk.replaceAll("_", " ")}: ${typeof vv === "object" ? JSON.stringify(vv) : String(vv)}`).join(" · ") : String(v)}</dd></Fragment>)}</dl>
      </section>
      {onBack && <button type="button" className="text-button back-simple" onClick={onBack}>Back to simple result</button>}
    </div>
  );
}

/** One plain sentence on why a site matched (or did not), from the measured distances as shares of the tolerance τ. */
function shortWhy(result: CandidateV3): string | null {
  const terrain = result.families.find((f) => f.family === "terrain");
  const slope = terrain?.features.find((f) => f.feature === "slope" && f.role === "scored")?.d_over_tau;
  const rel = terrain?.features.find((f) => f.feature === "relative_elevation" && f.role === "scored")?.d_over_tau;
  if (slope == null || rel == null) return null;
  const share = (x: number) => (x < 1 ? `${Math.round(100 * x)}%` : `${x.toFixed(1)}×`);
  const typical = "the typical difference between two ordinary Earth landscapes";
  if (slope < 1 && rel < 1) {
    return `Slope and relief differ by only ${share(slope)} and ${share(rel)} of ${typical}${result.resolution === "unresolved_from_reference" ? ", smaller than the measurement can resolve at a 60 m grid" : ""}.`;
  }
  if (slope >= 1 && rel >= 1) return `Slope differs by ${share(slope)} and relief by ${share(rel)} ${typical}.`;
  return `Slope differs by ${share(slope)} and relief by ${share(rel)} of ${typical}.`;
}

function TerrainCard({ site, comparison, result, detailed, actions }: {
  site: Site; comparison: CompareV3; result: CandidateV3; detailed: boolean; actions: React.ReactNode;
}) {
  const s = result.simple;
  const st = result.standing;
  const terrain = result.families.find((f) => f.family === "terrain");
  const range = result.sensitivity?.index_range;
  const ref = comparison.reference_name;
  if (result.state === "excluded") {
    return (
      <article className="result-card" data-testid="simple-result">
        <p className="kicker">Not scored</p>
        <p className="simple-conclusion" data-testid="simple-conclusion">{s.conclusion}</p>
        <p className="muted">{s.limitation}</p>
      </article>
    );
  }
  if (result.state === "not_measured") {
    return (
      <article className="result-card" data-testid="simple-result">
        <p className="kicker">Not measured yet</p>
        <p className="simple-conclusion" data-testid="simple-conclusion">This window lies outside SRTM elevation coverage (60° N to 56° S), so it has no terrain measurement to compare. It stays listed so its status is visible.</p>
      </article>
    );
  }
  const scored = st && result.observed_index != null && s.show_index;
  const why = scored ? shortWhy(result) : null;
  return (
    <article className={`result-card class-${result.terrain_class ?? "none"}`} data-testid="simple-result">
      <header className="card-head">
        {s.verdict ? <h3 className="verdict" data-testid="verdict">{s.verdict}</h3> : <h3 className="verdict">{comparison.reference_body === "moon" ? "Measured distances, no index" : "Terrain compared"}</h3>}
      </header>

      {scored && (
        <div className="score-block" data-testid="simple-index">
          <div className="score-main">
            <p className="score-label">Terrain similarity index</p>
            <p className="score-value mono"><b>{result.observed_index!.toFixed(0)}</b><span>/100</span></p>
            <p className="score-what">Present-day terrain shape at a 60&nbsp;m analysis grid</p>
            {detailed && range && <p className="score-range mono" data-testid="score-range">range {range[0].toFixed(0)}–{range[1].toFixed(0)} across {result.sensitivity?.scenarios.length ?? 0} checks</p>}
          </div>
          <div className="score-context" data-testid="standing">
            <p className="score-label">Compared with ordinary land</p>
            <p className="standing-line"><b className="mono">{st!.closer_than}</b> of {st!.of} ordinary Earth windows are less similar to {ref.split(" (")[0]}</p>
            <StandingBar closer={st!.closer_than} of={st!.of} wide />
            {s.class_label && <p className={`class-chip class-${result.terrain_class}`} data-testid="class-label">{s.class_label}</p>}
          </div>
        </div>
      )}

      {!scored && <p className="simple-conclusion" data-testid="simple-conclusion">{s.conclusion}</p>}
      <dl className="card-facts">
        {why && <div><dt>{result.terrain_class === "different" ? "Why it differs" : "Why it matched"}</dt><dd data-testid="why-short">{why}</dd></div>}
        <div><dt>Main limitation</dt><dd data-testid="main-limitation">{s.limitation}</dd></div>
      </dl>

      {detailed && scored && (
        <div className="card-detail" data-testid="card-detail">
          <p className="simple-conclusion" data-testid="simple-conclusion">{s.conclusion}</p>
          <p className="small muted" data-testid="coverage-text">{s.coverage_text} {s.validation_status}</p>
          {comparison.background_scores && comparison.background_scores.length > 0 && (
            <OrdinaryHistogram scores={comparison.background_scores} value={result.observed_index!} siteName={site.name} referenceName={ref} />
          )}
          {terrain && terrain.features.length > 0 && (
            <div className="why-match" data-testid="why-match">
              <h4 className="detail-title">Measured distributions</h4>
              <MeasureRows features={terrain.features} siteName={site.name} referenceName={ref} detailed={detailed} />
              {s.background_text && <p className="small" data-testid="background-text">{s.background_text}</p>}
            </div>
          )}
        </div>
      )}
      {actions}
    </article>
  );
}

function TemperatureCard({ site, context, detailed }: { site: Site; context: ContextV3; detailed: boolean }) {
  const row = context.temperature.sites.find((t) => t.site_id === site.id);
  const ref = context.temperature.reference;
  return (
    <article className="result-card" data-testid="simple-result">
      <header className="card-head">
        <p className="kicker">Surface temperature · measured, not scored</p>
        <h3 className="verdict">{row?.record ? `${site.name.split(" (")[0]}: about ${row.record.day_c?.toFixed(0)}°C by day and ${row.record.night_c?.toFixed(0)}°C at night` : `No temperature record for ${site.name}`}</h3>
      </header>
      <TemperatureChart rows={context.temperature.sites.map((t) => ({ id: t.site_id, name: t.site_name, rec: t.record }))} highlight={site.id}
        reference={ref ? { name: context.reference_name, rec: ref } : null} />
      <p className="simple-conclusion" data-testid="simple-conclusion">{context.temperature.note}{ref && row?.record ? ` ${context.reference_name} is about ${(row.record.day_c! - ref.day_c!).toFixed(0)}°C colder by day and ${(row.record.night_c! - ref.night_c!).toFixed(0)}°C colder at night than this window, but the two numbers are not measured the same way.` : ""}</p>
      {row?.audit && (
        <details className="why-match" open={detailed}>
          <summary>Why temperature is not scored</summary>
          <ul className="audit">{row.audit.checks.map((c) => <li key={c.check} className={c.passed ? "pass" : c.required ? "fail" : "note"}><span className="audit-mark" aria-hidden="true">{c.passed ? "✓" : c.required ? "✕" : "–"}</span><span><strong>{c.check}</strong> — {c.passed ? "passed" : c.required ? "failed" : "not met"}. {c.detail}</span></li>)}</ul>
        </details>
      )}
      {row?.record && <p className="small muted">Earth: {row.record.product_id} ({row.record.instrument}, {row.record.platform}){detailed ? `, ${row.record.period?.slice(0, 10)} to ${row.record.period?.slice(21, 31)}, ${row.record.paired_samples} paired 8-day composites` : ""}.{ref ? ` Reference: ${ref.instrument}, ${ref.platform}.` : ""}</p>}
    </article>
  );
}

function FieldworkCard({ site, context }: { site: Site; context: ContextV3 }) {
  const f = context.fieldwork.sites.find((x) => x.site_id === site.id);
  return (
    <article className="result-card" data-testid="simple-result">
      <header className="card-head">
        <p className="kicker">Field-test record · documented research, not scored</p>
        <h3 className="verdict">{f ? f.analog_status_text : "No record"}</h3>
      </header>
      <p className="simple-conclusion" data-testid="simple-conclusion">{f?.summary ?? "This window has no recorded analog study."}</p>
      {f && f.sources.length > 0 && (
        <ul className="source-list">{f.sources.map((c) => { const href = safeExternalUrl(c.url); return <li key={c.id}>{href ? <a href={href} target="_blank" rel="noreferrer noopener">{c.title}</a> : c.title}</li>; })}</ul>
      )}
      <p className="small muted">This record does not change the terrain result. Being a well-known analog site does not mean the terrain matches a given Mars window, and the reverse. Use “Terrain shape” for the measured comparison.</p>
    </article>
  );
}

/** The selected site's answer. Simple: verdict, one index with its context, why, and the main limitation. Detailed adds ranges, distributions and exports. */
export default function ResultPanel({ site, comparison, context, mode, result, onDetailed }: {
  site: Site; comparison: CompareV3 | null; context: ContextV3 | null; mode: CompareMode; result: CandidateV3 | null; onDetailed: () => void;
}) {
  const [why, setWhy] = useState(false);
  const [detail] = useDetailMode();
  const detailed = detail === "detailed";
  const profileId = "terrain_analogy" as const;
  const referenceId = comparison?.reference_site_id ?? "mars-jezero";

  if (mode !== "terrain") {
    if (!context) return <div className="viewer-placeholder card-placeholder" data-testid="simple-result">Loading measured context…</div>;
    return <section className="result-panel" aria-label={`Result for ${site.name}`}>{mode === "temperature" ? <TemperatureCard site={site} context={context} detailed={detailed} /> : <FieldworkCard site={site} context={context} />}</section>;
  }
  if (!comparison) return <div className="viewer-placeholder card-placeholder" data-testid="simple-result">Calculating comparison…</div>;
  if (!result) return <div className="viewer-placeholder card-placeholder" data-testid="simple-result">No result for this site.</div>;
  const reportHref = `/report?site=${encodeURIComponent(site.id)}&profile=${profileId}&reference=${encodeURIComponent(referenceId)}`;
  const jsonName = `alterecho-${site.id}-${referenceId}.json`;
  const canDetail = result.state !== "not_measured" && result.state !== "excluded";
  const actions = canDetail ? (
    <div className="simple-actions">
      {!detailed && <button type="button" className="primary-button" onClick={onDetailed} data-testid="toggle-full">Show the full calculation</button>}
      <button type="button" className="text-button" onClick={() => setWhy(true)} data-testid="why-data">Why this data?</button>
      {detailed && <Link className="text-button" href={reportHref} prefetch={false}>Printable report</Link>}
      {detailed && (
        <button type="button" className="text-button" data-testid="download-json"
          onClick={() => apiV3.result(site.id, profileId, referenceId).then((d) => downloadJson(d, jsonName)).catch(() => undefined)}>Download JSON</button>
      )}
    </div>
  ) : null;

  return (
    <section className="result-panel" aria-label={`Result for ${site.name}`}>
      <TerrainCard site={site} comparison={comparison} result={result} detailed={detailed} actions={actions} />
      <WhyThisData open={why} onClose={() => setWhy(false)} roleIds={result.data_roles} profileId={profileId} siteName={site.name} />
    </section>
  );
}

/** Detailed mode only: every formula, table, range, mask, checksum and source behind the selected result. */
export function FullCalculation({ site, comparison, result, onHide }: { site: Site; comparison: CompareV3; result: CandidateV3; onHide: () => void }) {
  const titleId = useId();
  const profileId = "terrain_analogy" as const;
  const referenceId = comparison.reference_site_id;
  const show = result.state !== "not_measured" && result.state !== "excluded";
  const detailData = useKeyed(show ? `${site.id}|${profileId}|${referenceId}` : null, () => apiV3.result(site.id, profileId, referenceId));
  if (!show) return null;
  return (
    <section className="full-evidence is-open" data-testid="full-evidence" aria-labelledby={titleId}>
      <div className="full-head">
        <h3 id={titleId}>The full calculation</h3>
        <button type="button" className="text-button" onClick={onHide} data-testid="hide-full">Hide the calculation</button>
      </div>
      {detailData.loading && <div className="viewer-placeholder">Loading measurements…</div>}
      {detailData.error && <p role="alert">The calculation could not be loaded: {detailData.error}</p>}
      {detailData.data && <FullEvidence detail={detailData.data} />}
    </section>
  );
}
