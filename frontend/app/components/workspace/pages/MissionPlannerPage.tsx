import type { ComparisonResult, Site, TerrainSummary } from "../../../../lib/api";

export default function MissionPlannerPage({ reference, referenceTerrain, selectedRealCount, realCandidateCount, results, onNavigate }: {
  reference: Site | null;
  referenceTerrain?: TerrainSummary;
  selectedRealCount: number;
  realCandidateCount: number;
  results: ComparisonResult[];
  onNavigate: (section: "discovery") => void;
}) {
  return <div className="page-section">
    <div className="page-intro"><div><p className="eyebrow">MISSION WORKSPACE</p><h1>Mission planner</h1><p>Review the currently supported analysis path and the evidence available for your study.</p></div></div>
    <div className="mission-layout">
      <section className="surface-section mission-path">
        <div className="section-title"><div><p className="eyebrow">CURRENT WORKFLOW</p><h2>Mars terrain analogue study</h2></div><span className="future-badge">PHASE 03</span></div>
        <div className="mission-step"><span className="step-number">01</span><div><h3>Reference location</h3><p>{reference?.name ?? "Jezero Crater"} · Mars</p><small>{referenceTerrain?.data_status === "real_processed" ? "Terrain summary available from the API" : "Reference terrain summary unavailable"}</small></div><span className={`step-state ${reference ? "complete" : ""}`}>{reference ? "Available" : "Pending"}</span></div>
        <div className="mission-step"><span className="step-number">02</span><div><h3>Earth study sites</h3><p>{selectedRealCount} selected · {realCandidateCount} processed candidates available</p><small>Only real processed sites are eligible for validated rankings.</small></div><span className={`step-state ${selectedRealCount ? "complete" : ""}`}>{selectedRealCount ? "Ready" : "Select sites"}</span></div>
        <div className="mission-step"><span className="step-number">03</span><div><h3>Terrain comparison</h3><p>{results.length ? `${results.length} API results returned` : "Run a comparison to generate evidence"}</p><small>Results retain rankability, provenance, compatibility, and limitations.</small></div><span className={`step-state ${results.length ? "complete" : ""}`}>{results.length ? "Complete" : "Not run"}</span></div>
        <button className="button button-primary mission-action" type="button" onClick={() => onNavigate("discovery")}>Continue to analogue discovery <span>→</span></button>
      </section>
      <aside className="surface-section mission-future"><p className="eyebrow">FUTURE CAPABILITIES</p><h2>Planned backend connections</h2><ul>
        <li><span>◷</span><div><strong>Mission objectives</strong><small>Not available in the current API</small></div></li>
        <li><span>◷</span><div><strong>Operational constraints</strong><small>Not available in the current API</small></div></li>
        <li><span>◷</span><div><strong>Surface hazard analysis</strong><small>Not available in the current API</small></div></li>
      </ul></aside>
    </div>
  </div>;
}
