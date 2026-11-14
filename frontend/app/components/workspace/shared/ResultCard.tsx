import type { ComparisonResult } from "../../../../lib/api";
import { dataLabel, label } from "./formatters";

export default function ResultCard({ result, rank, onDownload }: { result: ComparisonResult; rank: number; onDownload: (result: ComparisonResult) => void }) {
  const real = result.comparison_classification === "real_comparison";

  return <article className="result-card" data-testid={`result-${result.candidate_site.id}`}>
    <header className="result-header">
      <div>
        <p className="eyebrow">{real ? `RANK ${rank} · PROCESSED DEM` : result.rankability === "rankable" ? "PREVIEW ONLY" : "INSUFFICIENT EVIDENCE"}</p>
        <h3>{result.candidate_site.name}</h3>
        <p className="result-direction">Compared with {result.reference_site.name}, Mars</p>
      </div>
      <div className="score-block"><span>Terrain similarity</span><strong className="score">{result.display_percentage === null ? "Not rankable" : `${result.display_percentage}%`}</strong></div>
    </header>
    {!real && <p className="preview-warning">Illustrative fixture values only — this is not a NASA-derived discovery.</p>}
    <div className="result-meta"><em className={`data-badge ${result.data_status}`}>{dataLabel(result.data_status)}</em><span>Method {result.methodology_version}</span></div>
    <p className={`compatibility ${result.compatibility?.compatible ? "compatible" : "preview"}`}>{result.compatibility?.compatible ? "Compatible inputs" : "Preview / compatibility limits"}</p>
    {result.compatibility?.warnings.map((warning) => <p className="warning-text" key={warning}>{warning}</p>)}
    <div className="metrics-grid">{result.metric_similarities.map((metric) => <div key={metric.metric}><span>{label(metric.metric)}</span><strong>{Math.round(metric.similarity * 100)}%</strong><small>Ref {metric.reference_value.toFixed(2)} · Site {metric.candidate_value.toFixed(2)}</small><i style={{ width: `${metric.similarity * 100}%` }} /></div>)}</div>
    <p>{result.explanation}</p>
    {real && <p className="run-ids">Processing runs: {result.processing_run_ids.reference} / {result.processing_run_ids.candidate}</p>}
    <p className="science-limit">This score measures terrain similarity within equal-scale elevation-model windows. It does not measure atmosphere, gravity, radiation, geology, temperature, or habitability.</p>
    <details><summary>Data & methodology</summary><ul>{result.limitations.map((limit) => <li key={limit}>{limit}</li>)}</ul><p>{String(result.provenance.notice ?? "No provenance notice")}</p><p>AOI scale and processed resolution compatibility are reported above. Source checksums and processing runs are retained in the API response.</p></details>
    <button className="button button-secondary download-button" type="button" onClick={() => onDownload(result)}>Download result JSON</button>
  </article>;
}
