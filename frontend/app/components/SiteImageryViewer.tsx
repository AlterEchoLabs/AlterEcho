"use client";

import { useEffect, useState } from "react";
import { api, resolveApiUrl, type AoiFeature, type ImageryRecord, type Site } from "../../lib/api";
import AoiDetailMap from "./AoiDetailMap";

const MODE_LABELS: Record<string, string> = { reference: "High-resolution reference", latest_observation: "Latest available observation", terrain: "Terrain analysis" };

export default function SiteImageryViewer({ site, aoi }: { site: Site; aoi: AoiFeature | null }) {
  const [payload, setPayload] = useState<{ siteId: string; records: ImageryRecord[]; error: string | null }>({ siteId: "", records: [], error: null });
  const [mode, setMode] = useState<ImageryRecord["mode"]>("reference");

  useEffect(() => {
    const controller = new AbortController();
    api.imagery(site.id, controller.signal).then((items) => setPayload({ siteId: site.id, records: items, error: null })).catch((reason) => {
      if (!controller.signal.aborted) setPayload({ siteId: site.id, records: [], error: reason instanceof Error ? reason.message : "Imagery metadata unavailable" });
    });
    return () => controller.abort();
  }, [site.id]);

  const loading = payload.siteId !== site.id;
  const records = loading ? [] : payload.records;
  const error = loading ? null : payload.error;
  const active = records.find((item) => item.mode === mode) ?? records[0];

  return <section className="imagery-viewer" aria-label={`${site.name} AOI imagery`} data-testid="imagery-viewer">
    <header><div><span className="eyebrow">EXACT STUDY AREA</span><h4>{site.name} · 2D AOI viewer</h4></div><div className="north-arrow" aria-label="North is up">N ↑</div></header>
    <div className="imagery-modes" role="tablist" aria-label="Imagery layers">{records.map((record) => <button key={record.imagery_id} role="tab" aria-selected={active?.imagery_id === record.imagery_id} className={active?.imagery_id === record.imagery_id ? "active" : ""} onClick={() => setMode(record.mode)}>{MODE_LABELS[record.mode]}</button>)}</div>
    <div className="imagery-canvas">
      {loading && <div className="imagery-state imagery-loading">Loading AOI layer metadata…</div>}
      {error && <div className="imagery-state">Provider metadata unavailable: {error}. No substitute image is shown.</div>}
      {!loading && !error && active?.preview_url && <div className="imagery-preview" role="img" aria-label={`Derived terrain visualization for the exact ${site.name} study AOI`} style={{ backgroundImage: `url(${resolveApiUrl(active.preview_url)})` }} />}
      {!loading && !error && active?.tile_url && aoi && <AoiDetailMap aoi={aoi} tileUrl={active.tile_url} label={`${MODE_LABELS[active.mode]} for the exact ${site.name} AOI`} />}
      {!loading && !error && active && !active.preview_url && !active.tile_url && <div className="imagery-state"><strong>{MODE_LABELS[active.mode]} unavailable</strong><span>{active.data_status.replaceAll("_", " ")}</span><p>{active.limitations[0]}</p></div>}
      <div className="aoi-frame" aria-hidden="true" />
      <div className="scale-bar"><i />{aoi ? `${(aoi.properties.width_m / 1000).toFixed(0)} km AOI` : "AOI unavailable"}</div>
      <div className="coordinate-readout">{site.latitude.toFixed(4)}°, {site.longitude.toFixed(4)}°</div>
    </div>
    {active && <dl className="imagery-meta"><dt>Provider</dt><dd>{active.provider}</dd><dt>Product</dt><dd>{active.product_id ?? "Not retrieved"}</dd><dt>Observed</dt><dd>{active.acquisition_datetime ? new Date(active.acquisition_datetime).toISOString().slice(0, 10) : "Mosaic date unavailable"}</dd><dt>Published</dt><dd>{active.publication_datetime ? new Date(active.publication_datetime).toISOString().slice(0, 10) : "Not available"}</dd><dt>Resolution</dt><dd>{active.resolution_m ? `${active.resolution_m} m${active.display_resolution_m ? ` · ${active.display_resolution_m} m display` : ""}` : "Product dependent"}</dd><dt>Cloud cover</dt><dd>{active.cloud_cover_pct === null ? "Not available" : `${active.cloud_cover_pct}%`}</dd><dt>AOI coverage</dt><dd>{active.aoi_coverage_fraction === null ? "Not measured" : `${(active.aoi_coverage_fraction * 100).toFixed(1)}%`}</dd><dt>Cache</dt><dd>{active.cache_status.replaceAll("_", " ")}</dd>{active.source_checksum && <><dt>Source SHA-256</dt><dd className="checksum">{active.source_checksum}</dd></>}</dl>}
    {active && <footer><span>{active.attribution}</span><a href={active.official_source_url} target="_blank" rel="noreferrer">Official source ↗</a></footer>}
  </section>;
}
