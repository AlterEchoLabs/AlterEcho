"use client";

import dynamic from "next/dynamic";
import { useId, useState, type KeyboardEvent } from "react";
import { api, apiV2, resolveApiUrl, safeExternalUrl, type ImageryRecord, type Site } from "../../../lib/api";
import { date, num, pct } from "../../../lib/format";
import { useKeyed } from "../../../lib/hooks";
import { GLOBE_TEXTURES } from "./GlobeView";
import type { ReferenceV3 } from "../../../lib/analogue";
import SyncedCompare from "./SyncedCompare";

const GlobeView = dynamic(() => import("./GlobeView"), { ssr: false, loading: () => <div className="viewer-placeholder">Loading globe…</div> });
const TerrainView = dynamic(() => import("./TerrainView"), { ssr: false, loading: () => <div className="viewer-placeholder">Loading terrain…</div> });
const RecentMap = dynamic(() => import("./RecentMap"), { ssr: false, loading: () => <div className="viewer-placeholder">Loading map…</div> });
const SiteExplorer = dynamic(() => import("./SiteExplorer"), { ssr: false, loading: () => <div className="viewer-placeholder">Loading explorer…</div> });

type Mode = "explore" | "compare" | "satellite" | "elevation" | "terrain" | "globe";
type Layer = "detailed" | "recent";
const MODES: { id: Mode; label: string }[] = [{ id: "explore", label: "Explore map" }, { id: "compare", label: "Compare with reference" }, { id: "satellite", label: "Image + details" }, { id: "elevation", label: "Elevation" }, { id: "terrain", label: "3D terrain" }];
const EXAGGERATIONS = [1, 2, 4];
const TODAY = new Date("2026-11-14T00:00:00Z");

function ageText(value: string | null | undefined): string {
  if (!value) return "";
  const days = Math.round((TODAY.getTime() - new Date(value).getTime()) / 86_400_000);
  if (days < 45) return `${days} days before this build`;
  return `about ${Math.round(days / 30.4)} months before this build`;
}

function detailedOf(records: ImageryRecord[] | null) {
  return records?.find((r) => r.mode === "reference" && r.data_status === "available" && r.preview_url) ?? null;
}

function Plate({ src, alt, tag }: { src: string | null; alt: string; tag: string }) {
  if (!src) return <div className="viewer-placeholder">Preview not available.</div>;
  return (
    <figure className="image-panel">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={src} alt={alt} loading="lazy" decoding="async" onLoad={(e) => e.currentTarget.classList.add("is-loaded")} />
      <span className="image-scale" aria-hidden="true"><i style={{ width: "20%" }} />2 km</span>
      <span className="image-north" aria-hidden="true">N</span>
      <figcaption className="image-tag">{tag}</figcaption>
    </figure>
  );
}

function Legend({ record, site }: { record: ImageryRecord; site: Site }) {
  const link = safeExternalUrl(record.official_source_url);
  const earth = record.body === "earth";
  return (
    <div className="plate-legend">
      <h3>{earth ? "Sentinel-2 true colour" : "CTX orthomosaic"}</h3>
      <dl>
        <dt>{earth ? "Acquired" : "Mosaic published"}</dt><dd>{date(earth ? record.acquisition_datetime : record.publication_datetime ?? record.acquisition_datetime)}{earth && <span className="muted"> · {ageText(record.acquisition_datetime)}</span>}</dd>
        <dt>Pixel size</dt><dd>{record.display_resolution_m ?? record.resolution_m} m (source {record.resolution_m} m)</dd>
        <dt>Window</dt><dd>Exact 10 km study window, north up, same grid as the terrain analysis</dd>
        {record.aoi_coverage_fraction != null && <><dt>Footprint coverage</dt><dd>{pct(record.aoi_coverage_fraction)} <span className="muted">(share of the window inside the scene, not clear sky)</span></dd></>}
        {earth && record.cloud_cover_pct != null && <><dt>Scene cloud</dt><dd>{record.cloud_cover_pct < 0.01 ? "< 0.01" : record.cloud_cover_pct.toFixed(2)} % <span className="muted">(catalog value for the whole ~110 km tile)</span></dd></>}
        {earth && <><dt>AOI cloud</dt><dd>{record.aoi_cloud_fraction == null ? "not calculated" : `${pct(record.aoi_cloud_fraction, 1)} (SCL band over the window)`}</dd></>}
        {earth && record.aoi_snow_fraction != null && <><dt>AOI snow</dt><dd>{pct(record.aoi_snow_fraction, 1)}</dd></>}
        <dt>Product</dt><dd className="mono break">{record.product_id ?? "not recorded"}</dd>
        <dt>Provider</dt><dd>{record.provider}</dd>
      </dl>
      <p className="muted small">A view of the landscape, not evidence of a match. The index uses the elevation model only.</p>
      {site.id === "earth-atacama" && <p className="muted small">This original window contains a large industrial complex. It is excluded from analogue-method-v1.0 and replaced by the Atacama south window.</p>}
      {link && <p className="small"><a href={link} target="_blank" rel="noreferrer noopener">Source record</a> · {record.attribution}</p>}
    </div>
  );
}

export default function SiteViewer({ site, reference, referenceInfo }: { site: Site; reference: Site | null; referenceInfo?: ReferenceV3 | null }) {
  const [mode, setMode] = useState<Mode>("explore");
  const [layer, setLayer] = useState<Layer>("detailed");
  const [elevation, setElevation] = useState<"hillshade" | "slope">("hillshade");
  const [compare, setCompare] = useState(false);
  const [exaggeration, setExaggeration] = useState(2);
  const tabsId = useId();
  const measured = site.data_status === "real_processed";

  const imagery = useKeyed(measured ? site.id : null, api.imagery);
  const aoi = useKeyed(site.aoi_id ? site.id : null, api.aoi);
  const refImagery = useKeyed(compare && reference?.body === "mars" ? reference.id : null, api.imagery);
  const layers = useKeyed(measured && mode === "elevation" ? site.id : null, apiV2.layers);
  const heightmap = useKeyed(measured && mode === "terrain" ? site.id : null, api.heightmap);
  const refHeightmap = useKeyed(compare && mode === "terrain" && reference ? reference.id : null, api.heightmap);

  const detailed = detailedOf(imagery.data);
  const recent = imagery.data?.find((r) => r.mode === "latest_observation" && r.tile_url) ?? null;
  const refDetailed = detailedOf(refImagery.data);
  const activeLayer: Layer = layer === "detailed" && !detailed && recent ? "recent" : layer;
  const available: { id: Mode; label: string }[] = measured && site.body === "earth" ? MODES : [{ id: "globe", label: "Globe (orientation)" }];
  const activeMode: Mode = available.some((m) => m.id === mode) ? mode : "globe";
  const refName = reference?.name ?? "reference";
  const refLayer = (kind: string) => reference ? resolveApiUrl(`/api/sites/${reference.id}/terrain/layers/${kind}.png`) : null;

  const onTabKey = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
    event.preventDefault();
    const i = available.findIndex((m) => m.id === activeMode);
    const next = available[(i + (event.key === "ArrowRight" ? 1 : available.length - 1)) % available.length];
    setMode(next.id);
    document.getElementById(`${tabsId}-${next.id}`)?.focus();
  };

  return (
    <section className="viewer" aria-label={`${site.name} viewer`} data-testid="site-viewer" data-site-id={site.id}>
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
        {activeMode === "compare" && (
          referenceInfo
            ? <SyncedCompare site={site} reference={referenceInfo} earthImage={detailed?.preview_url ? resolveApiUrl(detailed.preview_url) : null} />
            : <div className="viewer-placeholder">Loading the reference window…</div>
        )}

        {activeMode === "explore" && (
          <div className={compare && reference ? "pair explore-pair" : "single"}>
            <SiteExplorer site={site} />
            {compare && reference && <GlobeView body={reference.body} latitude={reference.latitude} longitude={reference.longitude} markerColor="#e07a52" label={`${reference.body === "moon" ? "Moon" : "Mars"} globe with a marker at ${refName} (orientation only)`} />}
          </div>
        )}
        {activeMode === "satellite" && (
          <>
            <div className="layer-switch" role="radiogroup" aria-label="Imagery layer">
              <button type="button" role="radio" aria-checked={activeLayer === "detailed"} disabled={!detailed} onClick={() => setLayer("detailed")}>Detailed{detailed ? ` · ${date(detailed.acquisition_datetime)}` : ""}</button>
              <button type="button" role="radio" aria-checked={activeLayer === "recent"} disabled={!recent} onClick={() => setLayer("recent")}>Latest available{recent ? ` · ${num(recent.resolution_m, "m", 0)}` : ""}</button>
            </div>
            {imagery.loading && <div className="viewer-placeholder">Loading imagery records…</div>}
            {imagery.error && <div className="viewer-placeholder">Imagery records could not be loaded: {imagery.error}.</div>}
            {imagery.data && activeLayer === "detailed" && detailed && (
              <div className={compare ? "pair" : "plate"}>
                <Plate src={detailed.preview_url ? resolveApiUrl(detailed.preview_url) : null} alt={`Sentinel-2 true-colour crop of the ${site.name} study area, 10 km across, north up`} tag={site.name} />
                {compare && reference ? (
                  reference.body === "mars"
                    ? (refDetailed ? <Plate src={refDetailed.preview_url ? resolveApiUrl(refDetailed.preview_url) : null} alt={`CTX orthomosaic crop of the ${refName} study area, 10 km across, north up`} tag={refName} /> : <div className="viewer-placeholder">Loading {refName}…</div>)
                    : <Plate src={refLayer("hillshade")} alt={`LOLA hillshade of the ${refName} study area, 10 km across`} tag={`${refName} · LOLA hillshade (no orthoimage processed)`} />
                ) : <Legend record={detailed} site={site} />}
              </div>
            )}
            {imagery.data && activeLayer === "recent" && recent && aoi.data && (
              <>
                {!detailed && <p className="viewer-inline-note">No detailed crop has been processed for this site, so the latest available observation is shown.</p>}
                <RecentMap aoi={aoi.data} tileUrl={recent.tile_url!} attribution={recent.attribution} label={`Latest available VIIRS observation around the ${site.name} study area`} />
                <p className="viewer-caption"><span>{recent.provider}</span><span>{recent.product_id}</span><span>observed {date(recent.acquisition_datetime)} (latest available, not live)</span><span>~{recent.resolution_m} m, may be cloudy</span><span>visual context only, never scored</span></p>
              </>
            )}
          </>
        )}

        {activeMode === "elevation" && (
          <>
            <div className="layer-switch" role="radiogroup" aria-label="Elevation layer">
              <button type="button" role="radio" aria-checked={elevation === "hillshade"} onClick={() => setElevation("hillshade")}>Hillshade</button>
              <button type="button" role="radio" aria-checked={elevation === "slope"} onClick={() => setElevation("slope")}>Slope 0–35°</button>
            </div>
            <div className={compare && reference ? "pair" : "plate"}>
              <Plate src={resolveApiUrl(`/api/sites/${site.id}/terrain/layers/${elevation}.png`)} alt={`${elevation} of the ${site.name} study area from the scoring DEM, 10 km across`} tag={`${site.name} · ${elevation}`} />
              {compare && reference ? <Plate src={refLayer(elevation)} alt={`${elevation} of the ${refName} study area`} tag={`${refName} · ${elevation}`} /> : (
                <div className="plate-legend">
                  <h3>{elevation === "hillshade" ? "Hillshade" : "Slope"}</h3>
                  <dl>
                    <dt>Grid</dt><dd>30 m over the exact window, from the same DEM as the index</dd>
                    {elevation === "hillshade" ? <><dt>Light</dt><dd>from the north-west (315°), 45° high</dd></> : <><dt>Ramp</dt><dd>dark = flat, light = 35° or steeper; identical for every site</dd></>}
                    {layers.data && <><dt>Median slope (30 m)</dt><dd className="mono">{layers.data.slope_p50_deg.toFixed(1)}°</dd><dt>DEM SHA-256</dt><dd className="mono break">{layers.data.source_sha256.slice(0, 16)}…</dd></>}
                  </dl>
                  {elevation === "slope" && <div className="slope-ramp" aria-hidden="true"><span>0°</span><i /><span>35°+</span></div>}
                  <p className="muted small">Slopes here use a 30 m grid for display. The index uses the 60 m grid (120 and 240 m as sensitivity checks).</p>
                </div>
              )}
            </div>
          </>
        )}

        {activeMode === "terrain" && (
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

        {activeMode === "globe" && (
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
