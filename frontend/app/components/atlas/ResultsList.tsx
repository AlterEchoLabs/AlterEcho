"use client";

import { Fragment, useMemo, useState } from "react";
import type { Site } from "../../../lib/api";
import type { CandidateV3, ClassGroup, CompareMode, CompareV3, ContextV3 } from "../../../lib/analogue";
import { useDetailMode } from "../../../lib/detail";

/** How many of the ordinary Earth windows are less similar to the reference than this site. */
export function StandingBar({ closer, of, wide = false }: { closer: number; of: number; wide?: boolean }) {
  return <span className={`standing-bar ${wide ? "wide" : ""}`} aria-hidden="true"><span style={{ width: `${(100 * closer) / of}%` }} /></span>;
}

function TerrainRow({ r, site, selected, onSelect, detailed }: { r: CandidateV3; site?: Site; selected: boolean; onSelect: () => void; detailed: boolean }) {
  const st = r.standing;
  const terrain = r.families.find((f) => f.family === "terrain");
  const slope = terrain?.features.find((f) => f.feature === "slope");
  const rel = terrain?.features.find((f) => f.feature === "relative_elevation");
  const reason = r.resolution === "unresolved_from_reference" ? "Differences sit inside the measurement floor"
    : slope?.distance != null && rel?.distance != null ? `Slope off by ${slope.distance.toFixed(1)}° · relief off by ${rel.distance.toFixed(0)} m` : "";
  return (
    <li className="result-item">
      <button type="button" className={`result-row ${selected ? "is-selected" : ""}`} aria-current={selected ? "true" : undefined} onClick={onSelect} data-testid={`result-${r.site_id}`}>
        <span className={`class-dot class-${r.terrain_class ?? "none"}`} aria-hidden="true" />
        <span className="result-main">
          <span className="result-name">{r.site_name}</span>
          {site && <span className="result-place">{site.country_or_region}</span>}
          {reason && <span className="result-reason">{reason}</span>}
        </span>
        {st && r.observed_index != null ? (
          <span className="result-score">
            <span className="index-num mono" title="Terrain similarity index, 0–100"><b>{r.observed_index.toFixed(0)}</b><small>/100</small></span>
            <StandingBar closer={st.closer_than} of={st.of} />
            <small className="standing-cap">beats {st.closer_than} of {st.of} ordinary</small>
            {detailed && r.sensitivity?.index_range && <small className="mono muted">range {r.sensitivity.index_range[0].toFixed(0)}–{r.sensitivity.index_range[1].toFixed(0)}</small>}
          </span>
        ) : <span className="result-score"><small className="muted">distances only</small></span>}
      </button>
    </li>
  );
}

export default function ResultsList({ mode, comparison, context, loading, error, sites, selectedId, onSelect, onRetry }: {
  mode: CompareMode; comparison: CompareV3 | null; context: ContextV3 | null; loading: boolean; error: string | null; sites: Site[];
  selectedId: string | null; onSelect: (id: string) => void; onRetry: () => void;
}) {
  const [detail] = useDetailMode();
  const detailed = detail === "detailed";
  const byId = new Map(sites.map((s) => [s.id, s]));
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<"closeness" | "name">("closeness");
  const q = query.trim().toLowerCase();
  const matches = (name: string, id: string) => !q || `${name} ${byId.get(id)?.country_or_region ?? ""}`.toLowerCase().includes(q);

  const compared = comparison?.profile_state === "ranked";
  const terrainRows = useMemo(() => {
    const rows = (comparison?.results ?? []).filter((r) => r.state !== "excluded" && r.state !== "not_measured").filter((r) => matches(r.site_name, r.site_id));
    if (sort === "name" || !compared) return [...rows].sort((a, b) => a.site_name.localeCompare(b.site_name));
    return rows; // backend order: by index within terrain-class groups
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [comparison, q, sort, sites]);
  const groupOf = new Map<string, ClassGroup>();
  comparison?.class_groups?.forEach((g) => g.site_ids.forEach((id) => groupOf.set(id, g)));
  const grouped = compared && sort === "closeness" && !q;
  const unmeasured = comparison?.results.filter((r) => r.state === "not_measured") ?? [];

  const heading = mode === "terrain" ? "Earth sites by terrain match" : mode === "temperature" ? "Earth sites by surface temperature" : "Earth sites by field-test record";
  const listLoading = loading || (mode !== "terrain" && !context && !error);

  return (
    <div className="results" aria-busy={listLoading}>
      <div className="results-head">
        <h2>{heading}</h2>
        {mode === "terrain" && comparison && <p className="results-headline" data-testid="profile-headline">{comparison.headline}</p>}
        {mode === "temperature" && context && <p className="results-headline">{context.temperature.note}</p>}
        {mode === "fieldwork" && context && <p className="results-headline">{context.fieldwork.note}</p>}
        {listLoading && <p className="muted small">Loading measurements…</p>}
      </div>
      {error && (
        <div className="notice notice-error" role="alert">
          <p>Results could not be loaded: {error}</p>
          <button type="button" className="text-button" onClick={onRetry}>Try again</button>
        </div>
      )}
      <div className="list-tools" role="group" aria-label="Find Earth sites">
        <input type="search" className="search-input" placeholder="Search sites or regions" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search Earth sites" data-testid="site-search" />
        {mode === "terrain" && compared && (
          <label className="sort-label">Order <select value={sort} onChange={(e) => setSort(e.target.value as typeof sort)} data-testid="site-sort">
            <option value="closeness">closest first, grouped</option>
            <option value="name">by name</option>
          </select></label>
        )}
      </div>

      {mode === "terrain" && comparison && (
        <ol className="result-list" data-testid="results-list">
          {terrainRows.length === 0 && <li className="muted small">No measured site matches “{query}”.</li>}
          {terrainRows.map((r) => {
            const g = groupOf.get(r.site_id);
            const first = grouped && g && g.site_ids[0] === r.site_id;
            return (
              <Fragment key={r.site_id}>
                {first && (
                  <li className={`group-label class-${g!.terrain_class}`} data-testid="group-label">
                    <span>{g!.label} · {g!.site_ids.length}</span>
                    {g!.note && <small>{g!.note}</small>}
                  </li>
                )}
                <TerrainRow r={r} site={byId.get(r.site_id)} selected={selectedId === r.site_id} onSelect={() => onSelect(r.site_id)} detailed={detailed} />
              </Fragment>
            );
          })}
        </ol>
      )}

      {mode === "temperature" && context && (
        <ol className="result-list" data-testid="results-list">
          {context.temperature.reference && (
            <li className="ref-row">
              <span className="ref-row-name">{context.reference_name}</span>
              <span className="mono">day {context.temperature.reference.day_c?.toFixed(0)}° · night {context.temperature.reference.night_c?.toFixed(0)}°C</span>
            </li>
          )}
          {context.temperature.sites.filter((t) => matches(t.site_name, t.site_id)).sort((a, b) => a.site_name.localeCompare(b.site_name)).map((t) => (
            <li className="result-item" key={t.site_id}>
              <button type="button" className={`result-row plain ${selectedId === t.site_id ? "is-selected" : ""}`} aria-current={selectedId === t.site_id ? "true" : undefined} onClick={() => onSelect(t.site_id)} data-testid={`result-${t.site_id}`}>
                <span className="result-main">
                  <span className="result-name">{t.site_name}</span>
                  <span className="result-place">{byId.get(t.site_id)?.country_or_region}</span>
                </span>
                <span className="result-score temp-score">
                  {t.record ? <><span className="mono"><b>{t.record.day_c?.toFixed(0)}°</b> / {t.record.night_c?.toFixed(0)}°C</span><small className="muted">day / night</small></> : <small className="muted">no record</small>}
                </span>
              </button>
            </li>
          ))}
        </ol>
      )}

      {mode === "fieldwork" && context && (
        <ol className="result-list" data-testid="results-list">
          {[...context.fieldwork.sites].filter((f) => matches(f.site_name, f.site_id))
            .sort((a, b) => ["window", "region", "none"].indexOf(a.analog_status) - ["window", "region", "none"].indexOf(b.analog_status) || a.site_name.localeCompare(b.site_name))
            .map((f) => (
              <li className="result-item" key={f.site_id}>
                <button type="button" className={`result-row plain ${selectedId === f.site_id ? "is-selected" : ""}`} aria-current={selectedId === f.site_id ? "true" : undefined} onClick={() => onSelect(f.site_id)} data-testid={`result-${f.site_id}`}>
                  <span className="result-main">
                    <span className="result-name">{f.site_name}</span>
                    <span className="result-place">{byId.get(f.site_id)?.country_or_region}</span>
                  </span>
                  <span className={`status-chip analog-${f.analog_status}`}>{f.analog_status === "window" ? "studied here" : f.analog_status === "region" ? "studied nearby" : "no study found"}</span>
                </button>
              </li>
            ))}
        </ol>
      )}

      {mode === "terrain" && comparison && compared && comparison.base_rate && (
        <div className="how-to-read" data-testid="base-rate">
          <p><strong>How to read this.</strong> The index runs from 0 to 100. We also scored {comparison.base_rate.count} ordinary Earth land windows against {comparison.reference_name} the same way, and about half of them reach 90 or more because most land is gentle at a 60 m grid. So the bar under each number shows how many of those ordinary windows the site beats.</p>
        </div>
      )}
      {mode === "terrain" && comparison && !compared && comparison.reference_body === "moon" && (
        <p className="how-to-read" data-testid="ordering-note">No index for the Moon: moving the lunar window just 2 km changes its terrain more than the tolerance allows, so only measured distances are shown.</p>
      )}
      {unmeasured.length > 0 && (
        <div className="unmeasured">
          <h3>Registered, not measured yet</h3>
          <ul>
            {unmeasured.map((r) => (
              <li key={r.site_id}>
                <button type="button" className={`unmeasured-row ${selectedId === r.site_id ? "is-selected" : ""}`} aria-current={selectedId === r.site_id ? "true" : undefined} onClick={() => onSelect(r.site_id)} data-testid={`unmeasured-${r.site_id}`}>
                  <span>{r.site_name}</span><span className="muted small">{byId.get(r.site_id)?.country_or_region} · outside SRTM elevation coverage</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
