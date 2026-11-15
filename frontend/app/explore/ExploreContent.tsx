"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useState, useSyncExternalStore } from "react";
import { api, apiV2, resolveApiUrl, type AoiFeature, type Preflight, type ScreeningJob, type Site } from "../../lib/api";
import { coords, date, pct } from "../../lib/format";

const ExploreMap = dynamic(() => import("./ExploreMap"), { ssr: false, loading: () => <div className="explore-map" /> });

// Places with published analog research, offered as starting points. Coordinates are locators, not vetted study windows.
const GAZETTEER: { label: string; lat: number; lon: number }[] = [
  { label: "Death Valley — Badwater Basin (USA)", lat: 36.2297, lon: -116.7669 },
  { label: "Salar de Uyuni (Bolivia)", lat: -20.13, lon: -67.49 },
  { label: "Timanfaya lava fields, Lanzarote (Spain)", lat: 29.01, lon: -13.75 },
  { label: "Kīlauea Iki crater (Hawaiʻi, USA)", lat: 19.417, lon: -155.246 },
  { label: "Lava Beds National Monument (USA)", lat: 41.71, lon: -121.51 },
  { label: "Río Tinto mining district (Spain)", lat: 37.69, lon: -6.59 },
  { label: "Haughton Crater, Devon Island (outside SRTM)", lat: 75.38, lon: -89.68 },
];
const STEPS: ScreeningJob["state"][] = ["queued", "acquiring", "processing", "quality_check", "ready"];
const STEP_LABEL: Record<string, string> = { queued: "Queued", acquiring: "Acquiring SRTMGL1", processing: "Measuring terrain", quality_check: "Quality check", ready: "Ready" };
const FAMILY_LABEL: Record<string, string> = { slope: "Slope", local_relief: "Local relief", roughness: "Roughness", relative_elevation: "Relative elevation" };

const subscribe = (cb: () => void) => { window.addEventListener("popstate", cb); return () => window.removeEventListener("popstate", cb); };
const useJobParam = () => useSyncExternalStore(subscribe, () => new URLSearchParams(window.location.search).get("job"), () => null);

export default function ExploreContent() {
  const linkedJob = useJobParam();
  const [center, setCenter] = useState<{ lat: number; lon: number } | null>(null);
  const [latText, setLatText] = useState("");
  const [lonText, setLonText] = useState("");
  const [label, setLabel] = useState("");
  const [preflight, setPreflight] = useState<{ key: string; data: Preflight | null; error: string | null } | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [job, setJob] = useState<ScreeningJob | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [catalog, setCatalog] = useState<AoiFeature[]>([]);
  const [sites, setSites] = useState<Site[]>([]);
  const activeJob = jobId ?? (linkedJob && /^[0-9a-f]{32}$/.test(linkedJob) ? linkedJob : null);
  const centerKey = center ? `${center.lat},${center.lon}` : null;
  const jobRunning = !!job && !["ready", "failed", "unsupported", "requires_credentials"].includes(job.state);

  useEffect(() => {
    let active = true;
    api.sites().then((list) => {
      if (!active) return;
      setSites(list);
      Promise.allSettled(list.filter((s) => s.body === "earth" && s.aoi_id).map((s) => api.aoi(s.id))).then((items) => {
        if (active) setCatalog(items.flatMap((i) => (i.status === "fulfilled" ? [i.value] : [])));
      });
    }).catch(() => {});
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!center || !centerKey) return;
    let active = true;
    const timer = setTimeout(() => {
      apiV2.preflight(center.lat, center.lon)
        .then((data) => { if (active) setPreflight({ key: centerKey, data, error: null }); })
        .catch((error: unknown) => { if (active) setPreflight({ key: centerKey, data: null, error: error instanceof Error ? error.message : "Preflight failed" }); });
    }, 250);
    return () => { active = false; clearTimeout(timer); };
  }, [center, centerKey]);

  useEffect(() => {
    if (!activeJob) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    const poll = () => {
      apiV2.job(activeJob, controller.signal).then((data) => {
        setJob(data);
        if (!["ready", "failed", "unsupported", "requires_credentials"].includes(data.state)) timer = setTimeout(poll, 2000);
      }).catch(() => { if (!controller.signal.aborted) timer = setTimeout(poll, 4000); });
    };
    poll();
    return () => { controller.abort(); if (timer) clearTimeout(timer); };
  }, [activeJob]);

  const pick = useCallback((lat: number, lon: number) => {
    setCenter({ lat, lon }); setLatText(String(lat)); setLonText(String(lon)); setSubmitError(null);
  }, []);

  const submit = async () => {
    if (!center) return;
    setSubmitting(true); setSubmitError(null);
    try {
      const created = await apiV2.submit(center.lat, center.lon, label || undefined);
      setJobId(created.job_id); setJob(created);
      const url = new URL(window.location.href); url.searchParams.set("job", created.job_id); window.history.replaceState(null, "", url);
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : "Submission failed");
    } finally { setSubmitting(false); }
  };

  const pre = preflight?.key === centerKey ? preflight : null;
  const result = job?.result;
  const jezero = result?.comparisons["mars-jezero"];
  const moon = result?.comparisons["moon-south-pole-shackleton"];
  const share99 = result?.base_rate.share_at_or_above?.["99"];
  const stepIndex = job ? STEPS.indexOf(job.state) : -1;

  return (
    <div className="explore">
      <section className="explore-map-col" aria-label="Choose an area">
        <div className="step-label"><span className="mono">1</span> Place a 10 km window</div>
        <ExploreMap center={center ?? job?.center ?? null} window={pre?.data?.geometry ?? job?.geometry ?? null} catalog={catalog} onPick={pick} />
      </section>
      <section className="explore-side" aria-label="Screening">
        <h1>Explore a new Earth area</h1>
        <p className="muted">Click the map, type coordinates, or start from a documented analog place. TerraLuna measures the same terrain features as the showcase sites and compares them with the processed planetary references. Results are <span className="screening-badge">screening</span> until reviewed.</p>
        <form className="coord-form" onSubmit={(e) => { e.preventDefault(); const lat = Number(latText), lon = Number(lonText); if (Number.isFinite(lat) && Number.isFinite(lon) && Math.abs(lat) <= 90 && Math.abs(lon) <= 180) pick(lat, lon); }}>
          <label>Latitude<input inputMode="decimal" value={latText} onChange={(e) => setLatText(e.target.value)} placeholder="e.g. 36.23" aria-label="Latitude in decimal degrees" /></label>
          <label>Longitude<input inputMode="decimal" value={lonText} onChange={(e) => setLonText(e.target.value)} placeholder="e.g. -116.77" aria-label="Longitude in decimal degrees" /></label>
          <button type="submit" className="button-link secondary">Set</button>
          <label>Documented places<select aria-label="Documented analog places" value="" onChange={(e) => { const g = GAZETTEER[Number(e.target.value)]; if (g) { pick(g.lat, g.lon); setLabel(g.label); } }}>
            <option value="">Choose…</option>{GAZETTEER.map((g, i) => <option key={g.label} value={i}>{g.label}</option>)}
          </select></label>
        </form>

        {center && (
          <div className="preflight" data-testid="preflight">
            <div className="step-label"><span className="mono">2</span> What data exists here</div>
            <p className="mono small">{coords(center.lat, center.lon)} · 10 × 10 km</p>
            {!pre && <p className="muted small">Checking coverage…</p>}
            {pre?.error && <p className="error-inline" role="alert">{pre.error}</p>}
            {pre?.data && (
              <dl className="stability">
                <dt>Elevation</dt><dd>{pre.data.supported ? `${pre.data.dem.product}, ${pre.data.dem.native_resolution}; tiles ${pre.data.dem.tiles.join(", ")} (${pre.data.dem.tiles_cached.length} cached)` : pre.data.reason}</dd>
                <dt>Credentials</dt><dd>{pre.data.dem.requires_credentials ? "Needed: the server has no Earthdata token for uncached tiles." : pre.data.dem.credentials_available || pre.data.dem.tiles_cached.length === pre.data.dem.tiles.length ? "Available on the server" : "—"}</dd>
                <dt>Imagery</dt><dd>{pre.data.imagery.product} ({pre.data.imagery.authentication}). {pre.data.imagery.note}</dd>
                <dt>Compared with</dt><dd>{pre.data.references.map((r) => sites.find((s) => s.id === r)?.name ?? r).join(", ")}</dd>
                <dt>Analysis</dt><dd>{pre.data.dem.analysis_scales_m.join(" / ")} m, terrain-v4.0</dd>
                <dt>Limits</dt><dd>{pre.data.limits.per_client_per_hour} per hour per client · queue {pre.data.queue.pending}/{pre.data.queue.max}</dd>
              </dl>
            )}
            <label className="toggle" style={{ marginTop: 8 }}><span>Label</span><input className="search-input" style={{ width: 240, margin: 0 }} maxLength={60} value={label} onChange={(e) => setLabel(e.target.value)} aria-label="Optional label for this screening" /></label>
            <div className="export-row" style={{ marginTop: 12 }}>
              <button type="button" className="button-link" onClick={submit} disabled={submitting || jobRunning || !pre?.data?.supported} data-testid="submit-screening">{submitting ? "Submitting…" : jobRunning ? "Measuring… (one job at a time)" : "Measure this window"}</button>
              {submitError && <span className="error-inline" role="alert">{submitError}</span>}
            </div>
          </div>
        )}

        {job && (
          <div className="job" data-testid="job-panel" aria-live="polite">
            <div className="step-label" style={{ marginTop: 24 }}><span className="mono">3</span> Processing · {job.label}</div>
            {["failed", "unsupported", "requires_credentials"].includes(job.state) ? (
              <div className="notice notice-error" role="alert"><p><strong>{job.state.replaceAll("_", " ")}</strong>: {job.log[job.log.length - 1]?.message}</p></div>
            ) : (
              <ol className="job-steps">
                {STEPS.map((s, i) => <li key={s} className={i < stepIndex || job.state === "ready" ? "done" : i === stepIndex ? "active" : ""}><span className="step-dot" />{STEP_LABEL[s]}{i === stepIndex && job.state !== "ready" ? ` — ${job.log[job.log.length - 1]?.message ?? ""}` : ""}</li>)}
              </ol>
            )}
            {result && job.state === "ready" && (
              <div className="job-result" data-testid="job-result">
                <h2 className="section-title">Screening result <span className="screening-badge">screening · not reviewed</span></h2>
                {jezero && <p className="score-figure"><span className="mono">{jezero.terrain_index.toFixed(1)}</span><small>/100 vs Jezero</small></p>}
                {moon && <p className="muted">Against the lunar south-pole window: <span className="mono">{moon.terrain_index.toFixed(1)}</span>/100 (limited lunar comparison).</p>}
                {jezero && (
                  <div className="table-scroll"><table className="feature-table">
                    <thead><tr><th>Family</th><th>W1 at 60 m</th><th>τ</th><th>Index</th></tr></thead>
                    <tbody>{Object.entries(jezero.families).map(([k, f]) => <tr key={k}><th scope="row">{FAMILY_LABEL[k] ?? k}</th><td className="mono">{f.w1_60m.toFixed(2)} {f.units === "degrees" ? "°" : "m"}</td><td className="mono">{f.tau}</td><td className="mono">{f.index.toFixed(1)}</td></tr>)}</tbody>
                  </table></div>
                )}
                {share99 != null && <p className="base-rate"><strong>{Math.round(share99 * 100)}%</strong> of {result.base_rate.windows} unselected Earth windows score 99 or more against Jezero, so a high value here is common for low-relief terrain.</p>}
                {result.imagery?.status === "available" && result.imagery.preview_url ? (
                  <figure style={{ margin: "16px 0" }}>
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img className="job-image" src={resolveApiUrl(result.imagery.preview_url) ?? ""} alt={`Sentinel-2 true-colour image of the screened window at ${coords(job.center.lat, job.center.lon)}`} />
                    <figcaption className="muted small">{result.imagery.product_id} · acquired {date(result.imagery.acquisition_datetime)} · AOI cloud {pct(result.imagery.aoi_cloud_fraction ?? null, 1)} · {result.imagery.attribution}</figcaption>
                  </figure>
                ) : <p className="muted small">Imagery: {result.imagery?.reason ?? "not available"}</p>}
                <ul className="limits">{result.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
                <p className="muted small">Inputs: {result.inputs.map((i) => `${i.tile_id} (SHA-256 ${i.sha256.slice(0, 10)}…)`).join(", ")} · result SHA-256 {result.result_sha256?.slice(0, 12)}…</p>
                <div className="export-row">
                  <button type="button" className="button-link secondary" onClick={() => { const url = URL.createObjectURL(new Blob([JSON.stringify(job, null, 2)], { type: "application/json" })); const a = document.createElement("a"); a.href = url; a.download = `terraluna-screening-${job.job_id.slice(0, 8)}.json`; a.click(); URL.revokeObjectURL(url); }}>Download JSON record</button>
                  <button type="button" className="button-link secondary" onClick={() => navigator.clipboard?.writeText(window.location.href)}>Copy share link</button>
                </div>
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
