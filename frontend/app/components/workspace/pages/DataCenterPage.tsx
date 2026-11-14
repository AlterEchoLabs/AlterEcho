"use client";

import type { AoiFeature, Site, SourceManifest, TerrainSummary } from "../../../../lib/api";
import { dataLabel, label, resolutionLabel } from "../shared/formatters";

export default function DataCenterPage({ sites, sources, terrain, aois, onNavigate }: {
  sites: Site[];
  sources: SourceManifest[];
  terrain: Record<string, TerrainSummary>;
  aois: AoiFeature[];
  onNavigate: (section: "explorer") => void;
}) {
  const readySources = sources.filter((source) => source.processing_status === "processed").length;
  const summaries = Object.values(terrain);

  return <div className="page-section">
    <div className="page-intro"><div><p className="eyebrow">PROVENANCE · COVERAGE · QUALITY</p><h1>Scientific data center</h1><p>Inspect the source manifests and terrain summaries currently returned by the connected API.</p></div></div>
    <div className="data-center-summary">
      <article className="surface-card"><span>Catalog sites</span><strong>{sites.length}</strong><small>Earth candidates loaded from the API</small></article>
      <article className="surface-card"><span>Source manifests</span><strong>{sources.length}</strong><small>{readySources} marked as processed</small></article>
      <article className="surface-card"><span>Terrain summaries</span><strong>{summaries.length}</strong><small>Summaries loaded or inspected this session</small></article>
      <article className="surface-card"><span>AOI footprints</span><strong>{aois.length}</strong><small>Geometry returned by the API</small></article>
    </div>
    <section className="surface-section">
      <div className="section-title"><div><p className="eyebrow">DATA SOURCES</p><h2>Source manifests</h2></div><span className="section-count">{sources.length} records</span></div>
      {sources.length ? <div className="source-grid">{sources.map((source) => <article className="source-card" key={source.source_id}>
        <div className="source-card-top"><span className="source-orb">◉</span><em className={`data-badge ${source.processing_status === "processed" ? "real_processed" : "metadata_only"}`}>{label(source.processing_status)}</em></div>
        <h3>{source.title}</h3><p>{source.provider}{source.mission ? ` · ${source.mission}` : ""}{source.instrument ? ` · ${source.instrument}` : ""}</p>
        <dl><dt>Native resolution</dt><dd>{resolutionLabel(source.native_resolution)}</dd><dt>Access date</dt><dd>{source.access_date ?? "Not reported"}</dd></dl>
        <a className="source-link" href={source.source_page_url} target="_blank" rel="noreferrer">Open source record ↗</a>
      </article>)}</div> : <div className="empty-state"><strong>Source manifests unavailable</strong><p>Connect to the backend to load provenance records.</p></div>}
    </section>
    <section className="surface-section">
      <div className="section-title"><div><p className="eyebrow">PROCESSED TERRAIN</p><h2>Terrain summaries</h2></div><span className="section-count">{summaries.length} records</span></div>
      {summaries.length ? <div className="terrain-table-wrap"><table className="terrain-table"><thead><tr><th>Site</th><th>Status</th><th>Resolution</th><th>Coverage</th><th>AOI</th><th>Processing run</th></tr></thead><tbody>{summaries.map((summary) => <tr key={summary.site_id}>
        <td><strong>{sites.find((site) => site.id === summary.site_id)?.name ?? summary.site_id}</strong><small>{summary.site_id}</small></td>
        <td><em className={`data-badge ${summary.data_status}`}>{dataLabel(summary.data_status)}</em></td>
        <td>{summary.resolution_m ? `${summary.resolution_m} m` : "—"}</td><td>{`${(summary.valid_coverage_fraction * 100).toFixed(1)}%`}</td><td>{summary.aoi_id ?? "—"}</td><td className="table-mono">{summary.processing_run_id ?? "—"}</td>
      </tr>)}</tbody></table></div> : <div className="empty-state"><strong>No terrain summaries loaded</strong><p>Inspect a site in the explorer to request its terrain summary.</p><button className="button button-secondary" type="button" onClick={() => onNavigate("explorer")}>Open explorer</button></div>}
    </section>
    <p className="data-disclaimer">Displayed records come from the connected API response. Missing fields are shown as unavailable; no source or quality values are inferred by the frontend.</p>
  </div>;
}
