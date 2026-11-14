import type { ComparisonResult, HealthResponse } from "../../../../lib/api";
import ResultCard from "../shared/ResultCard";

export default function ReportsPage({ results, health, onDownload, onDownloadReport, onNavigate }: {
  results: ComparisonResult[];
  health: HealthResponse | null;
  onDownload: (result: ComparisonResult) => void;
  onDownloadReport: () => void;
  onNavigate: (section: "discovery") => void;
}) {
  const realResultCount = results.filter((result) => result.comparison_classification === "real_comparison").length;
  const previewResultCount = results.length - realResultCount;

  return <div className="page-section">
    <div className="page-intro"><div><p className="eyebrow">RESEARCH OUTPUTS</p><h1>Research reports</h1><p>Review and export the comparison results returned by this session’s backend requests.</p></div><button className="button button-secondary" type="button" onClick={onDownloadReport} disabled={!results.length}>Export report JSON <span>↓</span></button></div>
    <div className="report-summary">
      <article className="surface-card"><span>Comparison results</span><strong>{results.length}</strong><small>Returned by the discovery endpoint</small></article>
      <article className="surface-card"><span>Real comparisons</span><strong>{realResultCount}</strong><small>Ranked from processed terrain inputs</small></article>
      <article className="surface-card"><span>Preview / other</span><strong>{previewResultCount}</strong><small>Kept separate from real rankings</small></article>
      <article className="surface-card"><span>Methodology</span><strong className="method-version">{results[0]?.methodology_version ?? health?.methodology_version ?? "—"}</strong><small>Reported by API health / comparison</small></article>
    </div>
    {results.length ? <div className="report-results">{results.map((result, index) => <ResultCard key={result.candidate_site.id} result={result} rank={index + 1} onDownload={onDownload} />)}</div> : <div className="empty-state report-empty"><span className="empty-icon">↗</span><strong>No comparison report yet</strong><p>Run a terrain comparison first. The report view uses returned API results only.</p><button className="button button-primary" type="button" onClick={() => onNavigate("discovery")}>Start a discovery <span>→</span></button></div>}
  </div>;
}
