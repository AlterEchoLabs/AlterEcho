"use client";

import { useState } from "react";
import { api, apiV2, apiV3, resolveApiUrl, safeExternalUrl, type Site } from "../../../lib/api";
import { date, pct } from "../../../lib/format";
import { useKeyed } from "../../../lib/hooks";

export type PlateLayer = "satellite" | "hillshade" | "slope";
const LAYERS: { id: PlateLayer; label: string }[] = [{ id: "satellite", label: "Satellite" }, { id: "hillshade", label: "Hillshade" }, { id: "slope", label: "Slope" }];
const pretty = (iso: string | null | undefined) => (iso ? new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }) : "date not recorded");

/**
 * The selected site's 10 km study window as a still plate: the cached, dated Sentinel-2 crop (or the hillshade and slope of the
 * scoring DEM) served by the AlterEcho API. It needs no third-party map tiles, so it always renders. The image is the exact
 * analysis window, north up, so its frame is the window boundary.
 */
export default function StudyPlate({ site, layer: wanted, onLayer, detailed }: { site: Site; layer: PlateLayer; onLayer: (layer: PlateLayer) => void; detailed: boolean }) {
  const win = useKeyed(site.aoi_id ? site.id : null, apiV3.explorer);
  const records = useKeyed(detailed && site.aoi_id ? site.id : null, api.imagery);
  const layerMeta = useKeyed(detailed && site.aoi_id && wanted !== "satellite" ? site.id : null, apiV2.layers);
  const [failed, setFailed] = useState<PlateLayer[]>([]);
  const [loaded, setLoaded] = useState<string[]>([]);
  const [lastShown, setLastShown] = useState<string | null>(null);
  const data = win.data;

  const srcOf = (id: PlateLayer) => {
    const item = id === "satellite" ? data?.imagery : id === "hillshade" ? data?.hillshade : data?.slope;
    return item ? resolveApiUrl(item.url) : null;
  };
  const usable = (id: PlateLayer) => Boolean(srcOf(id)) && !failed.includes(id);
  // Satellite missing or broken: fall back to the hillshade of the same window, and say so.
  const layer: PlateLayer = usable(wanted) ? wanted : (["hillshade", "slope", "satellite"] as PlateLayer[]).find(usable) ?? wanted;
  const fellBack = data && layer !== wanted;
  const active = srcOf(layer);
  const shown = active && loaded.includes(active) ? active : lastShown;
  const stack = [...new Set([lastShown, active].filter((s): s is string => Boolean(s)))];
  const crop = records.data?.find((r) => r.mode === "reference" && r.data_status === "available") ?? null;
  const sourceLink = safeExternalUrl(data?.imagery?.source_url ?? null);

  if (!site.aoi_id) return null;
  const altOf = (id: PlateLayer) => id === "satellite"
    ? `Sentinel-2 true-colour image of the ${site.name} study area, 10 km across, north up`
    : `${id} of the ${site.name} study area from the scoring elevation model, 10 km across`;

  return (
    <figure className="study-plate" data-testid="study-plate" data-layer={layer}>
      <div className="plate-bar">
        <div className="layer-switch" role="radiogroup" aria-label="Study window layer">
          {LAYERS.map((l) => (
            <button key={l.id} type="button" role="radio" aria-checked={layer === l.id} disabled={!usable(l.id)} data-testid={`plate-${l.id}`}
              onClick={() => { setLastShown(shown); onLayer(l.id); }}>{l.label}</button>
          ))}
        </div>
      </div>
      <div className="plate-frame">
        {stack.map((src) => {
          const id = (LAYERS.find((l) => srcOf(l.id) === src)?.id ?? layer) as PlateLayer;
          return (
            // eslint-disable-next-line @next/next/no-img-element
            <img key={src} src={src} alt={src === active ? altOf(id) : ""} aria-hidden={src === active ? undefined : true} width={1000} height={1000}
              decoding="async" fetchPriority={src === active ? "high" : "low"} className={src === shown ? "is-shown" : ""}
              onLoad={() => setLoaded((l) => (l.includes(src) ? l : [...l, src]))}
              onError={() => setFailed((f) => (f.includes(id) ? f : [...f, id]))} />
          );
        })}
        {!shown && !win.error && <span className="plate-wait" aria-hidden="true" />}
        {win.error && <p className="plate-error" role="alert">The study-window image could not be loaded ({win.error}).</p>}
        <span className="plate-boundary" aria-hidden="true" />
        <span className="plate-tag" aria-hidden="true">10 km study window</span>
        <span className="plate-north" aria-hidden="true">N ↑</span>
        <span className="plate-scale" aria-hidden="true"><i />2 km</span>
      </div>
      <figcaption className="plate-caption" data-testid="plate-caption">
        {fellBack && <span className="plate-note">{failed.includes("satellite") ? "The satellite image could not be loaded" : "No satellite crop has been processed for this site"}; showing the elevation hillshade of the same window.</span>}
        {layer === "satellite" && data?.imagery && (
          <span>Sentinel-2 true colour · acquired {pretty(data.imagery.acquired)} · {data.imagery.resolution_m} m pixels · {data.imagery.attribution}</span>
        )}
        {layer === "hillshade" && data?.hillshade && <span>Hillshade · {data.hillshade.source} · light {data.hillshade.light.replace(" deg azimuth", "°").replace(" deg altitude", "° high")} · {data.hillshade.resolution_m} m grid</span>}
        {layer === "slope" && data?.slope && <span>Slope · dark is flat, light is 35° or steeper ({data.slope.ramp}) · {data.slope.resolution_m} m grid</span>}
        <span className="muted">Gold frame: exact 10 km analysis window. A view of the landscape, not evidence of a match; the index uses the elevation model only.</span>
      </figcaption>
      {detailed && (
        <div className="plate-legend" data-testid="plate-legend">
          {layer === "satellite" && crop && (
            <dl>
              <dt>Acquired</dt><dd>{date(crop.acquisition_datetime)}</dd>
              <dt>Pixel size</dt><dd>{crop.display_resolution_m ?? crop.resolution_m} m (source {crop.resolution_m} m)</dd>
              {crop.aoi_coverage_fraction != null && <><dt>Footprint coverage</dt><dd>{pct(crop.aoi_coverage_fraction)} <span className="muted">(share of the window inside the scene, not clear sky)</span></dd></>}
              {crop.cloud_cover_pct != null && <><dt>Scene cloud</dt><dd>{crop.cloud_cover_pct < 0.01 ? "< 0.01" : crop.cloud_cover_pct.toFixed(2)} % <span className="muted">(catalog value for the whole ~110 km tile)</span></dd></>}
              <dt>AOI cloud</dt><dd>{crop.aoi_cloud_fraction == null ? "not calculated" : `${pct(crop.aoi_cloud_fraction, 1)} (SCL band over the window)`}</dd>
              {crop.aoi_snow_fraction != null && <><dt>AOI snow</dt><dd>{pct(crop.aoi_snow_fraction, 1)}</dd></>}
              <dt>Product</dt><dd className="mono break">{crop.product_id ?? "not recorded"}</dd>
              <dt>Provider</dt><dd>{crop.provider}</dd>
              {crop.preview_checksum && <><dt>Image SHA-256</dt><dd className="mono break">{crop.preview_checksum}</dd></>}
            </dl>
          )}
          {layer !== "satellite" && (
            <dl>
              <dt>Grid</dt><dd>30 m over the exact window, from the same DEM as the index (the index itself uses 60 m)</dd>
              {layer === "hillshade" ? <><dt>Light</dt><dd>from the north-west (315°), 45° high</dd></> : <><dt>Ramp</dt><dd>dark = flat, light = 35° or steeper; identical for every site</dd></>}
              {layerMeta.data && <><dt>Median slope (30 m)</dt><dd className="mono">{layerMeta.data.slope_p50_deg.toFixed(1)}°</dd><dt>DEM SHA-256</dt><dd className="mono break">{layerMeta.data.source_sha256}</dd></>}
            </dl>
          )}
          {layer === "slope" && <div className="slope-ramp" aria-hidden="true"><span>0°</span><i /><span>35°+</span></div>}
          {site.id === "earth-atacama" && <p className="muted small">This first Atacama window contains a large industrial complex whose graded ground would look artificially flat. It is not scored; the Atacama Desert window 8 km south, free of built structures, is used instead.</p>}
          {sourceLink && layer === "satellite" && <p className="small"><a href={sourceLink} target="_blank" rel="noreferrer noopener">Source record</a></p>}
        </div>
      )}
    </figure>
  );
}
