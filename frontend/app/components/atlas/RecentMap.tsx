"use client";

import { useEffect, useRef, useState } from "react";
import { Map as MapLibreMap, NavigationControl, ScaleControl, setWorkerUrl } from "maplibre-gl";
import type { AoiFeature } from "../../../lib/api";

setWorkerUrl(new URL("maplibre-gl/dist/maplibre-gl-worker.mjs", import.meta.url).toString());

// Tile templates come from API metadata; only the NASA GIBS host is ever requested.
const ALLOWED_TILE_HOST = "gibs.earthdata.nasa.gov";

export default function RecentMap({ aoi, tileUrl, attribution, label }: { aoi: AoiFeature; tileUrl: string; attribution: string; label: string }) {
  const container = useRef<HTMLDivElement | null>(null);
  const [failed, setFailed] = useState(false);
  const allowed = (() => { try { const u = new URL(tileUrl.replace(/\{[xyz]\}/g, "0")); return u.protocol === "https:" && u.hostname === ALLOWED_TILE_HOST; } catch { return false; } })();

  useEffect(() => {
    if (!container.current || !allowed) return;
    const ring = aoi.geometry.coordinates[0];
    const xs = ring.map((p) => p[0]), ys = ring.map((p) => p[1]);
    const map = new MapLibreMap({
      container: container.current,
      style: {
        version: 8,
        sources: { recent: { type: "raster", tiles: [tileUrl], tileSize: 256, maxzoom: 9, attribution } },
        layers: [{ id: "recent", type: "raster", source: "recent" }],
      },
      bounds: [[Math.min(...xs), Math.min(...ys)], [Math.max(...xs), Math.max(...ys)]],
      fitBoundsOptions: { padding: 40, maxZoom: 9 },
      maxZoom: 10, dragRotate: false, pitchWithRotate: false, attributionControl: { compact: true },
      transformRequest: (url) => (new URL(url).hostname === ALLOWED_TILE_HOST ? { url } : { url: "about:blank" }),
    });
    map.addControl(new NavigationControl({ showCompass: false }), "top-right");
    map.addControl(new ScaleControl({ unit: "metric", maxWidth: 120 }), "bottom-left");
    map.on("load", () => {
      map.addSource("aoi", { type: "geojson", data: aoi });
      map.addLayer({ id: "aoi-line", type: "line", source: "aoi", paint: { "line-color": "#e3c178", "line-width": 2 } });
    });
    map.on("error", () => setFailed(true));
    return () => map.remove();
  }, [aoi, tileUrl, attribution, allowed]);

  if (!allowed) return <div className="viewer-placeholder">Recent-context tiles are not from an approved provider and were not loaded.</div>;
  return (
    <div className="recent-map-wrap">
      <div ref={container} className="recent-map" role="region" aria-label={label} />
      {failed && <p className="viewer-inline-note">Some recent-context tiles failed to load. The detailed reference and terrain views do not depend on this service.</p>}
    </div>
  );
}
