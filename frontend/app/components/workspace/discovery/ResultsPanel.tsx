import type { ComparisonResult, Site, SourceManifest, TerrainSummary, AoiFeature } from "../../../../lib/api";
import ResultCard from "../shared/ResultCard";
import { coordinate, dataLabel, longitude } from "../shared/formatters";

export default function ResultsPanel({ results, resultsStale, comparisonAttempted, realResultCount, previewResultCount, selectedSite, selectedAoi, selectedTerrain, selectedSource, terrainError, onDownload }: {
  results: ComparisonResult[];
  resultsStale: boolean;
  comparisonAttempted: boolean;
  realResultCount: number;
  previewResultCount: number;
  selectedSite: Site | null;
  selectedAoi?: AoiFeature;
  selectedTerrain?: TerrainSummary;
  selectedSource?: SourceManifest;
  terrainError: { siteId: string; message: string } | null;
  onDownload: (result: ComparisonResult) => void;
}) {
  return <div className="evidence-column">
    <div className="results-heading"><div><p className="eyebrow">SCIENTIFIC EVIDENCE</p><h2>Comparison results</h2></div>{results.length > 0 && <span className="result-count">{results.length} returned</span>}</div>
    <div className="results-list" data-testid="results-panel">
      {resultsStale && results.length > 0 && <div className="stale-result" role="status">Previous result shown. The latest comparison request failed.</div>}
      {!results.length && <div className="empty-state"><span className="empty-icon">◌</span><strong>{comparisonAttempted ? "No result was returned" : "Your evidence will appear here"}</strong><p>{comparisonAttempted ? "Check the request status and retry the comparison." : "Select real processed Earth sites, then run a comparison to see ranked terrain results."}</p></div>}
      {results.some((result) => result.ranking_scope === "real_only") && <h3 className="result-section-title">Real terrain ranking <span>{realResultCount}</span></h3>}
      {results.filter((result) => result.ranking_scope === "real_only").map((result, index) => <ResultCard result={result} rank={index + 1} onDownload={onDownload} key={result.candidate_site.id} />)}
      {results.some((result) => result.ranking_scope === "preview_only") && <h3 className="result-section-title">Preview candidates <span>{previewResultCount}</span></h3>}
      {results.filter((result) => result.ranking_scope === "preview_only").map((result, index) => <ResultCard result={result} rank={index + 1} onDownload={onDownload} key={result.candidate_site.id} />)}
    </div>
    {selectedSite ? <article className="site-card" data-testid="selected-candidate-details">
      <div className="site-card-heading"><div><p className="eyebrow">SELECTED STUDY AREA</p><h3>{selectedSite.name}</h3></div><em className={`data-badge ${selectedSite.data_status}`}>{dataLabel(selectedSite.data_status)}</em></div>
      <p>{selectedSite.short_description}</p>
      {terrainError?.siteId === selectedSite.id && <p className="warning-text" role="alert">Dataset details unavailable: {terrainError.message}</p>}
      <dl>
        <dt>Coordinates</dt><dd>{coordinate(selectedSite.latitude)}, {longitude(selectedSite.longitude)}</dd>
        <dt>Study window</dt><dd>{selectedAoi ? `${selectedAoi.properties.width_m / 1000} × ${selectedAoi.properties.height_m / 1000} km · ${selectedAoi.properties.aoi_id}` : "Regional locator only; no verified AOI footprint"}</dd>
        <dt>Source resolution</dt><dd>{selectedSource?.native_resolution ?? "Not available"}{selectedTerrain?.resolution_m ? ` · processed on a ${selectedTerrain.resolution_m} m grid` : ""}</dd>
        <dt>Data quality</dt><dd>{selectedTerrain ? `${(selectedTerrain.valid_coverage_fraction * 100).toFixed(1)}% valid coverage` : selectedSite.data_status === "real_processed" ? "Processed summary loading…" : "No validated terrain summary"}</dd>
        <dt>Known limits</dt><dd>{selectedSite.known_limitations.join(" ")}</dd>
      </dl>
      {selectedSource && <a className="source-link" href={selectedSource.source_page_url} target="_blank" rel="noreferrer">Open source record <span aria-hidden="true">↗</span></a>}
    </article> : <div className="empty-state">Select a site name or map marker to inspect its data.</div>}
  </div>;
}
