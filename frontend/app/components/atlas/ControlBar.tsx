"use client";

import { resolveApiUrl, safeExternalUrl } from "../../../lib/api";
import { COMPARE_MODES, type CompareMode, type ReferenceV3 } from "../../../lib/analogue";
import { coords } from "../../../lib/format";

const SHORT: Record<string, string> = {
  "mars-jezero": "Jezero", "mars-gale-aeolis-palus": "Gale", "mars-insight-elysium": "InSight", "mars-gusev-plains": "Gusev",
  "mars-eberswalde-delta": "Eberswalde", "moon-south-pole-shackleton": "Shackleton",
};
export const shortName = (r: { id: string; name: string }) => SHORT[r.id] ?? r.name.split(" (")[0];

/** Step 1 and 2 of the atlas in one compact band: which reference window, and what to compare by. */
export default function ControlBar({ references, referenceId, onReference, mode, onMode }: {
  references: ReferenceV3[]; referenceId: string; onReference: (id: string) => void; mode: CompareMode; onMode: (mode: CompareMode) => void;
}) {
  const reference = references.find((r) => r.id === referenceId) ?? null;
  const doi = reference?.dem.doi ? safeExternalUrl(`https://doi.org/${reference.dem.doi}`) : null;
  const bodies: ("mars" | "moon")[] = ["mars", "moon"];
  return (
    <section className="control-bar" aria-label="Choose a reference window and what to compare">
      <div className="cb-row">
        <div className="cb-block cb-refs">
          <span className="cb-label" id="ref-label"><span className="cb-step mono">1</span> Reference window</span>
          <div className="ref-chips" role="radiogroup" aria-labelledby="ref-label" data-testid="reference-cards">
            {bodies.map((body) => {
              const group = references.filter((r) => r.body === body);
              if (!group.length) return null;
              return (
                <div key={body} className="ref-chip-group">
                  <span className="ref-body">{body === "mars" ? "Mars" : "Moon"}</span>
                  {group.map((r) => {
                    const src = resolveApiUrl(r.imagery?.url ?? r.hillshade_url);
                    const active = r.id === referenceId;
                    return (
                      <button key={r.id} type="button" role="radio" aria-checked={active} className={`ref-chip ${active ? "is-active" : ""}`}
                        onClick={() => onReference(r.id)} data-testid={`reference-${r.id}`} title={r.name}>
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        {src && <img src={src} alt="" width={30} height={30} loading="lazy" />}
                        <span>{shortName(r)}</span>
                        {!r.scorable && <span className="ref-chip-flag"><span aria-hidden="true">·</span><span className="sr-only">distances only</span></span>}
                      </button>
                    );
                  })}
                </div>
              );
            })}
          </div>
        </div>
        <div className="cb-block cb-modes">
          <span className="cb-label" id="mode-label"><span className="cb-step mono">2</span> Compare by</span>
          <div className="mode-switch" role="radiogroup" aria-labelledby="mode-label">
            {COMPARE_MODES.map((m) => (
              <button key={m.id} type="button" role="radio" aria-checked={mode === m.id} onClick={() => onMode(m.id)} data-testid={`mode-${m.id}`} title={m.hint}>
                {m.label}
              </button>
            ))}
          </div>
          <p className="mode-hint" data-testid="mode-hint">{COMPARE_MODES.find((m) => m.id === mode)?.hint}</p>
        </div>
      </div>
      {reference && (
        <div className="ref-summary">
          <h1 className="reference-name">{reference.name}</h1>
          <p className="reference-facts">
            {reference.body === "moon" ? "Moon · 90° S" : `Mars · ${coords(reference.center[1], reference.center[0])}`} · 10 km window · {reference.dem.product.replaceAll("_", " ")} (20 m), analysed on a 60 m grid
          </p>
          {!reference.scorable && <p className="notice notice-warn" data-testid="reference-not-scorable">{reference.scorable_reason}</p>}
          <details className="ref-about">
            <summary>About this reference window</summary>
            <div className="ref-about-body">
              {reference.context && <p>{reference.context}</p>}
              <p><strong>Placement:</strong> {reference.selection_rationale}</p>
              <dl className="kv small">
                <dt>Elevation product</dt><dd>{reference.dem.item ?? reference.dem.product} · {reference.dem.provider}{doi && <> · <a href={doi} target="_blank" rel="noreferrer noopener">DOI {reference.dem.doi}</a></>}</dd>
                {reference.dem.intersection_error && <><dt>Stereo quality</dt><dd>median intersection error {reference.dem.intersection_error.median_m} m (95th percentile {reference.dem.intersection_error.p95_m} m)</dd></>}
                <dt>Median slope (60 m)</dt><dd className="mono">{reference.slope_median_60m.toFixed(2)}°</dd>
                <dt>Resolution floor</dt><dd className="mono">slope {reference.resolution_floor.slope?.combined.toFixed(2)}° · relative elevation {reference.resolution_floor.relative_elevation?.combined.toFixed(1)} m</dd>
                {reference.imagery && <><dt>Image</dt><dd>{reference.imagery.attribution}</dd></>}
              </dl>
              <ul className="small">{reference.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
            </div>
          </details>
        </div>
      )}
    </section>
  );
}
