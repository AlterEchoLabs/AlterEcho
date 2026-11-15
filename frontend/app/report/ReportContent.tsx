"use client";

import Link from "next/link";
import { useEffect, useState, useSyncExternalStore } from "react";
import { apiV3 } from "../../lib/api";
import { PROFILE_IDS_V3, type ProfileIdV3, type ResultDetail } from "../../lib/analogue";
import { pct } from "../../lib/format";
import { FullEvidence } from "../components/atlas/ResultPanel";

const subscribe = (cb: () => void) => { window.addEventListener("popstate", cb); return () => window.removeEventListener("popstate", cb); };
const useSearch = () => useSyncExternalStore(subscribe, () => window.location.search, () => "");
const slug = (v: string | null, fallback: string) => (v && /^[a-z0-9-]{1,64}$/.test(v) ? v : fallback);

export default function ReportContent() {
  const params = new URLSearchParams(useSearch());
  const site = slug(params.get("site"), "earth-atacama-south");
  const reference = slug(params.get("reference"), "mars-jezero");
  const profileParam = params.get("profile") as ProfileIdV3 | null;
  const profile: ProfileIdV3 = profileParam && PROFILE_IDS_V3.includes(profileParam) ? profileParam : "terrain_analogy";
  const key = `${site}|${reference}|${profile}`;
  const [state, setState] = useState<{ key: string; data: ResultDetail | null; error: string | null } | null>(null);

  useEffect(() => {
    let active = true;
    apiV3.result(site, profile, reference)
      .then((data) => { if (active) setState({ key, data, error: null }); })
      .catch((error: unknown) => { if (active) setState({ key, data: null, error: error instanceof Error ? error.message : "Report unavailable" }); });
    return () => { active = false; };
  }, [key, site, profile, reference]);

  const current = state?.key === key ? state : null;
  if (!current) return <article className="report"><p className="muted">Building the report from stored measurements…</p></article>;
  if (current.error || !current.data) return <article className="report"><p className="error-inline" role="alert">{current.error}</p><Link href="/">Back to the atlas</Link></article>;
  const d = current.data, c = d.candidate, s = c.simple;
  const download = () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(d, null, 2)], { type: "application/json" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `alterecho-${site}-${profile}-${reference}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return (
    <article className="report" data-testid="report">
      <p className="step-label">Comparison record · {d.comparison.method_version} · generated {String(d.comparison.generated_at).slice(0, 19)} UTC</p>
      <h1>{d.earth_window.name} compared with {d.reference_window.name}</h1>
      <p className="lede">{d.comparison.profile.label}: {d.comparison.profile.question}</p>
      <div className="report-actions">
        <button type="button" className="button-link" onClick={() => window.print()}>Print or save as PDF</button>
        <button type="button" className="button-link secondary" onClick={download}>Download JSON record</button>
        <Link className="button-link secondary" href={`/?site=${site}&profile=${profile}&reference=${reference}`}>Open in the atlas</Link>
      </div>
      <h2>Result</h2>
      {s.verdict && <p className="report-verdict"><strong>{s.verdict}</strong></p>}
      {s.show_index && c.observed_index != null && <p>Terrain similarity index <strong className="mono">{c.observed_index.toFixed(0)}/100</strong> (present-day terrain shape at a 60 m grid){c.sensitivity?.index_range ? `, scenario range ${c.sensitivity.index_range[0].toFixed(0)}–${c.sensitivity.index_range[1].toFixed(0)}` : ""} · evidence coverage {pct(c.evidence_coverage)}</p>}
      {c.standing && <p data-testid="report-standing"><strong className="mono">{c.standing.closer_than} of {c.standing.of}</strong> ordinary Earth land windows are less similar to {d.reference_window.name} than this site.{s.class_label ? ` ${s.class_label}.` : ""}</p>}
      <p>{s.conclusion}</p>
      {s.strength && <p><strong>Main strength:</strong> {s.strength}</p>}
      {s.mismatch && <p><strong>Main mismatch:</strong> {s.mismatch}</p>}
      {s.background_text && <p><strong>Compared with ordinary land:</strong> {s.background_text}</p>}
      <p><strong>Limitation:</strong> {s.limitation}</p>
      <p className="muted">{s.validation_status}</p>
      <h2>Full evidence and calculations</h2>
      <FullEvidence detail={d} />
    </article>
  );
}
