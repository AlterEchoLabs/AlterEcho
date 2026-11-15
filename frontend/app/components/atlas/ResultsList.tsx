"use client";

import { Fragment, useMemo, useState } from "react";
import type { Site } from "../../../lib/api";
import { PROFILE_STATE_TEXT, type CandidateV3, type CompareV3 } from "../../../lib/analogue";
import { pct } from "../../../lib/format";

function rankText(r: CandidateV3, groupSize: number): string {
  if (r.state !== "ranked" || r.rank == null) return "·";
  return groupSize > 1 ? `${r.rank}=` : String(r.rank);
}

function Row({ result, site, selected, groupSize, onSelect, delay }: {
  result: CandidateV3; site: Site | undefined; selected: boolean; groupSize: number; onSelect: () => void; delay: number;
}) {
  const ranked = result.state === "ranked";
  const range = result.sensitivity?.index_range;
  const terrain = result.families.find((f) => f.family === "terrain");
  const scored = terrain?.features.filter((f) => f.role === "scored" && f.distance != null) ?? [];
  const note = result.state === "partial" ? `Terrain only · ${pct(result.evidence_coverage)} of plan measured`
    : result.state === "not_assessed" ? "Task-critical evidence missing"
    : result.resolution === "unresolved_from_reference" ? "Not resolved from the reference by the floor tests"
    : scored.length ? `Slope Δ ${scored.find((f) => f.feature === "slope")?.distance?.toFixed(2)}° · relief Δ ${scored.find((f) => f.feature === "relative_elevation")?.distance?.toFixed(0)} m` : "";
  return (
    <li className="result-item" style={{ animationDelay: `${delay}ms` }}>
      <button type="button" className={`result-row ${selected ? "is-selected" : ""}`} aria-current={selected ? "true" : undefined} onClick={onSelect} data-testid={`result-${result.site_id}`}>
        <span className="result-rank mono" aria-label={ranked ? `Rank ${rankText(result, groupSize)}` : "Not ranked"}>{rankText(result, groupSize)}</span>
        <span className="result-main">
          <span className="result-name">{result.site_name}</span>
          {site && <span className="result-place">{site.country_or_region}</span>}
          {note && <span className="result-reason">{note}</span>}
        </span>
        <span className="result-score">
          {ranked && result.observed_index != null ? (
            <>
              <b className="mono" title="Experimental terrain index (0–100), not a probability">{result.observed_index.toFixed(0)}</b>
              {range && <small className="mono" title="Scenario range: placement, DEM, grid, tolerance and weights">{range[0].toFixed(0)}–{range[1].toFixed(0)}</small>}
              {result.background_share != null && <small className="bg-share" title="Share of unselected Earth windows that score at least as high">top {Math.max(1, Math.round(result.background_share * 100))}% of background</small>}
            </>
          ) : (
            <span className="coverage" title="Share of the planned profile weight that is measured and comparable">
              <span className="coverage-track"><span style={{ width: pct(result.evidence_coverage) }} /></span>
              <span className="coverage-label">{pct(result.evidence_coverage)} measured</span>
            </span>
          )}
        </span>
      </button>
    </li>
  );
}

export default function ResultsList({ comparison, loading, error, sites, selectedId, onSelect, onRetry }: {
  comparison: CompareV3 | null; loading: boolean; error: string | null; sites: Site[];
  selectedId: string | null; onSelect: (id: string) => void; onRetry: () => void;
}) {
  const byId = new Map(sites.map((s) => [s.id, s]));
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | "close" | "rugged">("all");
  const [sort, setSort] = useState<"rank" | "background" | "name">("rank");
  const ranked = comparison?.profile_state === "ranked";
  const sortBy = ranked ? sort : "name";
  const listed = useMemo(() => {
    const q = query.trim().toLowerCase();
    const rows = (comparison?.results ?? []).filter((r) => r.state === "ranked" || r.state === "partial" || r.state === "not_assessed")
      .filter((r) => !q || `${r.site_name} ${byId.get(r.site_id)?.country_or_region ?? ""}`.toLowerCase().includes(q))
      .filter((r) => filter === "all" || (filter === "close" ? (r.observed_index ?? 0) >= 50 : (r.observed_index ?? 100) < 50));
    if (sortBy === "name") return [...rows].sort((a, b) => a.site_name.localeCompare(b.site_name));
    if (sortBy === "background") return [...rows].sort((a, b) => (a.background_share ?? 1) - (b.background_share ?? 1) || a.site_name.localeCompare(b.site_name));
    return rows;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [comparison, query, filter, sortBy, sites]);
  const excluded = comparison?.results.filter((r) => r.state === "excluded") ?? [];
  const unmeasured = comparison?.results.filter((r) => r.state === "not_measured") ?? [];
  const groupFor = (id: string) => comparison?.tie_groups.find((g) => g.includes(id));
  const base = comparison?.base_rate;
  return (
    <div className="results" aria-busy={loading}>
      <div className="results-head">
        <h2>Earth candidates</h2>
        {comparison && <p className={`state-pill state-${comparison.profile_state}`} data-testid="profile-state">{PROFILE_STATE_TEXT[comparison.profile_state]}</p>}
        {comparison && <p className="results-headline" data-testid="profile-headline">{comparison.headline}</p>}
        {loading && !comparison && <p className="muted small">Calculating from prepared measurements…</p>}
      </div>
      {error && (
        <div className="notice notice-error" role="alert">
          <p>Results could not be loaded: {error}</p>
          <button type="button" className="text-button" onClick={onRetry}>Try again</button>
        </div>
      )}
      {comparison && (
        <div className="list-tools" role="group" aria-label="Find and order Earth windows">
          <input type="search" className="search-input" placeholder="Search sites or regions" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search Earth windows" data-testid="site-search" />
          <div className="list-tools-row">
            {ranked && (
              <label>Order <select value={sort} onChange={(e) => setSort(e.target.value as typeof sort)} data-testid="site-sort">
                <option value="rank">by rank (tie groups kept)</option>
                <option value="background">by background share</option>
                <option value="name">by name</option>
              </select></label>
            )}
            {ranked && (
              <label>Show <select value={filter} onChange={(e) => setFilter(e.target.value as typeof filter)} data-testid="site-filter">
                <option value="all">all measured</option>
                <option value="close">index 50 or more</option>
                <option value="rugged">index below 50</option>
              </select></label>
            )}
            {!ranked && <span className="muted small">Partial evidence: listed by name, never ranked.</span>}
          </div>
        </div>
      )}
      {comparison && (
        <ol className="result-list" data-testid="results-list">
          {listed.length === 0 && <li className="muted small">No measured window matches.</li>}
          {listed.map((r, i) => {
            const group = groupFor(r.site_id);
            const first = sortBy === "rank" && !query && filter === "all" && group && group.length > 1 && group[0] === r.site_id;
            return (
              <Fragment key={r.site_id}>
                {first && <li className="tie-label" data-testid="tie-label">Tie group · {group!.length} sites · order not resolved by the data</li>}
                <Row result={r} site={byId.get(r.site_id)} selected={selectedId === r.site_id} groupSize={group?.length ?? 1} onSelect={() => onSelect(r.site_id)} delay={i * 40} />
              </Fragment>
            );
          })}
        </ol>
      )}
      {comparison && <p className="ordering-note" data-testid="ordering-note">{comparison.ordering_note}</p>}
      {base && comparison?.profile_state === "ranked" && (
        <p className="base-rate" data-testid="base-rate">
          <strong>{pct(base.share_at_or_above["90"])}</strong> of {base.count} unselected Earth windows also score 90 or more against {comparison.reference_name}. A high terrain index mostly means low relief.
        </p>
      )}
      {excluded.length > 0 && (
        <div className="unmeasured">
          <h3>Excluded windows</h3>
          <ul>
            {excluded.map((r) => (
              <li key={r.site_id}>
                <button type="button" className={`unmeasured-row ${selectedId === r.site_id ? "is-selected" : ""}`} aria-current={selectedId === r.site_id ? "true" : undefined} onClick={() => onSelect(r.site_id)} data-testid={`excluded-${r.site_id}`}>
                  <span>{r.site_name}</span><span className="muted small">contaminated window · replaced by {r.exclusion?.replacement_name}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
      {unmeasured.length > 0 && (
        <div className="unmeasured">
          <h3>Not measured yet</h3>
          <ul>
            {unmeasured.map((r) => (
              <li key={r.site_id}>
                <button type="button" className={`unmeasured-row ${selectedId === r.site_id ? "is-selected" : ""}`} aria-current={selectedId === r.site_id ? "true" : undefined} onClick={() => onSelect(r.site_id)} data-testid={`unmeasured-${r.site_id}`}>
                  <span>{r.site_name}</span><span className="muted small">{byId.get(r.site_id)?.country_or_region} · {byId.get(r.site_id)?.data_status === "planned" ? "planned dataset" : "metadata only"}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
