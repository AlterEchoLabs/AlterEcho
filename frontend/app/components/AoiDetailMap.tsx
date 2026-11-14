"use client";

import { memo, useEffect, useRef } from "react";
import { Map as MapLibreMap, NavigationControl, setWorkerUrl } from "maplibre-gl";
import type { Map as MapLibreMapType } from "maplibre-gl";
import type { AoiFeature } from "../../lib/api";

setWorkerUrl(new URL("maplibre-gl/dist/maplibre-gl-worker.mjs", import.meta.url).toString());

function AoiDetailMap({ aoi, tileUrl, label }: { aoi: AoiFeature; tileUrl: string; label: string }) {
  const container = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMapType | null>(null);
  useEffect(() => {
    if (!container.current) return;
    const coordinates = aoi.geometry.coordinates[0];
    const west = Math.min(...coordinates.map((point) => point[0]));
    const east = Math.max(...coordinates.map((point) => point[0]));
    const south = Math.min(...coordinates.map((point) => point[1]));
    const north = Math.max(...coordinates.map((point) => point[1]));
    const map = new MapLibreMap({
      container: container.current,
      style: { version: 8, sources: { observation: { type: "raster", tiles: [tileUrl], tileSize: 256, attribution: "NASA Worldview / GIBS" } }, layers: [{ id: "observation", type: "raster", source: "observation" }] },
      bounds: [[west, south], [east, north]], fitBoundsOptions: { padding: 28, maxZoom: 9 }, maxZoom: 9,
      attributionControl: { compact: true }, dragRotate: false, pitchWithRotate: false,
    });
    mapRef.current = map; map.addControl(new NavigationControl({ showCompass: true }), "top-right");
    map.on("load", () => {
      map.addSource("study-aoi", { type: "geojson", data: aoi });
      map.addLayer({ id: "study-aoi-fill", type: "fill", source: "study-aoi", paint: { "fill-color": "#f59e0b", "fill-opacity": 0.06 } });
      map.addLayer({ id: "study-aoi-line", type: "line", source: "study-aoi", paint: { "line-color": "#fbbf24", "line-width": 3, "line-dasharray": [2, 2] } });
    });
    return () => { map.remove(); mapRef.current = null; };
  }, [aoi, tileUrl]);
  return <div ref={container} className="aoi-detail-map" role="img" aria-label={label} />;
}

export default memo(AoiDetailMap);
