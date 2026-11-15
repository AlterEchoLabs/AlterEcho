"use client";

import { useCallback, useEffect, useRef, useState, type KeyboardEvent, type PointerEvent, type WheelEvent } from "react";
import { resolveApiUrl, type Site } from "../../../lib/api";
import type { ReferenceV3 } from "../../../lib/analogue";

type Layer = "image" | "hillshade" | "slope";
const MAX_ZOOM = 4;
const EXTENT_M = 10_000;

/**
 * Earth and reference windows side by side at the same ground scale (both 10 km, north up) with one shared
 * zoom/pan state. Zoom is capped at 4x, where a 10 m source pixel already spans several screen pixels.
 */
export default function SyncedCompare({ site, reference, earthImage }: { site: Site; reference: ReferenceV3; earthImage: string | null }) {
  const [layer, setLayer] = useState<Layer>("image");
  const [view, setView] = useState({ z: 1, x: 0, y: 0 });
  const [width, setWidth] = useState(400);
  const frame = useRef<HTMLDivElement | null>(null);
  const drag = useRef<{ x: number; y: number } | null>(null);

  useEffect(() => {
    const el = frame.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setWidth(el.clientWidth));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const clamp = useCallback((z: number, x: number, y: number) => {
    const lim = (1 - 1 / z) / 2;
    return { z, x: Math.max(-lim, Math.min(lim, x)), y: Math.max(-lim, Math.min(lim, y)) };
  }, []);
  const zoomBy = (factor: number) => setView((v) => clamp(Math.max(1, Math.min(MAX_ZOOM, v.z * factor)), v.x, v.y));
  const onWheel = (e: WheelEvent) => { e.preventDefault(); zoomBy(e.deltaY < 0 ? 1.25 : 0.8); };
  const onDown = (e: PointerEvent) => { drag.current = { x: e.clientX, y: e.clientY }; (e.target as Element).setPointerCapture?.(e.pointerId); };
  const onMove = (e: PointerEvent) => {
    if (!drag.current) return;
    const dx = (e.clientX - drag.current.x) / (width * view.z), dy = (e.clientY - drag.current.y) / (width * view.z);
    drag.current = { x: e.clientX, y: e.clientY };
    setView((v) => clamp(v.z, v.x - dx, v.y - dy));
  };
  const onUp = () => { drag.current = null; };
  const onKey = (e: KeyboardEvent) => {
    const step = 0.08 / view.z;
    const map: Record<string, () => void> = { "+": () => zoomBy(1.25), "=": () => zoomBy(1.25), "-": () => zoomBy(0.8), "0": () => setView({ z: 1, x: 0, y: 0 }),
      ArrowLeft: () => setView((v) => clamp(v.z, v.x - step, v.y)), ArrowRight: () => setView((v) => clamp(v.z, v.x + step, v.y)),
      ArrowUp: () => setView((v) => clamp(v.z, v.x, v.y - step)), ArrowDown: () => setView((v) => clamp(v.z, v.x, v.y + step)) };
    if (map[e.key]) { e.preventDefault(); map[e.key](); }
  };

  const earthSrc = layer === "image" ? earthImage : resolveApiUrl(`/api/sites/${site.id}/terrain/layers/${layer}.png`);
  const refSrc = layer === "image" ? resolveApiUrl(reference.imagery?.url ?? reference.hillshade_url) : resolveApiUrl(layer === "hillshade" ? reference.hillshade_url : reference.slope_url);
  const style = { transform: `scale(${view.z}) translate(${-view.x * 100}%, ${-view.y * 100}%)` };
  const metresPerPx = EXTENT_M / (width * view.z);
  const barM = metresPerPx * 100 > 2000 ? 2000 : metresPerPx * 100 > 1000 ? 1000 : metresPerPx * 100 > 500 ? 500 : 200;
  const barPx = barM / metresPerPx;
  const panes: [string, string | null, string][] = [
    [site.name, earthSrc, layer === "image" ? "Sentinel-2 L2A true colour, 10 m" : `SRTMGL1 ${layer} (30 m display grid)`],
    [reference.name, refSrc, layer === "image" ? (reference.imagery ? `CTX orthoimage, ${reference.imagery.resolution_m} m source` : "LOLA hillshade (no orthoimage processed)") : `${reference.dem.product.replaceAll("_", " ")} ${layer}`],
  ];
  return (
    <div className="synced" data-testid="synced-compare">
      <div className="explorer-bar">
        <div className="layer-switch" role="radiogroup" aria-label="Compare layer">
          {(["image", "hillshade", "slope"] as Layer[]).map((l) => <button key={l} type="button" role="radio" aria-checked={layer === l} onClick={() => setLayer(l)}>{l === "image" ? "Imagery" : l === "hillshade" ? "Hillshade" : "Slope 0–35°"}</button>)}
        </div>
        <div className="explorer-actions">
          <button type="button" className="icon-button" onClick={() => zoomBy(1.25)} aria-label="Zoom both views in">+</button>
          <button type="button" className="icon-button" onClick={() => zoomBy(0.8)} aria-label="Zoom both views out">−</button>
          <button type="button" className="text-button" onClick={() => setView({ z: 1, x: 0, y: 0 })}>Reset</button>
        </div>
      </div>
      <div className="synced-pair" ref={frame} tabIndex={0} role="group" aria-label={`Synchronised views of ${site.name} and ${reference.name}; scroll or press plus and minus to zoom, drag or use arrow keys to pan`}
        onWheel={onWheel} onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerLeave={onUp} onKeyDown={onKey}>
        {panes.map(([name, src, label]) => (
          <figure key={name} className="synced-pane">
            <div className="synced-clip">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              {src ? <img src={src} alt={`${label} of the 10 km ${name} window, north up`} style={style} draggable={false} /> : <div className="viewer-placeholder">No image processed.</div>}
              <span className="image-north" aria-hidden="true">N</span>
              <span className="synced-scale" aria-hidden="true"><i style={{ width: `${barPx}px` }} />{barM >= 1000 ? `${barM / 1000} km` : `${barM} m`}</span>
            </div>
            <figcaption><strong>{name}</strong> · {label}</figcaption>
          </figure>
        ))}
      </div>
      <p className="viewer-caption" data-testid="synced-caption">
        <span>Same 10 km ground extent and scale on both sides · zoom {view.z.toFixed(2)}× · display {metresPerPx.toFixed(1)} m per screen pixel</span>
        <span>{metresPerPx < 10 ? "finer than the 10 m crops: no extra detail exists past this point" : "within the detail of the crops"}</span>
        <span>Images are display context; scores use the elevation models only</span>
      </p>
    </div>
  );
}
