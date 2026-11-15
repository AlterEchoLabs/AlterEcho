"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Map as MapLibreMap, NavigationControl, ScaleControl, setWorkerUrl } from "maplibre-gl";
import type { GeoJSONSource, ImageSource, LngLatBoundsLike, Map as MapType } from "maplibre-gl";
import { apiV3, resolveApiUrl, type Site } from "../../../lib/api";
import type { ExplorerWindow } from "../../../lib/analogue";
import { date } from "../../../lib/format";
import { useKeyed, useReducedMotion } from "../../../lib/hooks";

setWorkerUrl(new URL("maplibre-gl/dist/maplibre-gl-worker.mjs", import.meta.url).toString());

const BLUE_MARBLE = "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_ShadedRelief_Bathymetry/default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg";
type LayerId = "satellite" | "hillshade" | "slope";
const API_ORIGIN = (() => { try { return new URL(resolveApiUrl("/api/health") ?? "http://localhost:8000").origin; } catch { return ""; } })();

function bounds(corners: [number, number][]): LngLatBoundsLike {
  const lons = corners.map((c) => c[0]), lats = corners.map((c) => c[1]);
  return [[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]];
}

function groundResolution(zoom: number, latitude: number) {
  return (156_543.03 * Math.cos((latitude * Math.PI) / 180)) / 2 ** zoom;
}

/**
 * Earth explorer: a MapLibre globe that flies to the study window and swaps to the real georeferenced
 * 10 m Sentinel-2 crop (or the DEM hillshade/slope) inside the exact analysis-grid boundary. The global
 * mosaic is never stretched into fake local detail: zoom stops half a level past the crop's native 10 m.
 */
export default function SiteExplorer({ site }: { site: Site }) {
  const container = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapType | null>(null);
  const [ready, setReady] = useState(false);
  const [layer, setLayer] = useState<LayerId>("satellite");
  const [recent, setRecent] = useState(false);
  const [zoom, setZoom] = useState(1.4);
  const [busy, setBusy] = useState(true);
  const [failed, setFailed] = useState(false);
  const reduced = useReducedMotion();
  const win = useKeyed(site.aoi_id ? site.id : null, apiV3.explorer);
  const data: ExplorerWindow | null = win.data;
  const maxZoom = data ? data.max_native_zoom + 0.5 : 14;

  useEffect(() => {
    if (!container.current || mapRef.current) return;
    const map = new MapLibreMap({
      container: container.current,
      style: {
        version: 8, projection: { type: "globe" },
        sources: { bm: { type: "raster", tiles: [BLUE_MARBLE], tileSize: 256, maxzoom: 8, attribution: "NASA Blue Marble (2004 composite) via GIBS" } },
        layers: [{ id: "space", type: "background", paint: { "background-color": "#0b0f14" } }, { id: "bm", type: "raster", source: "bm" }],
      },
      center: [site.longitude, site.latitude], zoom: 1.4, minZoom: 0.6, maxZoom: 14, attributionControl: { compact: true },
      transformRequest: (url) => {
        const host = new URL(url, window.location.href);
        return host.hostname === "gibs.earthdata.nasa.gov" || host.origin === API_ORIGIN ? { url } : { url: "about:blank" };
      },
    });
    mapRef.current = map;
    map.addControl(new NavigationControl({ visualizePitch: false }), "top-right");
    map.addControl(new ScaleControl({ unit: "metric", maxWidth: 120 }), "bottom-left");
    map.on("zoom", () => setZoom(map.getZoom()));
    map.on("dataloading", () => setBusy(true));
    map.on("idle", () => setBusy(false));
    map.on("error", () => setFailed(true));
    map.once("style.load", () => setReady(true));
    return () => { map.remove(); mapRef.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const fit = useCallback((animate: boolean) => {
    const map = mapRef.current;
    if (!map || !data) return;
    map.fitBounds(bounds(data.aoi_corners), { padding: 36, maxZoom: data.max_native_zoom - 0.6, duration: animate && !reduced ? 2800 : 0, essential: false });
  }, [data, reduced]);

  const world = useCallback(() => {
    const map = mapRef.current;
    if (!map) return;
    map.flyTo({ center: [site.longitude, site.latitude], zoom: 1.4, duration: reduced ? 0 : 1600 });
  }, [site.longitude, site.latitude, reduced]);

  // Overlays for this site: exact grid corners from the API, never estimated in the browser.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready || !data) return;
    map.setMaxZoom(maxZoom);
    const ring = [...data.aoi_corners, data.aoi_corners[0]];
    const overlays: [string, { url: string; corners: [number, number][] } | null][] = [["satellite", data.imagery], ["hillshade", data.hillshade], ["slope", data.slope]];
    for (const [id, item] of overlays) {
      if (!item) continue;
      const url = resolveApiUrl(item.url);
      if (!url) continue;
      const src = map.getSource(`ov-${id}`) as ImageSource | undefined;
      const coordinates = item.corners as [[number, number], [number, number], [number, number], [number, number]];
      if (src) src.updateImage({ url, coordinates });
      else {
        map.addSource(`ov-${id}`, { type: "image", url, coordinates });
        map.addLayer({ id: `ov-${id}`, type: "raster", source: `ov-${id}`, paint: { "raster-opacity": 1, "raster-fade-duration": reduced ? 0 : 300, "raster-resampling": "linear" } });
      }
    }
    if (data.recent && !map.getSource("recent")) {
      map.addSource("recent", { type: "raster", tiles: [data.recent.tile_url], tileSize: 256, maxzoom: 9, attribution: `${data.recent.attribution} (${date(data.recent.observed)})` });
      map.addLayer({ id: "recent", type: "raster", source: "recent", layout: { visibility: "none" } }, map.getLayer("ov-satellite") ? "ov-satellite" : undefined);
    }
    const aoi = { type: "Feature" as const, geometry: { type: "Polygon" as const, coordinates: [ring] }, properties: {} };
    const existing = map.getSource("aoi") as GeoJSONSource | undefined;
    if (existing) existing.setData(aoi);
    else {
      map.addSource("aoi", { type: "geojson", data: aoi });
      map.addLayer({ id: "aoi-halo", type: "line", source: "aoi", paint: { "line-color": "#0b0f14", "line-width": 5, "line-opacity": 0.55 } });
      map.addLayer({ id: "aoi-line", type: "line", source: "aoi", paint: { "line-color": "#f3d58f", "line-width": 2 } });
    }
    map.jumpTo({ center: data.center, zoom: 1.4 });
    const timer = window.setTimeout(() => fit(true), reduced ? 0 : 350);
    return () => window.clearTimeout(timer);
  }, [ready, data, maxZoom, reduced, fit]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    for (const id of ["satellite", "hillshade", "slope"] as LayerId[]) {
      if (map.getLayer(`ov-${id}`)) map.setLayoutProperty(`ov-${id}`, "visibility", id === layer ? "visible" : "none");
    }
    if (map.getLayer("recent")) map.setLayoutProperty("recent", "visibility", recent ? "visible" : "none");
  }, [layer, recent, ready, data]);

  const res = data ? groundResolution(zoom, data.center[1]) : null;
  const active = layer === "satellite" ? data?.imagery : layer === "hillshade" ? data?.hillshade : data?.slope;
  const detailText = useMemo(() => {
    if (!data || res == null) return "";
    if (zoom < 7) return "Global orientation mosaic (NASA Blue Marble, ~500 m and coarser). Zoom in or fit the study window.";
    const native = active?.resolution_m ?? 10;
    return res < native ? `Display ${res.toFixed(1)} m per pixel; the ${native} m source has no finer detail (zoom is capped).` : `Display ${res.toFixed(0)} m per pixel · source ${native} m inside the window`;
  }, [data, res, zoom, active]);

  return (
    <div className="explorer" data-testid="site-explorer">
      <div className="explorer-bar">
        <div className="layer-switch" role="radiogroup" aria-label="Explorer layer">
          <button type="button" role="radio" aria-checked={layer === "satellite"} disabled={!data?.imagery} onClick={() => setLayer("satellite")}>Satellite 10 m</button>
          <button type="button" role="radio" aria-checked={layer === "hillshade"} disabled={!data?.hillshade} onClick={() => setLayer("hillshade")}>Hillshade</button>
          <button type="button" role="radio" aria-checked={layer === "slope"} disabled={!data?.slope} onClick={() => setLayer("slope")}>Slope</button>
        </div>
        <label className="toggle"><input type="checkbox" checked={recent} disabled={!data?.recent} onChange={(e) => setRecent(e.target.checked)} /><span>Latest {data?.recent ? `${Math.round(data.recent.resolution_m)} m` : ""} context around the window</span></label>
        <div className="explorer-actions">
          <button type="button" className="text-button" onClick={() => fit(true)} disabled={!data} data-testid="fit-aoi">Fit study window</button>
          <button type="button" className="text-button" onClick={world}>Whole Earth</button>
        </div>
      </div>
      <div className="explorer-stage">
        <div ref={container} className="explorer-map" role="region" aria-label={`Interactive globe and map of the ${site.name} study window. Use arrow keys to pan and plus or minus to zoom.`} tabIndex={0} />
        {(busy || win.loading) && <div className="explorer-loading" aria-live="polite"><span className="spinner" aria-hidden="true" /> Loading imagery…</div>}
        {win.error && <div className="explorer-overlay-note" role="alert">Study-window imagery is unavailable ({win.error}). The globe still works.</div>}
        {failed && <div className="explorer-overlay-note">Some map tiles failed to load; the window overlay and results are unaffected.</div>}
      </div>
      <p className="viewer-caption" data-testid="explorer-caption">
        <span>Zoom {zoom.toFixed(1)} · {detailText}</span>
        {layer === "satellite" && data?.imagery && <span>Sentinel-2 L2A {date(data.imagery.acquired)} · {data.imagery.product_id}</span>}
        {layer !== "satellite" && data?.hillshade && <span>{data.hillshade.source} · {layer === "hillshade" ? data.hillshade.light : data.slope?.ramp}</span>}
        {recent && data?.recent && <span>VIIRS {date(data.recent.observed)} (latest available, not live)</span>}
        <span>Gold line: exact 10 km analysis boundary · north up</span>
      </p>
    </div>
  );
}
