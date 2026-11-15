"use client";

import { resolveApiUrl, safeExternalUrl } from "../../../lib/api";
import type { ReferenceV3 } from "../../../lib/analogue";
import { coords } from "../../../lib/format";

interface ProfileOption { id: string; label: string; question: string; task_critical: string[]; rankable?: boolean }

function thumbOf(r: ReferenceV3): string | null {
  return resolveApiUrl(r.imagery?.url ?? r.hillshade_url);
}

export default function ReferenceBand({ references, referenceId, onReference, profiles, profileId, onProfile }: {
  references: ReferenceV3[]; referenceId: string; onReference: (id: string) => void;
  profiles: ProfileOption[]; profileId: string; onProfile: (id: string) => void;
}) {
  const reference = references.find((r) => r.id === referenceId) ?? null;
  const body = reference?.body ?? "mars";
  const shown = references.filter((r) => r.body === body);
  const active = profiles.find((p) => p.id === profileId);
  const marsCount = references.filter((r) => r.body === "mars").length;
  const moon = references.find((r) => r.body === "moon");
  const firstMars = references.find((r) => r.body === "mars");
  const doi = reference?.dem.doi ? safeExternalUrl(`https://doi.org/${reference.dem.doi}`) : null;
  return (
    <section className="reference-band rb2" aria-label="Reference site and mission profile">
      <div className="reference">
        <div className="step-label"><span className="mono">1</span> Reference window on another world</div>
        <div className="body-switch" role="radiogroup" aria-label="Reference body">
          <button type="button" role="radio" aria-checked={body === "mars"} disabled={!firstMars} onClick={() => firstMars && onReference(firstMars.id)}>Mars · {marsCount}</button>
          <button type="button" role="radio" aria-checked={body === "moon"} disabled={!moon} onClick={() => moon && onReference(moon.id)}>Moon · {moon ? 1 : 0}</button>
        </div>
        <div className="ref-cards" role="radiogroup" aria-label={`${body === "moon" ? "Moon" : "Mars"} reference windows`} data-testid="reference-cards">
          {shown.map((r) => {
            const src = thumbOf(r);
            return (
              <button key={r.id} type="button" role="radio" aria-checked={r.id === referenceId} className={`ref-card ${r.id === referenceId ? "is-active" : ""}`} onClick={() => onReference(r.id)} data-testid={`reference-${r.id}`}>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                {src && <img src={src} alt="" loading="lazy" width={56} height={56} />}
                <span className="ref-card-text">
                  <span className="ref-card-name">{r.name}</span>
                  <span className="ref-card-meta">{r.region.replace(/^(Mars|Moon) - /, "")}</span>
                  <span className={`ref-card-badge ${r.scorable ? "ok" : "warn"}`}>{r.scorable ? "scored terrain" : "distances only"}</span>
                </span>
              </button>
            );
          })}
        </div>
        {reference && (
          <div className="ref-detail">
            <h1 className="reference-name">{reference.name}</h1>
            <p className="reference-facts">
              {reference.body === "moon" ? "90° S" : coords(reference.center[1], reference.center[0])} · 10 km window · {reference.dem.product.replaceAll("_", " ")} (20 m) analysed on a 60 m grid · present-day surface
            </p>
            {!reference.scorable && <p className="notice notice-warn" data-testid="reference-not-scorable">{reference.scorable_reason}</p>}
            <details className="ref-about">
              <summary>About this reference window</summary>
              <div className="ref-about-body">
                {reference.context && <p>{reference.context}</p>}
                <p><strong>Placement:</strong> {reference.selection_rationale}</p>
                <dl className="kv small">
                  <dt>Elevation product</dt><dd>{reference.dem.item ?? reference.dem.product} · {reference.dem.provider}{doi && <> · <a href={doi} target="_blank" rel="noreferrer noopener">DOI {reference.dem.doi}</a></>}</dd>
                  {reference.dem.intersection_error && <><dt>Stereo quality</dt><dd>median intersection error {reference.dem.intersection_error.median_m} m (p95 {reference.dem.intersection_error.p95_m} m)</dd></>}
                  <dt>Input SHA-256</dt><dd className="mono break">{reference.dem.sha256}</dd>
                  <dt>Median slope (60 m)</dt><dd className="mono">{reference.slope_median_60m.toFixed(2)}°</dd>
                  <dt>Resolution floor</dt><dd className="mono">slope {reference.resolution_floor.slope?.combined.toFixed(2)}° · relative elevation {reference.resolution_floor.relative_elevation?.combined.toFixed(1)} m</dd>
                  {reference.imagery && <><dt>Image</dt><dd>{reference.imagery.attribution}</dd></>}
                </dl>
                <ul className="small">{reference.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
              </div>
            </details>
          </div>
        )}
      </div>
      <div className="profile">
        <div className="step-label"><span className="mono">2</span> Question or field task</div>
        <div className="profile-options" role="radiogroup" aria-label="Mission profile">
          {profiles.map((p) => (
            <button key={p.id} type="button" role="radio" aria-checked={p.id === profileId} onClick={() => onProfile(p.id)} data-testid={`profile-${p.id}`}>
              {p.label}{p.rankable === false && <span className="profile-tag">partial</span>}
            </button>
          ))}
        </div>
        {active && <p className="profile-purpose">{active.question} <span className="muted">Task-critical evidence: {active.task_critical.map((d) => d.replaceAll("_", " ")).join(", ")}. Weights are provisional.</span></p>}
      </div>
    </section>
  );
}
