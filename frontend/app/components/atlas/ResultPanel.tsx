"use client";

import Link from "next/link";
import { Fragment, useEffect, useId, useRef, useState } from "react";
import { apiV3, safeExternalUrl, type Site } from "../../../lib/api";
import { ROLE_TEXT, STATE_TEXT, STATUS_TEXT, type CandidateV3, type CompareV3, type DataRole, type DistributionPair, type FeatureRecord, type ResultDetail, type ViewMode } from "../../../lib/analogue";
import { coords, num, pct } from "../../../lib/format";
import { useKeyed } from "../../../lib/hooks";

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
      <figcaption><strong>{label}</strong><span>{feature?.role === "scored" ? "scored" : "diagnostic"} · 60 m grid · W1 = shaded area{feature?.distance != null ? ` = ${fmt(feature.distance, pair.units)}` : ""}</span></figcaption>
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
        <ul className="formula-list">{Object.entries(comp.formulas).map(([k, v]) => <li key={k}><span className="muted">{k.replaceAll("_", " ")}</span><code>{v}</code></li>)}</ul>
        <dl className="kv params">{Object.entries(comp.parameters).map(([k, v]) => <Fragment key={k}><dt className="mono">{k}</dt><dd>{v}</dd></Fragment>)}</dl>
      </section>

      <section>
        <h3>Per-feature calculation (60 m grid)</h3>
        <div className="table-scroll">
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
            <tfoot><tr><th scope="row" colSpan={8}>Terrain family score S = Σ a·s{c.observed_index != null ? " → observed index" : ""}</th><td className="mono" colSpan={2}>{terrain?.score != null ? `${(terrain.score * 100).toFixed(2)}` : "not scored"}{c.observed_index != null ? ` → ${c.observed_index.toFixed(2)}` : ""}</td></tr></tfoot>
          </table>
        </div>
        <p className="muted small">s = exp(−ln 2 · (d/τ)²). Points = 100 × a × s. A difference at or below δ cannot be separated from re-placing the reference window by 2 km or changing the DEM product.</p>
      </section>

      <section>
        <h3>Distributions</h3>
        <div className="chart-grid">
          {detail.distributions.map((p) => <QuantileChart key={p.feature} pair={p} earthName={e.name} referenceName={r.name} feature={featureBy.get(p.feature)} />)}
        </div>
      </section>

      <section>
        <h3>Evidence families, weights and eligibility</h3>
        <div className="table-scroll">
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
          <div className="table-scroll">
            <table className="feature-table" data-testid="sensitivity-table">
              <caption className="sr-only">Index and rank under each scenario</caption>
              <thead><tr><th scope="col">Scenario</th><th scope="col">Index</th><th scope="col">Rank</th></tr></thead>
              <tbody>{c.sensitivity.scenarios.map((s) => <tr key={s.id}><th scope="row">{s.label}</th><td className="mono">{s.index?.toFixed(2) ?? "—"}</td><td className="mono">{s.rank ?? "—"}</td></tr>)}</tbody>
            </table>
          </div>
          <p>Range {c.sensitivity.index_range?.join("–")} · rank range {c.sensitivity.rank_range?.join("–") ?? "—"}{c.sensitivity.tie_group ? ` · tie group ${c.sensitivity.tie_group}` : ""}.</p>
        </section>
      )}

      <section>
        <h3>Tolerances and resolution floor</h3>
        <div className="table-scroll">
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
            {Object.entries(comp.discrimination.alternative_tolerances).map(([k, v]) => <li key={k}>{k === "phase5_tau" ? "Phase 5 tolerances" : k === "tau_x0.5" ? "half the tolerances" : "double the tolerances"}: {pct(v["90"])} at 90 or more</li>)}
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
        <dl className="kv small">{Object.entries(detail.reproducibility).map(([k, v]) => <Fragment key={k}><dt>{k.replaceAll("_", " ")}</dt><dd className="mono break">{Array.isArray(v) ? v.join(" · ") : String(v)}</dd></Fragment>)}</dl>
      </section>
      {onBack && <button type="button" className="text-button back-simple" onClick={onBack}>Back to simple result</button>}
    </div>
  );
}

export default function ResultPanel({ site, reference, comparison, result, view, onView }: {
  site: Site; reference: Site | null; comparison: CompareV3 | null; result: CandidateV3 | null; view: ViewMode; onView: (view: ViewMode) => void;
}) {
  const [why, setWhy] = useState(false);
  const fullId = useId();
  const profileId = comparison?.profile.id ?? "terrain_analogy";
  const referenceId = comparison?.reference_site_id ?? reference?.id ?? "mars-jezero";
  const wantDetail = view === "full" && result && (result.state !== "not_measured");
  const detail = useKeyed(wantDetail ? `${site.id}|${profileId}|${referenceId}` : null, () => apiV3.result(site.id, profileId, referenceId));
  const fullRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => { if (view === "full" && detail.data) fullRef.current?.focus({ preventScroll: true }); }, [view, detail.data]);

  if (!comparison) return <div className="viewer-placeholder" data-testid="simple-result">Calculating comparison…</div>;
  if (!result) return <div className="viewer-placeholder" data-testid="simple-result">No result for this site under {comparison.profile.label}.</div>;
  const s = result.simple;
  const range = result.sensitivity?.index_range;
  const groupSize = comparison.tie_groups.find((g) => g.includes(result.site_id))?.length ?? 1;
  const reportHref = `/report?site=${encodeURIComponent(site.id)}&profile=${profileId}&reference=${encodeURIComponent(referenceId)}`;
  const jsonName = `terraluna-${site.id}-${profileId}-${referenceId}.json`;

  return (
    <section className="result-panel" aria-label={`Result for ${site.name}`}>
      <article className={`simple-result state-${result.state}`} data-testid="simple-result">
        <header className="simple-head">
          <p className="kicker">{comparison.profile.label} · {STATE_TEXT[result.state]}{result.rank != null ? ` · rank ${result.rank}${groupSize > 1 ? "= (tie group)" : ""}` : ""}</p>
          <h3><span className="muted">Compared with</span> {comparison.reference_name}</h3>
        </header>
        <p className="simple-conclusion" data-testid="simple-conclusion">{s.conclusion}</p>
        {s.show_index && result.observed_index != null && (
          <p className="simple-index" data-testid="simple-index">
            <span className="mono">{result.observed_index.toFixed(1)}</span>
            <span>{s.index_label}{range ? ` · scenario range ${range[0].toFixed(0)}–${range[1].toFixed(0)}` : ""}{groupSize > 1 ? " · order within the tie group not resolved" : ""}</span>
          </p>
        )}
        <dl className="simple-facts">
          <div><dt>Measured</dt><dd>{s.measured.length ? s.measured.join(", ") : "Nothing comparable yet"}</dd></div>
          <div><dt>Evidence coverage</dt><dd><span className="coverage-track wide"><span style={{ width: pct(result.evidence_coverage) }} /></span>{s.coverage_text}</dd></div>
          {s.strength && <div><dt>Main strength</dt><dd>{s.strength}</dd></div>}
          {s.mismatch && <div><dt>Main mismatch</dt><dd>{s.mismatch}</dd></div>}
          {s.background_text && <div className="wide"><dt>Background check</dt><dd data-testid="background-text">{s.background_text}</dd></div>}
          <div className="wide"><dt>Important limitation</dt><dd>{s.limitation}</dd></div>
          <div className="wide"><dt>Validation status</dt><dd>{s.validation_status}</dd></div>
        </dl>
        <div className="simple-actions">
          <button type="button" className="primary-button" aria-expanded={view === "full"} aria-controls={fullId} onClick={() => onView(view === "full" ? "simple" : "full")} data-testid="toggle-full">
            {view === "full" ? "Hide full evidence" : "Full evidence and calculations"}
          </button>
          <button type="button" className="text-button" onClick={() => setWhy(true)} data-testid="why-data">Why this data?</button>
          <Link className="text-button" href={reportHref} prefetch={false}>Printable report</Link>
          {result.state !== "not_measured" && (
            <button type="button" className="text-button" data-testid="download-json"
              onClick={() => apiV3.result(site.id, profileId, referenceId).then((d) => downloadJson(d, jsonName)).catch(() => undefined)}>Download JSON</button>
          )}
        </div>
      </article>

      <div id={fullId} className={`full-evidence ${view === "full" ? "is-open" : ""}`} data-testid="full-evidence" hidden={view !== "full"} ref={fullRef} tabIndex={-1} aria-label="Full evidence and calculations">
        {view === "full" && (
          <>
            <div className="full-head">
              <h3>Full evidence and calculations</h3>
              <button type="button" className="text-button" onClick={() => onView("simple")}>Back to simple result</button>
            </div>
            {detail.loading && <div className="viewer-placeholder">Loading measurements…</div>}
            {detail.error && <p role="alert">Full evidence could not be loaded: {detail.error}</p>}
            {result.state === "not_measured" && <p>This site has no processed study window, so there are no calculations to show.</p>}
            {detail.data && <FullEvidence detail={detail.data} onBack={() => onView("simple")} />}
          </>
        )}
      </div>
      <WhyThisData open={why} onClose={() => setWhy(false)} roleIds={result.data_roles} profileId={profileId} siteName={site.name} />
    </section>
  );
}
