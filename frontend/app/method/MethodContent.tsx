"use client";

import { Fragment, useState } from "react";
import { apiV3 } from "../../lib/api";
import type { ProfileV3, ResultDetail, ToleranceRecord } from "../../lib/analogue";
import { pct } from "../../lib/format";
import { useKeyed } from "../../lib/hooks";
import FormulaList from "../components/FormulaList";
import TeX from "../components/TeX";

/* eslint-disable @typescript-eslint/no-explicit-any */
type Json = Record<string, any>;
const EXAMPLE_SITES = [["earth-atacama-south", "Atacama Desert"], ["earth-craters-of-the-moon", "Craters of the Moon"], ["earth-hanksville-mdrs", "Hanksville (MDRS)"], ["earth-ladakh", "Ladakh (contrast)"]];
const unit = (u: string) => (u === "degrees" ? "°" : " m");
const texUnit = (u: string) => (u === "degrees" ? "^{\\circ}" : "\\,\\text{m}");

export default function MethodContent() {
  const method = useKeyed("method-v3", () => apiV3.method() as Promise<Json>);
  const [site, setSite] = useState("earth-atacama-south");
  const example = useKeyed(`ex|${site}`, () => apiV3.result(site, "terrain_analogy", "mars-jezero"));
  const thermal = useKeyed("thermal|earth-hanksville-mdrs", () => apiV3.result("earth-hanksville-mdrs", "mars_base_field_testing", "mars-jezero"));
  const m = method.data;
  const tex: Record<string, string> = m?.formulas_tex ?? {};
  const tol: ToleranceRecord[] = m?.tolerances ?? [];
  const cal: Json = m?.calibration ?? {};
  const dec: Json = m?.decomposition ?? {};
  const profiles: ProfileV3[] = m?.profiles ?? [];

  return (
    <article className="page page-wide method-page">
      <h1>How every number is made</h1>
      <p className="intro">
        AlterEcho answers one narrow question: how alike is the ground in two 10 km windows, one on Earth and one on Mars or the Moon, using
        measurements that mean the same thing on both? This page shows each step with the formula that runs, the symbols and units, and a worked example
        taken from the live calculation.
      </p>
      {method.error && <p className="error-inline" role="alert">Method data could not be loaded: {method.error}</p>}

      <ol className="method-steps" aria-label="The method in four steps">
        <li><strong>Measure the ground</strong><span>Slope and relative elevation on every 60 m cell of both windows, from real elevation models.</span></li>
        <li><strong>Compare whole distributions</strong><span>Not just averages: the Wasserstein distance measures how far apart the two sets of values are.</span></li>
        <li><strong>Turn distance into similarity</strong><span>A tolerance taken from ordinary Earth terrain says how big a difference is.</span></li>
        <li><strong>Check it against ordinary land</strong><span>The same score for 88 ordinary Earth windows shows whether a high number is special.</span></li>
      </ol>

      <section className="step-section">
        <h2>1 · Two windows and one question</h2>
        <p>{m?.comparison_definition ?? "Loading…"}</p>
        <dl className="definition-list">
          <dt>E · Earth window</dt><dd>A registered 10 km window with an integrity-checked NASA SRTMGL1.003 elevation model (about 30 m posting).</dd>
          <dt>P · Reference window</dt><dd>One of five Mars windows (Jezero, Gale, InSight, Gusev, Eberswalde; USGS CTX stereo elevation, 20 m) or the lunar south-pole window (LRO LOLA, 20 m).</dd>
          <dt>T · Comparison</dt><dd>Terrain shape. Temperature and field-test records are shown beside it but are not scored.</dd>
          <dt>H · Epoch</dt><dd>The present-day surface. Jezero’s ancient lake is a past process; today’s elevation model records its result, not the lake.</dd>
          <dt>V · Method</dt><dd className="mono">{m ? `${m.method_version} · ${m.terrain_method} · ${String(m.review_status).replaceAll("_", " ")}` : "…"}</dd>
        </dl>
      </section>

      <section className="step-section">
        <h2>2 · Measuring the ground</h2>
        <p>Both windows are resampled onto the same 60 m grid, with a 1.2 km margin so edge cells have full neighbourhoods. Two quantities are scored:</p>
        <FormulaList tex={tex} only={["slope", "relative_elevation"]} />
        <p>
          Here <TeX block={false} tex="z" /> is elevation in metres and <TeX block={false} tex="x,\,y" /> are ground distances in metres. Relative elevation removes the
          vertical datum, which differs between Earth, Mars and the Moon. Local relief and roughness are measured too, but they rise and fall with slope
          (Spearman <TeX block={false} tex="\rho \ge 0.95" />), so scoring them would count one property three times; they are shown as diagnostics only.
        </p>
        <ul className="small mono">{cal.redundancy && Object.entries(cal.redundancy.spearman_medians_60m as Record<string, number>).map(([k, v]) => <li key={k}>{k.replace("~", " ~ ").replaceAll("_", " ")}: ρ = {v}</li>)}</ul>
      </section>

      <section className="step-section">
        <h2>3 · Comparing whole distributions</h2>
        <FormulaList tex={tex} only={["distribution_distance"]} />
        <p>
          <TeX block={false} tex="F" /> is the share of cells at or below a value, <TeX block={false} tex="Q" /> its inverse (the quantile function), and the distance is in
          the feature’s own units: degrees for slope, metres for relief. Two windows with the same shape of distribution shifted by one degree are one degree apart.
          A distribution does not record where ridges, channels or craters are, so two windows with very different landforms can still look alike here.
        </p>
      </section>

      <section className="step-section">
        <h2>4 · From distance to similarity</h2>
        <FormulaList tex={tex} only={["feature_similarity", "tolerance", "resolution_floor"]} />
        <p>
          The tolerance <TeX block={false} tex="\tau" /> is the median distance between pairs of {cal.redundancy?.population_windows ?? 88} ordinary Earth land windows, so a
          site that differs from the reference as much as two typical landscapes differ from each other gets <TeX block={false} tex="s = 0.5" />. It is a project definition,
          not fitted to expert labels, and it is accepted only when it is at least three times the resolution floor <TeX block={false} tex="\delta" />.
        </p>
        <div className="table-scroll" tabIndex={0} role="region" aria-label="Tolerances and resolution floors">
          <table className="feature-table" data-testid="method-tolerances">
            <thead><tr><th scope="col">Feature</th><th scope="col">Role</th><th scope="col">τ at 60 / 120 / 240 m</th><th scope="col">τ, one tile left out</th><th scope="col">δ placement</th><th scope="col">δ elevation model</th><th scope="col">τ ≥ 3δ</th></tr></thead>
            <tbody>{tol.map((t) => (
              <tr key={t.feature} className={t.role === "diagnostic" ? "is-diagnostic" : ""}>
                <th scope="row">{t.feature.replaceAll("_", " ")}</th>
                <td>{t.role === "scored" ? "scored" : `diagnostic (moves with ${t.redundant_with})`}</td>
                <td className="mono">{["60", "120", "240"].map((s) => t.tau_by_scale[s]?.toFixed(t.units === "degrees" ? 2 : 1)).join(" / ")}{unit(t.units)}</td>
                <td className="mono">{t.leave_one_tile_out[0].toFixed(1)}–{t.leave_one_tile_out[1].toFixed(1)}{unit(t.units)}</td>
                <td className="mono">{t.delta_placement.toFixed(2)}{unit(t.units)}</td><td className="mono">{t.delta_dem?.toFixed(2) ?? "—"}{unit(t.units)}</td>
                <td>{t.noise_condition_passed ? "yes" : "no"}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      </section>

      <section className="step-section">
        <h2>5 · Combining the features</h2>
        <FormulaList tex={tex} only={["family_score", "observed_index", "evidence_coverage"]} />
        <p>
          Slope and relative elevation each carry weight <TeX block={false} tex="a = \tfrac12" />. For terrain the index is simply 100 × the terrain score, and coverage
          {" "}<TeX block={false} tex="C = 1" /> means all of the planned terrain evidence was measured; it says nothing about geology, temperature or safety. Missing evidence is
          left out of both sums and never counted as zero.
        </p>
      </section>

      <section className="step-section">
        <h2>6 · Checking the score against ordinary land</h2>
        <FormulaList tex={tex} only={["standing"]} />
        <p>
          <TeX block={false} tex="\mathcal{B}" /> is the set of {m?.discrimination_population?.windows ?? 88} ordinary Earth windows, <TeX block={false} tex="A_b" /> their index against the
          same reference and <TeX block={false} tex="A_c" /> the candidate’s. If many ordinary windows score highly, a high index says little; the table shows how often that happens.
          This is why the atlas shows “beats N of 88” beside every index, and the verdict reads the count in quarters: three quarters or more is “closer than most ordinary land”.
        </p>
        <div className="table-scroll" tabIndex={0} role="region" aria-label="Scores of ordinary windows">
          <table className="feature-table" data-testid="method-discrimination">
            <thead><tr><th scope="col">Reference</th><th scope="col">Median ordinary window</th><th scope="col">Ordinary windows at 90 or more</th><th scope="col">at 99 or more</th><th scope="col">Slope alone, 90+</th><th scope="col">Relief alone, 90+</th></tr></thead>
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
        <p className="muted small">{m?.discrimination_population?.caveat}</p>
        <h3>Synthetic checks</h3>
        <ul>{cal.synthetic_negatives && Object.entries(cal.synthetic_negatives as Record<string, Json>).map(([k, v]) => (
          <li key={k}><strong>{k.replaceAll("_", " ")}</strong>: index {v.index_vs_jezero ?? "—"} against Jezero{v.expectation ? `. ${v.expectation}.` : "."}</li>
        ))}</ul>
      </section>

      <section className="step-section">
        <h2>Worked example from stored data</h2>
        <p>Every number below is read from the live calculation for the chosen site against Jezero.</p>
        <div className="layer-switch" role="radiogroup" aria-label="Worked example site">
          {EXAMPLE_SITES.map(([id, label]) => <button key={id} type="button" role="radio" aria-checked={site === id} onClick={() => setSite(id)}>{label}</button>)}
        </div>
        {example.loading && <p className="muted">Loading stored measurements…</p>}
        {example.data && <Worked detail={example.data} />}
      </section>

      <section className="step-section">
        <h2>Reference windows</h2>
        <p>Each reference is a 10 km window placed by a written rule before its terrain was measured. Its resolution floor comes from moving it 2 km in four directions; a reference whose terrain changes by more than a third of the tolerance under that move is shown with distances only.</p>
        <div className="table-scroll" tabIndex={0} role="region" aria-label="Reference windows">
          <table className="feature-table" data-testid="method-references">
            <thead><tr><th scope="col">Reference</th><th scope="col">Elevation product</th><th scope="col">Median slope (60 m)</th><th scope="col">δ slope · relative elevation</th><th scope="col">Scored</th></tr></thead>
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
      </section>

      <section className="step-section">
        <h2>What the atlas compares, and what it does not</h2>
        <p><strong>Offered:</strong> Terrain shape (scored), Surface temperature (measured, not scored) and Field-test record (published research, not scored).</p>
        <p><strong>Planned, not offered yet.</strong> These task profiles exist in the API but are not shown in the atlas, because their task-critical evidence has not been measured comparably:</p>
        <div className="profile-cards">{profiles.filter((p) => p.id !== "terrain_analogy").map((p) => (
          <section key={p.id} className="profile-card" data-testid={`method-profile-${p.id}`}>
            <h3>{p.label}</h3>
            <p className="small">{p.question}</p>
            <p className="small"><strong>Would need:</strong> {p.task_critical.map((d) => d.replaceAll("_", " ")).join(", ")}. {p.not_assessed.length ? `Not measured today: ${p.not_assessed.slice(0, 3).join(", ")}.` : ""}</p>
          </section>
        ))}</div>
      </section>

      <section className="step-section">
        <h2>Temperature comparability audit</h2>
        <p>MODIS land-surface temperature (a 1 km area mean from orbit, clear-sky 8-day composites) and Mars 2020 MEDA ground temperature (a few square metres beside the rover, all conditions) are both skin temperatures, but they fail spatial-support and sampling equivalence. Temperature is therefore shown as context and never enters an index.</p>
        {thermal.data && <ThermalChecks detail={thermal.data} />}
      </section>

      <section className="step-section">
        <h2>Why earlier scores clustered near 99.9</h2>
        <p>{dec.finding}</p>
        <div className="table-scroll" tabIndex={0} role="region" aria-label="Index after each method change">
          <table className="feature-table" data-testid="decomposition">
            <caption className="sr-only">Index after each change, Jezero reference</caption>
            <thead><tr><th scope="col">Site</th>{(dec.steps ?? []).map((s: string, i: number) => <th key={s} scope="col">{i + 1}. {s}</th>)}</tr></thead>
            <tbody>{(dec.rows ?? []).map((r: Json) => (
              <tr key={r.site_id}><th scope="row">{r.site_name}</th>{r.steps.map((v: number, i: number) => <td key={i} className="mono">{v.toFixed(2)}</td>)}</tr>
            ))}</tbody>
          </table>
        </div>
        <p className="muted small">Each column changes one thing. The first Atacama window is shown for history only: it contains an industrial complex and is not scored.</p>
      </section>

      <section className="step-section">
        <h2>Data exclusions</h2>
        <ul>{m && Object.entries(m.aoi_exclusions as Record<string, Json>).map(([k, v]) => <li key={k}><strong>{k}</strong>: {v.reason}</li>)}</ul>
        <p className="small">Holuhraun (Iceland) and the McMurdo Dry Valleys (Antarctica) are registered but not measured: both lie outside SRTM elevation coverage (60° N to 56° S).</p>
      </section>

      <section className="step-section">
        <h2>Paper and historical methods</h2>
        <p>The technical paper <span className="mono">docs/terraluna-technical-paper.md</span> describes this build from the same verified outputs. Earlier method versions are still served for reproducibility:</p>
        <dl className="definition-list">{m && Object.entries(m.compatibility as Record<string, string>).map(([k, v]) => <Fragment key={k}><dt>{k}</dt><dd>{v}</dd></Fragment>)}</dl>
      </section>
    </article>
  );
}

function Worked({ detail }: { detail: ResultDetail }) {
  const c = detail.candidate;
  const terrain = c.families.find((f) => f.family === "terrain");
  const scored = terrain?.features.filter((f) => f.role === "scored") ?? [];
  const parts = scored.filter((f) => f.contribution != null);
  return (
    <div className="worked" data-testid="worked-example">
      <p><strong>{detail.earth_window.name}</strong> against <strong>{detail.reference_window.name}</strong>, 60 m grid:</p>
      {scored.map((f) => (
        <div key={f.feature} className="worked-tex">
          <p className="small"><strong>{f.label}</strong>{f.resolvable === false ? " · inside the resolution floor" : ""}</p>
          {f.distance != null && f.tau != null && f.similarity != null ? (
            <TeX tex={`\\begin{aligned} d &= ${f.distance.toFixed(3)}${texUnit(f.units)}, \\quad \\tau = ${f.tau.toFixed(2)}${texUnit(f.units)} \\\\ s &= \\exp\\!\\left[-\\ln 2\\,(${(f.d_over_tau ?? 0).toFixed(3)})^{2}\\right] = ${f.similarity.toFixed(4)} \\\\ 100\\,a\\,s &= ${(f.contribution ?? 0).toFixed(2)} \\end{aligned}`} />
          ) : <p className="muted small">{f.reason}</p>}
        </div>
      ))}
      {c.observed_index != null && (
        <div className="worked-tex">
          <TeX tex={`A_{\\text{obs}} = ${parts.map((f) => (f.contribution ?? 0).toFixed(2)).join(" + ")} = ${c.observed_index.toFixed(2)}`} />
          {c.standing && <TeX tex={`N_{\\text{closer}} = ${c.standing.closer_than} \\text{ of } ${c.standing.of} \\text{ ordinary windows}`} />}
        </div>
      )}
      <p className="small">Shown in the atlas as <strong>{c.observed_index != null ? `${c.observed_index.toFixed(0)}/100` : "no index"}</strong>{c.standing ? `, beats ${c.standing.closer_than} of ${c.standing.of} ordinary windows` : ""}. Scenario range {c.sensitivity?.index_range?.join("–") ?? "—"} across window shifts, elevation model, grid, tolerance and weights.</p>
    </div>
  );
}

function ThermalChecks({ detail }: { detail: ResultDetail }) {
  const t = detail.candidate.families.find((f) => f.family === "temperature");
  const audit = (t?.context as Json | null)?.audit as Json | undefined;
  if (!audit) return <p className="muted">{t?.reason ?? "No thermal record."}</p>;
  return (
    <ul className="audit" data-testid="thermal-audit">
      {(audit.checks as Json[]).map((c) => (
        <li key={c.check} className={c.passed ? "pass" : c.required ? "fail" : "note"}>
          <span className="audit-mark" aria-hidden="true">{c.passed ? "✓" : c.required ? "✕" : "–"}</span>
          <span><strong>{c.check}</strong> — {c.passed ? "passed" : c.required ? "failed" : "not met"}. {c.detail}</span>
        </li>
      ))}
    </ul>
  );
}
