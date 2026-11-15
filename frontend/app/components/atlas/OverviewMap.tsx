"use client";

import { useEffect, useRef, useState } from "react";
import { Map as MapLibreMap, NavigationControl, setWorkerUrl } from "maplibre-gl";
import type { GeoJSONSource, Map as MapLibreMapType } from "maplibre-gl";
import { api, type AoiFeature, type Site } from "../../../lib/api";
import { useReducedMotion } from "../../../lib/hooks";

setWorkerUrl(new URL("maplibre-gl/dist/maplibre-gl-worker.mjs", import.meta.url).toString());

const BLUE_MARBLE = "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_ShadedRelief_Bathymetry/default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg";

export default function OverviewMap({ sites, selectedId, onSelect }: { sites: Site[]; selectedId: string | null; onSelect: (id: string) => void }) {
  const container = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMapType | null>(null);
  const onSelectRef = useRef(onSelect);
  const [aois, setAois] = useState<AoiFeature[]>([]);
  const [failed, setFailed] = useState(false);
  const [ready, setReady] = useState(false);
  const reduced = useReducedMotion();
  const earth = sites.filter((s) => s.body === "earth");

  useEffect(() => { onSelectRef.current = onSelect; }, [onSelect]);

  useEffect(() => {
    let active = true;
    Promise.allSettled(earth.filter((s) => s.aoi_id).map((s) => api.aoi(s.id))).then((items) => {
      if (active) setAois(items.flatMap((i) => (i.status === "fulfilled" ? [i.value] : [])));
    });
    return () => { active = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [earth.length]);

  useEffect(() => {
    if (!container.current || mapRef.current) return;
    const map = new MapLibreMap({
      container: container.current,
      style: { version: 8, sources: { bm: { type: "raster", tiles: [BLUE_MARBLE], tileSize: 256, maxzoom: 8, attribution: "NASA Blue Marble via GIBS" } }, layers: [{ id: "bm", type: "raster", source: "bm" }] },
      center: [20, 15], zoom: 0.6, minZoom: 0.4, maxZoom: 11, attributionControl: { compact: true }, dragRotate: false, pitchWithRotate: false,
      transformRequest: (url) => (new URL(url).hostname === "gibs.earthdata.nasa.gov" ? { url } : { url: "about:blank" }),
    });
    mapRef.current = map;
    map.addControl(new NavigationControl({ showCompass: false }), "top-right");
    map.on("error", () => setFailed(true));
    map.on("load", () => {
      map.addSource("aois", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addSource("sites", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({ id: "aoi-line", type: "line", source: "aois", paint: { "line-color": ["case", ["==", ["get", "selected"], true], "#f3d58f", "#e3c178"], "line-width": ["case", ["==", ["get", "selected"], true], 2.5, 1.2] } });
      map.addLayer({ id: "site-dot", type: "circle", source: "sites", paint: {
        "circle-radius": ["case", ["==", ["get", "selected"], true], 7, 5], "circle-color": ["case", ["==", ["get", "measured"], true], "#e3c178", "#7d7a73"],
        "circle-stroke-color": "#0d1117", "circle-stroke-width": 1.5 } });
      map.on("click", "site-dot", (event) => { const id = event.features?.[0]?.properties?.id; if (id) onSelectRef.current(String(id)); });
      map.on("mouseenter", "site-dot", () => { map.getCanvas().style.cursor = "pointer"; });
      map.on("mouseleave", "site-dot", () => { map.getCanvas().style.cursor = ""; });
      setReady(true);
    });
    return () => { map.remove(); mapRef.current = null; };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    {
      (map.getSource("sites") as GeoJSONSource | undefined)?.setData({ type: "FeatureCollection", features: earth.map((s) => ({
        type: "Feature", geometry: { type: "Point", coordinates: [s.longitude, s.latitude] },
        properties: { id: s.id, measured: s.data_status === "real_processed", selected: s.id === selectedId } })) });
      (map.getSource("aois") as GeoJSONSource | undefined)?.setData({ type: "FeatureCollection", features: aois.map((a) => ({ ...a, properties: { ...a.properties, selected: a.properties.site_id === selectedId } })) });
      const selected = aois.find((a) => a.properties.site_id === selectedId);
      if (selected) {
        const ring = selected.geometry.coordinates[0];
        map.fitBounds([[Math.min(...ring.map((p) => p[0])), Math.min(...ring.map((p) => p[1]))], [Math.max(...ring.map((p) => p[0])), Math.max(...ring.map((p) => p[1]))]],
          { padding: 70, maxZoom: 8.5, duration: reduced ? 0 : 1400 });
      }
    }
  }, [earth, aois, selectedId, reduced, ready]);

  return (
    <div className="overview-map-wrap">
      <div ref={container} className="overview-map" role="region" aria-label="Map of Earth study windows; select a marker to open a site" />
      {failed && <p className="viewer-inline-note">Some base-map tiles failed to load. The list below works without the map.</p>}
      <p className="map-legend"><span className="legend-measured" /> measured 10 km window <span className="legend-planned" /> not measured yet</p>
    </div>
  );
}
