"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { api, apiV3, type Site } from "../../../lib/api";
import { COMPARE_MODES, type CompareMode, type CompareV3, type ContextV3, type ReferenceV3, type ViewMode } from "../../../lib/analogue";
import { coords } from "../../../lib/format";
import { useNarrow, useReducedMotion } from "../../../lib/hooks";
import ControlBar, { shortName } from "./ControlBar";
import ResultPanel from "./ResultPanel";
import ResultsList from "./ResultsList";
import SiteViewer from "./SiteViewer";

const OverviewMap = dynamic(() => import("./OverviewMap"), { ssr: false, loading: () => <div className="overview-map placeholder" /> });

const subscribeLocation = (callback: () => void) => { window.addEventListener("popstate", callback); return () => window.removeEventListener("popstate", callback); };
const useQueryString = () => useSyncExternalStore(subscribeLocation, () => window.location.search, () => "");
const slug = (value: string | null) => (value && /^[a-z0-9-]{1,64}$/.test(value) ? value : null);
const MODE_IDS = COMPARE_MODES.map((m) => m.id);

function fromQuery(search: string) {
  const params = new URLSearchParams(search);
  const compare = params.get("compare") as CompareMode | null;
  const view = params.get("view");
  return {
    mode: compare && MODE_IDS.includes(compare) ? compare : null, site: slug(params.get("site")), reference: slug(params.get("reference")),
    view: (view === "full" ? "full" : null) as ViewMode | null,
  };
}

export default function Atlas() {
  const linked = fromQuery(useQueryString());
  const [sites, setSites] = useState<Site[]>([]);
  const [references, setReferences] = useState<ReferenceV3[]>([]);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [modeChoice, setMode] = useState<CompareMode | null>(null);
  const [referenceChoice, setReference] = useState<string | null>(null);
  const [selectedChoice, setSelected] = useState<string | null>(null);
  const [viewChoice, setView] = useState<ViewMode | null>(null);
  const [comparison, setComparison] = useState<{ key: string; data: CompareV3 | null; error: string | null } | null>(null);
  const [context, setContext] = useState<{ key: string; data: ContextV3 | null; error: string | null } | null>(null);
  const [attempt, setAttempt] = useState(0);
  const viewerRef = useRef<HTMLDivElement | null>(null);
  const narrow = useNarrow();
  const reduced = useReducedMotion();

  const mode: CompareMode = modeChoice ?? linked.mode ?? "terrain";
  const referenceId = referenceChoice ?? (linked.reference && references.some((r) => r.id === linked.reference) ? linked.reference : "mars-jezero");
  const view: ViewMode = viewChoice ?? linked.view ?? "simple";

  useEffect(() => {
    let active = true;
    Promise.all([api.sites(), apiV3.references()])
      .then(([siteList, refList]) => { if (active) { setSites(siteList); setReferences(refList); setCatalogError(null); } })
      .catch((error: unknown) => { if (active) setCatalogError(error instanceof Error ? error.message : "Catalog unavailable"); });
    return () => { active = false; };
  }, [attempt]);

  // Terrain comparison: always needed (it also lists the sites). Responses are keyed by reference so a slow answer never paints over a newer choice.
  useEffect(() => {
    if (!sites.length) return;
    let active = true;
    apiV3.compare(referenceId, "terrain_analogy")
      .then((data) => { if (active) setComparison({ key: referenceId, data, error: null }); })
      .catch((error: unknown) => { if (active) setComparison({ key: referenceId, data: null, error: error instanceof Error ? error.message : "Comparison unavailable" }); });
    return () => { active = false; };
  }, [referenceId, sites.length, attempt]);

  useEffect(() => {
    if (!sites.length || mode === "terrain") return;
    let active = true;
    apiV3.context(referenceId)
      .then((data) => { if (active) setContext({ key: referenceId, data, error: null }); })
      .catch((error: unknown) => { if (active) setContext({ key: referenceId, data: null, error: error instanceof Error ? error.message : "Context unavailable" }); });
    return () => { active = false; };
  }, [referenceId, mode, sites.length, attempt]);

  const current = comparison?.key === referenceId ? comparison : null;
  const ctx = context?.key === referenceId ? context : null;
  const loading = sites.length > 0 && !current;
  const wanted = selectedChoice ?? linked.site;
  const firstListed = current?.data?.results.find((r) => r.state !== "excluded" && r.state !== "not_measured")?.site_id ?? null;
  const selectedId = wanted && sites.some((s) => s.id === wanted && s.body === "earth") ? wanted : firstListed;
  const selectedSite = sites.find((s) => s.id === selectedId) ?? null;
  const reference = sites.find((s) => s.id === referenceId) ?? null;
  const referenceInfo = references.find((r) => r.id === referenceId) ?? null;
  const result = current?.data?.results.find((r) => r.site_id === selectedId) ?? null;
  // Windows excluded for contamination stay reachable by link but are not offered as candidates or map markers.
  const excludedIds = new Set((current?.data?.results ?? []).filter((r) => r.state === "excluded").map((r) => r.site_id));

  useEffect(() => {
    if (!selectedId) return;
    const url = new URL(window.location.href);
    url.searchParams.set("reference", referenceId);
    url.searchParams.set("site", selectedId);
    if (mode !== "terrain") url.searchParams.set("compare", mode); else url.searchParams.delete("compare");
    url.searchParams.delete("profile");
    if (view === "full") url.searchParams.set("view", "full"); else url.searchParams.delete("view");
    window.history.replaceState(null, "", url);
  }, [selectedId, referenceId, mode, view]);

  const onSelect = useCallback((id: string) => {
    setSelected(id);
    if (narrow) requestAnimationFrame(() => viewerRef.current?.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "start" }));
  }, [narrow, reduced]);

  return (
    <div className="atlas">
      <header className="atlas-intro">
        <p className="eyebrow">AlterEcho atlas · Team AlterEcho</p>
        <p className="intro-title">Which places on Earth have terrain like Mars or the Moon?</p>
        <p className="intro-text">Pick a reference window on another world. Every Earth site is measured from real elevation data, compared with it, and checked against ordinary land, so you can see why a site matched and what the comparison cannot tell you.</p>
      </header>
      <ControlBar references={references} referenceId={referenceId} onReference={setReference} mode={mode} onMode={setMode} />
      {catalogError && (
        <div className="notice notice-error atlas-notice" role="alert">
          <p>The AlterEcho API is not reachable ({catalogError}). Start the backend on port 8000 and try again.</p>
          <button type="button" className="text-button" onClick={() => setAttempt((n) => n + 1)}>Try again</button>
        </div>
      )}
      <div className="atlas-body">
        <aside className="atlas-results" aria-label="Earth sites">
          <ResultsList mode={mode} comparison={current?.data ?? null} context={ctx?.data ?? null} loading={loading} error={(mode === "terrain" ? current?.error : ctx?.error) ?? null}
            sites={sites} selectedId={selectedId} onSelect={onSelect} onRetry={() => setAttempt((n) => n + 1)} />
          {sites.length > 0 && (
            <div className="overview-wrap">
              <p className="mini-label">Where the Earth sites are</p>
              <OverviewMap sites={sites.filter((s) => !excludedIds.has(s.id))} selectedId={selectedId} onSelect={onSelect} />
            </div>
          )}
        </aside>
        <div className="atlas-site" ref={viewerRef} tabIndex={-1} aria-live="polite" aria-busy={loading}>
          {selectedSite ? (
            <div key={selectedSite.id} className="site-enter">
              <header className="site-head">
                <h2 className="site-name">{selectedSite.name}</h2>
                <p className="site-meta">{selectedSite.country_or_region} · {coords(selectedSite.latitude, selectedSite.longitude)} · {selectedSite.aoi_id ? "10 km study window" : "regional locator only"}{referenceInfo ? ` · compared with ${shortName(referenceInfo)}` : ""}</p>
                {narrow && <a className="text-button back-link" href="#main" onClick={(e) => { e.preventDefault(); window.scrollTo({ top: 0, behavior: reduced ? "auto" : "smooth" }); }}>Back to the list</a>}
              </header>
              <ResultPanel site={selectedSite} reference={reference} comparison={current?.data ?? null} context={ctx?.data ?? null} mode={mode} result={result} view={view} onView={setView} />
              <SiteViewer site={selectedSite} reference={reference} referenceInfo={referenceInfo} />
            </div>
          ) : (
            <div className="viewer-placeholder tall">{catalogError ? "Waiting for the API." : "Loading sites…"}</div>
          )}
        </div>
      </div>
    </div>
  );
}
