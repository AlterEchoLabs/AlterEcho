"use client";

import { Fragment, useState } from "react";
import { apiV3 } from "../../lib/api";
import type { ProfileV3, ResultDetail, ToleranceRecord } from "../../lib/analogue";
import { pct } from "../../lib/format";
import { useKeyed } from "../../lib/hooks";
import FormulaList from "../components/FormulaList";

/* eslint-disable @typescript-eslint/no-explicit-any */
type Json = Record<string, any>;
const EXAMPLE_SITES = [["earth-hanksville-mdrs", "Hanksville (MDRS)"], ["earth-craters-of-the-moon", "Craters of the Moon"], ["earth-atacama-south", "Atacama south"], ["earth-ladakh", "Ladakh"]];
const unit = (u: string) => (u === "degrees" ? "°" : " m");

export default function MethodContent() {
  const method = useKeyed("method-v3", () => apiV3.method() as Promise<Json>);
  const [site, setSite] = useState("earth-hanksville-mdrs");
  const example = useKeyed(`ex|${site}`, () => apiV3.result(site, "terrain_analogy", "mars-jezero"));
  const thermal = useKeyed("thermal|earth-hanksville-mdrs", () => apiV3.result("earth-hanksville-mdrs", "mars_base_field_testing", "mars-jezero"));
  const m = method.data;
  const tol: ToleranceRecord[] = m?.tolerances ?? [];
  const cal: Json = m?.calibration ?? {};
  const dec: Json = m?.decomposition ?? {};
  const profiles: ProfileV3[] = m?.profiles ?? [];

  return (
    <article className="page page-wide">
      <h1>How every number is made</h1>
      <p className="intro">
        AlterEcho separates three things that are often blurred together: a <strong>measured analogy</strong> (how alike two windows are on comparable
        measurements), <strong>field-test suitability</strong> (whether a place is useful for a task, recorded as evidence and never scored), and
        <strong> evidence quality</strong> (coverage, resolution limits and sensitivity, shown as facts rather than a confidence number).
      </p>
      {method.error && <p className="error-inline" role="alert">Method data could not be loaded: {method.error}</p>}

      <h2>The question a result answers</h2>
      <p>{m?.comparison_definition ?? "Loading…"}</p>
      <dl className="definition-list">
        <dt>E · Earth AOI</dt><dd>A registered 10 km study window with an integrity-checked SRTMGL1.003 DEM.</dd>
        <dt>P · Reference AOI</dt><dd>The 10 km Jezero window (Mars 2020 CTX DEM, 20 m) or the limited lunar south-pole window (LOLA, 20 m).</dd>
        <dt>T · Task</dt><dd>One of five profiles below, each with its own planned evidence families and task-critical gates.</dd>
        <dt>H · Epoch</dt><dd>Present-day surface form. Jezero&apos;s ancient lake is a process in the past; today&apos;s DEM records its result, not the lake.</dd>
        <dt>V · Method</dt><dd className="mono">{m ? `${m.method_version} · ${m.terrain_method} · ${String(m.review_status).replaceAll("_", " ")}` : "…"}</dd>
      </dl>

      <h2>The formulas</h2>
      {m && <FormulaList formulas={m.formulas as Record<string, string>} />}
      <dl className="kv params">{m && Object.entries(m.parameters as Record<string, string>).map(([k, v]) => <Fragment key={k}><dt className="mono">{k}</dt><dd>{v}</dd></Fragment>)}</dl>
      <p className="muted small">{m?.notice}</p>

      <h2>Tolerances and the resolution floor</h2>
      <p>
        Each tolerance τ is the median Wasserstein distance between unselected pairs of Earth land windows ({cal.redundancy?.population_windows ?? "…"} windows),
        so a candidate that differs from the reference as much as a typical pair of real landscapes differ from each other gets s = 0.5. It is accepted only
        if it is at least {cal.rules?.noise_factor ?? 3}× the resolution floor δ, which combines moving the reference window 2 km and changing the DEM product.
        Neither value is fitted to expert labels, and the candidate windows were already known, so this is not a blind test.
      </p>
      <div className="table-scroll" tabIndex={0} role="region" aria-label="Scrollable data table">
        <table className="feature-table" data-testid="method-tolerances">
          <thead><tr><th scope="col">Feature</th><th scope="col">Role</th><th scope="col"><span className="g">τ</span> 60 / 120 / 240 m</th><th scope="col">Leave one tile out</th><th scope="col"><span className="g">δ</span> placement</th><th scope="col"><span className="g">δ</span> DEM</th><th scope="col"><span className="g">τ ≥ 3δ</span></th></tr></thead>
          <tbody>{tol.map((t) => (
            <tr key={t.feature} className={t.role === "diagnostic" ? "is-diagnostic" : ""}>
              <th scope="row">{t.feature.replaceAll("_", " ")}</th>
              <td>{t.role === "scored" ? "scored" : `diagnostic (redundant with ${t.redundant_with})`}</td>
              <td className="mono">{["60", "120", "240"].map((s) => t.tau_by_scale[s]?.toFixed(t.units === "degrees" ? 2 : 1)).join(" / ")}{unit(t.units)}</td>
              <td className="mono">{t.leave_one_tile_out[0].toFixed(1)}–{t.leave_one_tile_out[1].toFixed(1)}{unit(t.units)}</td>
              <td className="mono">{t.delta_placement.toFixed(2)}{unit(t.units)}</td><td className="mono">{t.delta_dem?.toFixed(2) ?? "—"}{unit(t.units)}</td>
              <td>{t.noise_condition_passed ? "yes" : "no"}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      <p className="muted small">Relative elevation passes the 3δ condition with little margin; if one source tile is left out its tolerance can fall below 3δ. Treat its similarity as the more fragile of the two.</p>

      <h2>Reference windows</h2>
      <p>Each reference is a 10 km window placed by a documented rule before its terrain was measured. Its own resolution floor comes from moving that window 2 km in four directions; a reference whose features change by more than a third of the tolerance under that move is shown with distances only.</p>
      <div className="table-scroll" tabIndex={0} role="region" aria-label="Scrollable data table">
        <table className="feature-table" data-testid="method-references">
          <thead><tr><th scope="col">Reference</th><th scope="col">Elevation product</th><th scope="col">Median slope (60 m)</th><th scope="col"><span className="g">δ</span> slope · relative elevation</th><th scope="col">Scored</th></tr></thead>
          <tbody>{(m?.references ?? []).map((r: Json) => (
            <tr key={r.id}>
              <th scope="row">{r.name}<span className="muted small"> · {r.region}</span></th>
              <td className="small">{r.dem.item ?? r.dem.product}{r.dem.intersection_error ? ` · stereo error ${r.dem.intersection_error.median_m} m` : ""}</td>
              <td className="mono">{r.slope_median_60m.toFixed(2)}°</td>
              <td className="mono">{r.resolution_floor.slope.combined.toFixed(2)}° · {r.resolution_floor.relative_elevation.combined.toFixed(1)} m</td>
              <td>{r.scorable ? "yes" : "distances only"}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>

      <h2>Is the index informative? Discrimination analysis</h2>
      <p>Each reference is compared with the same {m?.discrimination_population?.windows ?? "…"} unselected Earth windows. If many of them score highly, a high value for a candidate says little. The table shows how often that happens.</p>
      <div className="table-scroll" tabIndex={0} role="region" aria-label="Scrollable data table">
        <table className="feature-table" data-testid="method-discrimination">
          <thead><tr><th scope="col">Reference</th><th scope="col">Background median</th><th scope="col">Share ≥ 90</th><th scope="col">Share ≥ 99</th><th scope="col">Slope alone ≥ 90</th><th scope="col">Relative elevation alone ≥ 90</th></tr></thead>
          <tbody>{Object.entries((m?.discrimination ?? {}) as Record<string, Json>).filter(([, v]) => v.background?.count).map(([rid, v]) => (
            <tr key={rid}>
              <th scope="row">{(m?.references ?? []).find((r: Json) => r.id === rid)?.name ?? rid}</th>
              <td className="mono">{v.background.median?.toFixed?.(1) ?? "—"}</td>
              <td className="mono">{pct(v.background.share_at_or_above?.["90"])}</td>
              <td className="mono">{pct(v.background.share_at_or_above?.["99"])}</td>
              <td className="mono">{pct(v.single_feature?.slope?.["90"])}</td>
              <td className="mono">{pct(v.single_feature?.relative_elevation?.["90"])}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      <p>At a 60 m grid the index separates low-relief from rugged terrain, but about half of all unselected windows also score 90 or more against every Mars reference, so it does not order low-relief windows. Read each candidate&apos;s background share (the fraction of unselected windows scoring at least as high) next to its index. {m?.discrimination_population?.caveat}</p>

      <h2>Research methods paper</h2>
      <p>The Methods and Results sections for the research paper are generated from this implementation: <span className="mono">{m?.paper?.markdown}</span> (Markdown with LaTeX), <span className="mono">{m?.paper?.latex}</span> → <span className="mono">{m?.paper?.pdf}</span>, and <span className="mono">{m?.paper?.docx}</span> with native Word equations. The generator recomputes the worked example independently, and <span className="mono">{m?.paper?.test}</span> fails if any documented number no longer matches the backend.</p>

      <h2>Which features are scored</h2>
      <p>
        Slope, local relief and roughness rise and fall together across Earth windows, so scoring all three would count one property three times.
        Features whose medians correlate at Spearman |ρ| ≥ {cal.rules?.redundancy_rho ?? 0.95} are treated as one construct: only slope is scored from that group, and the
        other two are shown as diagnostics. Relative elevation behaves independently and is scored.
      </p>
      <ul className="small mono">{cal.redundancy && Object.entries(cal.redundancy.spearman_medians_60m as Record<string, number>).map(([k, v]) => <li key={k}>{k.replace("~", " ~ ").replaceAll("_", " ")}: ρ = {v}</li>)}</ul>

      <h2>Why the old scores clustered near 99.9</h2>
      <p>{dec.finding}</p>
      <div className="table-scroll" tabIndex={0} role="region" aria-label="Scrollable data table">
        <table className="feature-table" data-testid="decomposition">
          <caption className="sr-only">Index after each change, Jezero reference</caption>
          <thead><tr><th scope="col">Site</th>{(dec.steps ?? []).map((s: string, i: number) => <th key={s} scope="col">{i + 1}. {s}</th>)}</tr></thead>
          <tbody>{(dec.rows ?? []).map((r: Json) => (
            <tr key={r.site_id}><th scope="row">{r.site_name}</th>{r.steps.map((v: number, i: number) => <td key={i} className="mono">{v.toFixed(2)}</td>)}</tr>
          ))}</tbody>
        </table>
      </div>
      <p className="muted small">Each column changes one thing. The original Atacama window is shown for history; it is excluded from the current method because it contains an industrial complex.</p>

      <h2>Checks against synthetic and unselected terrain</h2>
      <ul>{cal.synthetic_negatives && Object.entries(cal.synthetic_negatives as Record<string, Json>).map(([k, v]) => (
        <li key={k}><strong>{k.replaceAll("_", " ")}</strong>: experimental terrain evidence index {v.index_vs_jezero ?? "—"} against the Jezero window{v.expectation ? `. ${v.expectation}.` : "."}</li>
      ))}</ul>
      {cal.base_rate && <p>Of {cal.base_rate.count} unselected Earth windows, {pct(cal.base_rate.share_at_or_above["90"])} score 90 or more and {pct(cal.base_rate.share_at_or_above["99"])} score 99 or more against Jezero (median {cal.base_rate.median_index}). Under terrain-v4.0, 44% scored 99 or more.</p>}

      <h2>What each task can conclude</h2>
      <div className="profile-cards">{profiles.map((p) => (
        <section key={p.id} className="profile-card" data-testid={`method-profile-${p.id}`}>
          <h3>{p.label}{p.rankable ? "" : " · never ranked on partial evidence"}</h3>
          <p>{p.question}</p>
          <p className="small"><strong>Planned weights:</strong> {Object.entries(p.weights).map(([k, v]) => `${k.replaceAll("_", " ")} ${pct(v)}`).join(" · ")}. <strong>Task-critical:</strong> {p.task_critical.map((d) => d.replaceAll("_", " ")).join(", ")}.</p>
          <p className="small">{p.scope_line}</p>
        </section>
      ))}</div>

      <h2>Worked example from stored data</h2>
      <div className="layer-switch" role="radiogroup" aria-label="Worked example site">
        {EXAMPLE_SITES.map(([id, label]) => <button key={id} type="button" role="radio" aria-checked={site === id} onClick={() => setSite(id)}>{label}</button>)}
      </div>
      {example.loading && <p className="muted">Loading stored measurements…</p>}
      {example.data && <Worked detail={example.data} />}

      <h2>Temperature comparability audit</h2>
      <p>MODIS land-surface temperature (1 km area mean, clear-sky 8-day composites) and Mars 2020 MEDA ground temperature (a few square metres beside the rover, all conditions) are both skin temperatures, but they fail spatial-support and sampling equivalence. Temperature is therefore shown as context and never enters an index.</p>
      {thermal.data && <ThermalChecks detail={thermal.data} />}

      <h2>Data exclusions</h2>
      <ul>{m && Object.entries(m.aoi_exclusions as Record<string, Json>).map(([k, v]) => <li key={k}><strong>{k}</strong>: {v.reason}</li>)}</ul>

      <h2>Historical methods</h2>
      <dl className="definition-list">{m && Object.entries(m.compatibility as Record<string, string>).map(([k, v]) => <Fragment key={k}><dt>{k}</dt><dd>{v}</dd></Fragment>)}</dl>
    </article>
  );
}

function Worked({ detail }: { detail: ResultDetail }) {
  const terrain = detail.candidate.families.find((f) => f.family === "terrain");
  const scored = terrain?.features.filter((f) => f.role === "scored") ?? [];
  return (
    <div className="worked" data-testid="worked-example">
      <ol className="worked-steps">
        {scored.map((f) => (
          <li key={f.feature}>
            <strong>{f.label}</strong>: W1 between the 500-point quantile functions of {detail.earth_window.name} and {detail.reference_window.name} is
            d = <span className="mono">{f.distance?.toFixed(3)}{unit(f.units)}</span>; τ = <span className="mono">{f.tau?.toFixed(2)}{unit(f.units)}</span>, so d/τ = <span className="mono">{f.d_over_tau?.toFixed(3) ?? "—"}</span> and
            s = exp(−ln 2 × {f.d_over_tau?.toFixed(3) ?? "—"}²) = <span className="mono">{f.similarity?.toFixed(4) ?? "—"}</span>. With a = {f.weight.toFixed(2)} it contributes <span className="mono">{f.contribution?.toFixed(2) ?? "—"}</span> points.
            {f.resolvable === false ? " The difference is within the resolution floor." : ""}
          </li>
        ))}
      </ol>
      <p>Observed terrain index = Σ points = <span className="mono">{detail.candidate.observed_index?.toFixed(2) ?? "not defined"}</span> (scenario range {detail.candidate.sensitivity?.index_range?.join("–") ?? "—"}).</p>
    </div>
  );
}

function ThermalChecks({ detail }: { detail: ResultDetail }) {
  const t = detail.candidate.families.find((f) => f.family === "temperature");
  const audit = (t?.context as Json | null)?.audit as Json | undefined;
  if (!audit) return <p className="muted">{t?.reason ?? "No thermal record."}</p>;
  return (
    <ul className="audit" data-testid="thermal-audit">
      {(audit.checks as Json[]).map((c) => <li key={c.check} className={c.passed ? "pass" : c.required ? "fail" : "note"}><strong>{c.check}</strong> — {c.passed ? "passed" : c.required ? "failed" : "not met"}. {c.detail}</li>)}
    </ul>
  );
}
