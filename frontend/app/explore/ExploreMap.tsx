"use client";

import { useEffect, useRef, useState } from "react";
import { Map as MapLibreMap, NavigationControl, ScaleControl, setWorkerUrl } from "maplibre-gl";
import type { GeoJSONSource, Map as MapLibreMapType, StyleSpecification } from "maplibre-gl";
import type { AoiFeature } from "../../lib/api";

setWorkerUrl(new URL("maplibre-gl/dist/maplibre-gl-worker.mjs", import.meta.url).toString());

const ALLOWED_HOSTS = new Set(["tiles.openfreemap.org", "gibs.earthdata.nasa.gov"]);
const SATELLITE: StyleSpecification = {
  version: 8,
  sources: { bm: { type: "raster", tiles: ["https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_ShadedRelief_Bathymetry/default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg"], tileSize: 256, maxzoom: 8, attribution: "NASA Blue Marble via GIBS" } },
  layers: [{ id: "bm", type: "raster", source: "bm" }],
};

export default function ExploreMap({ center, window: square, catalog, onPick }: {
  center: { lat: number; lon: number } | null; window: AoiFeature["geometry"] | null; catalog: AoiFeature[]; onPick: (lat: number, lon: number) => void;
}) {
  const container = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMapType | null>(null);
  const pickRef = useRef(onPick);
  const [style, setStyle] = useState<"map" | "satellite">("map");
  const [ready, setReady] = useState(0);
  const [failed, setFailed] = useState(false);

  useEffect(() => { pickRef.current = onPick; }, [onPick]);

  useEffect(() => {
    if (!container.current) return;
    const map = new MapLibreMap({
      container: container.current,
      style: style === "map" ? "https://tiles.openfreemap.org/styles/liberty" : SATELLITE,
      center: center ? [center.lon, center.lat] : [20, 20], zoom: center ? 8 : 1.4, maxZoom: 13, dragRotate: false, pitchWithRotate: false,
      attributionControl: { compact: true },
      transformRequest: (url) => { try { return ALLOWED_HOSTS.has(new URL(url).hostname) ? { url } : { url: "about:blank" }; } catch { return { url: "about:blank" }; } },
    });
    mapRef.current = map;
    map.addControl(new NavigationControl({ showCompass: false }), "top-right");
    map.addControl(new ScaleControl({ unit: "metric", maxWidth: 120 }), "bottom-left");
    map.on("error", () => setFailed(true));
    map.on("load", () => {
      map.addSource("catalog", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addSource("window", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({ id: "catalog-line", type: "line", source: "catalog", paint: { "line-color": "#8a7448", "line-width": 1.2 } });
      map.addLayer({ id: "window-fill", type: "fill", source: "window", paint: { "fill-color": "#e3c178", "fill-opacity": 0.12 } });
      map.addLayer({ id: "window-line", type: "line", source: "window", paint: { "line-color": "#f3d58f", "line-width": 2.4 } });
      map.on("click", (event) => pickRef.current(Number(event.lngLat.lat.toFixed(4)), Number(event.lngLat.lng.toFixed(4))));
      map.getCanvas().style.cursor = "crosshair";
      setReady((n) => n + 1);
    });
    return () => { map.remove(); mapRef.current = null; };
    // the map is rebuilt only when the base style changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [style]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    (map.getSource("catalog") as GeoJSONSource | undefined)?.setData({ type: "FeatureCollection", features: catalog });
    (map.getSource("window") as GeoJSONSource | undefined)?.setData({ type: "FeatureCollection", features: square ? [{ type: "Feature", geometry: square, properties: {} }] : [] });
    if (square) {
      const ring = square.coordinates[0];
      map.fitBounds([[Math.min(...ring.map((p) => p[0])), Math.min(...ring.map((p) => p[1]))], [Math.max(...ring.map((p) => p[0])), Math.max(...ring.map((p) => p[1]))]], { padding: 120, maxZoom: 10.5, duration: 900 });
    }
  }, [square, catalog, ready]);

  return (
    <div>
      <div className="layer-switch" role="radiogroup" aria-label="Base map">
        <button type="button" role="radio" aria-checked={style === "map"} onClick={() => setStyle("map")}>Map (OpenStreetMap)</button>
        <button type="button" role="radio" aria-checked={style === "satellite"} onClick={() => setStyle("satellite")}>Satellite (NASA Blue Marble)</button>
      </div>
      <div ref={container} className="explore-map" role="application" aria-label="Map. Click to place a 10 km study window; or type coordinates beside the map." />
      {failed && <p className="viewer-inline-note">Some map tiles failed to load. Coordinates can still be typed in the form.</p>}
      <p className="muted small">Map data © OpenStreetMap contributors via OpenFreeMap; satellite base: NASA Blue Marble via GIBS. Brown outlines are already-processed study windows.</p>
    </div>
  );
}
