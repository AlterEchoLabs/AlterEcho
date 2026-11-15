"use client";

import dynamic from "next/dynamic";
import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { api, apiV3, resolveApiUrl, type Site } from "../../../lib/api";
import { num } from "../../../lib/format";
import { useKeyed } from "../../../lib/hooks";
import { GLOBE_TEXTURES } from "./GlobeView";
import type { ReferenceV3 } from "../../../lib/analogue";
import SyncedCompare from "./SyncedCompare";

const GlobeView = dynamic(() => import("./GlobeView"), { ssr: false, loading: () => <div className="viewer-placeholder">Loading globe…</div> });
const TerrainView = dynamic(() => import("./TerrainView"), { ssr: false, loading: () => <div className="viewer-placeholder">Loading terrain…</div> });
const SiteExplorer = dynamic(() => import("./SiteExplorer"), { ssr: false, loading: () => <div className="viewer-placeholder explorer-placeholder">Loading the interactive map…</div> });

type Mode = "explore" | "compare" | "terrain" | "globe";
// The interactive globe depends on WebGL and third-party tiles, so it is offered last; the first view uses only local images.
const MODES: { id: Mode; label: string }[] = [{ id: "compare", label: "Compare with reference" }, { id: "terrain", label: "3D terrain" }, { id: "explore", label: "Interactive map" }];
const EXAGGERATIONS = [1, 2, 4];

/** Below the result: ways to look further. The panels need WebGL or third-party tiles, so they mount only when scrolled near. */
export default function SiteViewer({ site, reference, referenceInfo }: { site: Site; reference: Site | null; referenceInfo?: ReferenceV3 | null }) {
  const [mode, setMode] = useState<Mode>("compare");
  const [compare, setCompare] = useState(false);
  const [exaggeration, setExaggeration] = useState(2);
  // Browsers without IntersectionObserver load the panels straight away.
  const [near, setNear] = useState(() => typeof window !== "undefined" && typeof IntersectionObserver === "undefined");
  const root = useRef<HTMLElement | null>(null);
  const tabsId = useId();
  const measured = site.data_status === "real_processed";

  useEffect(() => {
    const el = root.current;
    if (!el || near || typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver((entries) => { if (entries.some((e) => e.isIntersecting)) setNear(true); }, { rootMargin: "300px 0px" });
    io.observe(el);
    return () => io.disconnect();
  }, [near]);

  const explorer = useKeyed(measured && near && mode === "compare" ? site.id : null, apiV3.explorer);
  const heightmap = useKeyed(measured && near && mode === "terrain" ? site.id : null, api.heightmap);
  const refHeightmap = useKeyed(compare && near && mode === "terrain" && reference ? reference.id : null, api.heightmap);

  const available: { id: Mode; label: string }[] = measured && site.body === "earth" ? MODES : [{ id: "globe", label: "Globe (orientation)" }];
  const activeMode: Mode = available.some((m) => m.id === mode) ? mode : "globe";
  const refName = reference?.name ?? "reference";

  const onTabKey = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
    event.preventDefault();
    const i = available.findIndex((m) => m.id === activeMode);
    const next = available[(i + (event.key === "ArrowRight" ? 1 : available.length - 1)) % available.length];
    setMode(next.id);
    document.getElementById(`${tabsId}-${next.id}`)?.focus();
  };

  return (
    <section ref={root} className="viewer" aria-labelledby={`${tabsId}-title`} data-testid="site-viewer" data-site-id={site.id}>
      <h3 className="viewer-title" id={`${tabsId}-title`}>Look closer at the study window</h3>
      <div className="viewer-bar">
        <div role="tablist" aria-label="View mode" className="segmented">
          {available.map((m) => (
            <button key={m.id} id={`${tabsId}-${m.id}`} role="tab" type="button" aria-selected={activeMode === m.id} aria-controls={`${tabsId}-panel`}
              tabIndex={activeMode === m.id ? 0 : -1} onClick={() => setMode(m.id)} onKeyDown={onTabKey}>{m.label}</button>
          ))}
        </div>
        {measured && reference && activeMode !== "compare" && (
          <label className="toggle"><input type="checkbox" checked={compare} onChange={(e) => setCompare(e.target.checked)} /><span>Show {refName} alongside</span></label>
        )}
      </div>

      <div id={`${tabsId}-panel`} role="tabpanel" aria-labelledby={`${tabsId}-${activeMode}`} className="viewer-panel" key={activeMode}>
        {!near && <div className="viewer-placeholder explorer-placeholder">Scroll here to load this view.</div>}
        {near && activeMode === "compare" && (
          referenceInfo
            ? <SyncedCompare site={site} reference={referenceInfo} earthImage={explorer.data?.imagery ? resolveApiUrl(explorer.data.imagery.url) : null} />
            : <div className="viewer-placeholder">Loading the reference window…</div>
        )}

        {near && activeMode === "explore" && (
          <div className={compare && reference ? "pair explore-pair" : "single"}>
            <SiteExplorer site={site} />
            {compare && reference && <GlobeView body={reference.body} latitude={reference.latitude} longitude={reference.longitude} markerColor="#e07a52" label={`${reference.body === "moon" ? "Moon" : "Mars"} globe with a marker at ${refName} (orientation only)`} />}
          </div>
        )}

        {near && activeMode === "terrain" && (
          <>
            <div className="layer-switch" role="radiogroup" aria-label="Vertical exaggeration">
              {EXAGGERATIONS.map((v) => <button key={v} type="button" role="radio" aria-checked={exaggeration === v} onClick={() => setExaggeration(v)}>{v}× vertical</button>)}
            </div>
            {heightmap.loading && <div className="viewer-placeholder">Loading terrain grid…</div>}
            {heightmap.error && <div className="viewer-placeholder">Terrain grid unavailable: {heightmap.error}.</div>}
            {heightmap.data && (!compare || refHeightmap.data) && (
              <TerrainView maps={compare && refHeightmap.data ? [heightmap.data, refHeightmap.data] : [heightmap.data]} exaggeration={exaggeration}
                label={`3D terrain of the ${site.name} study area${compare ? ` beside ${refName}` : ""}, ${exaggeration} times vertical exaggeration`} />
            )}
            {heightmap.data && compare && refHeightmap.loading && <div className="viewer-placeholder">Loading {refName} terrain…</div>}
            {heightmap.data && (
              <p className="viewer-caption">
                <span>{site.name}: {num(heightmap.data.relative_min_m, "m", 0)} to +{num(heightmap.data.relative_max_m, "m", 0)} around the window median</span>
                {compare && refHeightmap.data && <span>{refName}: {num(refHeightmap.data.relative_min_m, "m", 0)} to +{num(refHeightmap.data.relative_max_m, "m", 0)}</span>}
                <span>10 km · {heightmap.data.resolution_m} m grid · {exaggeration}× vertical</span>
                <span>same DEM as the index</span>
                {compare && <span>both surfaces share one vertical scale</span>}
              </p>
            )}
          </>
        )}

        {near && activeMode === "globe" && (
          <>
            <div className={compare && reference ? "pair" : "single"}>
              <GlobeView body={site.body} latitude={site.latitude} longitude={site.longitude} label={`${GLOBE_TEXTURES[site.body].credit} globe with a marker at ${site.name}`} />
              {compare && reference && <GlobeView body={reference.body} latitude={reference.latitude} longitude={reference.longitude} markerColor="#e07a52" label={`${reference.body === "moon" ? "Moon" : "Mars"} globe with a marker at ${refName}`} />}
            </div>
            <p className="viewer-caption">
              <span>Orientation only</span>
              <span>{GLOBE_TEXTURES[site.body].credit} ({GLOBE_TEXTURES[site.body].note})</span>
              {compare && reference && <span>{GLOBE_TEXTURES[reference.body].credit}</span>}
              <span>Global mosaics, not live imagery and not observations of the study area</span>
            </p>
          </>
        )}
      </div>
    </section>
  );
}
