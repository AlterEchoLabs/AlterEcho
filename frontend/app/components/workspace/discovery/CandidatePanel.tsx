"use client";

import type { Site, TerrainSummary } from "../../../../lib/api";
import type { DataFilter } from "../types";
import { coordinate, dataLabel, label, longitude } from "../shared/formatters";

export default function CandidatePanel({ sites, selectedIds, focusedCandidateId, dataFilter, candidateCounts, candidateQuery, regionFilter, environmentFilter, regions, environments, reference, referenceTerrain, catalogLoading, catalogError, realSitesAvailable, selectedRealCount, comparisonButtonLabel, comparisonLoading, backendError, comparisonError, methodologyVersion, onQueryChange, onRegionChange, onEnvironmentChange, onDataFilterChange, onSelectAll, onToggle, onFocus, onCompare, onMethodologyChange }: {
  sites: Site[];
  selectedIds: string[];
  focusedCandidateId: string | null;
  dataFilter: DataFilter;
  candidateCounts: Record<DataFilter, number>;
  candidateQuery: string;
  regionFilter: string;
  environmentFilter: string;
  regions: string[];
  environments: string[];
  reference: Site | null;
  referenceTerrain?: TerrainSummary;
  catalogLoading: boolean;
  catalogError: string | null;
  realSitesAvailable: boolean;
  selectedRealCount: number;
  comparisonButtonLabel: string;
  comparisonLoading: boolean;
  backendError: boolean;
  comparisonError: string | null;
  methodologyVersion: "terrain-v3.0" | "terrain-v2.0";
  onQueryChange: (value: string) => void;
  onRegionChange: (value: string) => void;
  onEnvironmentChange: (value: string) => void;
  onDataFilterChange: (filter: DataFilter) => void;
  onSelectAll: () => void;
  onToggle: (siteId: string) => void;
  onFocus: (siteId: string) => void;
  onCompare: () => void;
  onMethodologyChange: (value: "terrain-v3.0" | "terrain-v2.0") => void;
}) {
  return <div className="candidate-column">
    <div className="workflow-heading"><p className="eyebrow">EARTH CANDIDATES</p><h2>Find a terrain analogue</h2><p className="panel-muted">Choose validated sites to compare with the Jezero Crater reference using the configured terrain methodology.</p></div>
    <article className="reference-card"><div><span className="reference-kicker">PLANETARY REFERENCE</span><h3>{reference?.name ?? "Jezero Crater"}</h3><p>Mars · {referenceTerrain?.data_status === "real_processed" ? "processed elevation model" : "reference site"}</p></div><strong>{referenceTerrain?.resolution_m ? `${referenceTerrain.resolution_m} m grid` : "Grid unavailable"}</strong></article>
    <div className="candidate-search"><span aria-hidden="true">⌕</span><input aria-label="Search Earth candidates" value={candidateQuery} onChange={(event) => onQueryChange(event.target.value)} placeholder="Search sites, regions, terrain…" /></div>
    <div className="candidate-selectors">
      <label>Region<select aria-label="Filter by region" value={regionFilter} onChange={(event) => onRegionChange(event.target.value)}><option value="all">All regions</option>{regions.map((region) => <option value={region} key={region}>{region}</option>)}</select></label>
      <label>Environment<select aria-label="Filter by environment type" value={environmentFilter} onChange={(event) => onEnvironmentChange(event.target.value)}><option value="all">All environments</option>{environments.map((environment) => <option value={environment} key={environment}>{label(environment)}</option>)}</select></label>
    </div>
    <div className="filter-toolbar">
      <div className="data-filters" aria-label="Candidate data filters">{([["real_processed", "Real data"], ["all", "All sites"], ["planned", "Planned"], ["metadata_only", "Metadata"]] as const).map(([id, text]) => <button type="button" className={dataFilter === id ? "active" : ""} key={id} onClick={() => onDataFilterChange(id)}>{text}<b>{candidateCounts[id]}</b></button>)}</div>
      {realSitesAvailable && <button className="select-all-button" type="button" onClick={onSelectAll}>Select all real sites</button>}
    </div>
    {catalogLoading && <p className="inline-message">Loading candidate catalog…</p>}
    {catalogError && <p className="error-text" role="alert">Could not load the candidate catalog: {catalogError}</p>}
    {!catalogLoading && !sites.length && <p className="empty-inline">No sites match these filters.</p>}
    <div className="candidate-list">{sites.map((site) => {
      const eligible = site.data_status === "real_processed";
      const inspected = focusedCandidateId === site.id;
      return <div data-testid={`candidate-${site.id}`} key={site.id} className={`candidate-row ${inspected ? "focused" : ""} ${selectedIds.includes(site.id) ? "selected" : ""} ${!eligible ? "not-eligible" : ""}`}>
        <input aria-label={`Include ${site.name} in comparison`} type="checkbox" disabled={!eligible} checked={selectedIds.includes(site.id)} onChange={() => onToggle(site.id)} />
        <button type="button" className="site-inspect-button" onClick={() => onFocus(site.id)}><strong>{site.name}</strong><span>{site.country_or_region} · {coordinate(site.latitude)}, {longitude(site.longitude)}</span></button>
        <em className={`data-badge ${site.data_status}`}>{dataLabel(site.data_status)}</em>
        <div className="candidate-detail"><span>{label(site.analog_type)}</span><span>{site.available_metrics.length} metrics</span>{!eligible && <small>{site.data_status === "planned" ? "Planned dataset integration; comparison disabled." : "No validated terrain summary."}</small>}</div>
      </div>;
    })}</div>
    <div className="methodology-picker"><label htmlFor="methodology">Method</label><select id="methodology" value={methodologyVersion} onChange={(event) => onMethodologyChange(event.target.value as "terrain-v3.0" | "terrain-v2.0")}><option value="terrain-v3.0">terrain-v3.0 · distributions + multi-scale</option><option value="terrain-v2.0">terrain-v2.0 · historical summary metrics</option></select></div>
    <div className="compare-action"><button className="button button-primary compare-button" type="button" onClick={onCompare} disabled={comparisonLoading || backendError || !selectedRealCount}>{comparisonButtonLabel}<span>→</span></button><span>{selectedRealCount ? `${selectedRealCount} real site${selectedRealCount === 1 ? "" : "s"} selected` : "Choose at least one real site to enable comparison."}</span></div>
    {comparisonError && <div className="request-error" role="alert"><strong>Comparison request failed.</strong><p>{comparisonError}. Your site selection is preserved.</p><button type="button" onClick={onCompare}>Retry comparison</button></div>}
  </div>;
}
