"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { api, apiV3, resolveApiUrl, type Site } from "../../../lib/api";
import { COMPARE_MODES, type CompareMode, type CompareV3, type ContextV3, type ReferenceV3 } from "../../../lib/analogue";
import { useDetailMode } from "../../../lib/detail";
import { coords } from "../../../lib/format";
import { useNarrow, useReducedMotion } from "../../../lib/hooks";
import ControlBar, { shortName } from "./ControlBar";
import ResultPanel, { FullCalculation } from "./ResultPanel";
import ResultsList from "./ResultsList";
import SiteViewer from "./SiteViewer";
import StudyPlate, { type PlateLayer } from "./StudyPlate";

const OverviewMap = dynamic(() => import("./OverviewMap"), { ssr: false, loading: () => <div className="overview-map placeholder" /> });

// The URL is the single source of truth for reference, site and comparison mode, so links, reloads and back/forward all agree.
const URL_EVENT = "alterecho-url";
const subscribeLocation = (callback: () => void) => {
  window.addEventListener("popstate", callback);
  window.addEventListener(URL_EVENT, callback);
  return () => { window.removeEventListener("popstate", callback); window.removeEventListener(URL_EVENT, callback); };
};
const useQueryString = () => useSyncExternalStore(subscribeLocation, () => window.location.search, () => "");
const slug = (value: string | null) => (value && /^[a-z0-9-]{1,64}$/.test(value) ? value : null);
const MODE_IDS = COMPARE_MODES.map((m) => m.id);

function fromQuery(search: string) {
  const params = new URLSearchParams(search);
  const compare = params.get("compare") as CompareMode | null;
  return { mode: compare && MODE_IDS.includes(compare) ? compare : null, site: slug(params.get("site")), reference: slug(params.get("reference")) };
}

function navigate(patch: Record<string, string | null>, push: boolean) {
  const url = new URL(window.location.href);
  for (const [key, value] of Object.entries(patch)) { if (value == null) url.searchParams.delete(key); else url.searchParams.set(key, value); }
  if (url.search === window.location.search) return;
  window.history[push ? "pushState" : "replaceState"](null, "", url);
  window.dispatchEvent(new Event(URL_EVENT));
}

export default function Atlas() {
  const query = fromQuery(useQueryString());
  const [detail, setDetail] = useDetailMode();
  const detailed = detail === "detailed";
  const [sites, setSites] = useState<Site[]>([]);
  const [references, setReferences] = useState<ReferenceV3[]>([]);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [comparison, setComparison] = useState<{ key: string; data: CompareV3 | null; error: string | null } | null>(null);
  const [context, setContext] = useState<{ key: string; data: ContextV3 | null; error: string | null } | null>(null);
  const [plateLayer, setPlateLayer] = useState<PlateLayer>("satellite");
  const [attempt, setAttempt] = useState(0);
  const viewerRef = useRef<HTMLDivElement | null>(null);
  const fullRef = useRef<HTMLDivElement | null>(null);
  const resultsRef = useRef<HTMLElement | null>(null);
  const narrow = useNarrow();
  const reduced = useReducedMotion();

  const mode: CompareMode = query.mode ?? "terrain";
  const referenceId = query.reference && (!references.length || references.some((r) => r.id === query.reference)) ? query.reference : "mars-jezero";

  // A shared link may ask for a reading mode: view=full opens Detailed, view=simple opens Simple.
  useEffect(() => {
    const view = new URLSearchParams(window.location.search).get("view");
    if (view === "full") setDetail("detailed");
    else if (view === "simple") setDetail("simple");
  }, [setDetail]);

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
  const listed = (current?.data?.results ?? []).filter((r) => r.state !== "excluded" && r.state !== "not_measured");
  const firstListed = listed[0]?.site_id ?? null;
  const selectedId = query.site && sites.some((s) => s.id === query.site && s.body === "earth") ? query.site : firstListed;
  const selectedSite = sites.find((s) => s.id === selectedId) ?? null;
  const reference = sites.find((s) => s.id === referenceId) ?? null;
  const referenceInfo = references.find((r) => r.id === referenceId) ?? null;
  const result = current?.data?.results.find((r) => r.site_id === selectedId) ?? null;
  // Windows excluded for contamination stay reachable by link but are not offered as candidates or map markers.
  const excludedIds = new Set((current?.data?.results ?? []).filter((r) => r.state === "excluded").map((r) => r.site_id));

  // Fill in the defaults (reference, first site) and the reading mode without adding history entries.
  useEffect(() => {
    if (!selectedId) return;
    navigate({ reference: referenceId, site: selectedId, view: detailed ? "full" : null, profile: null }, false);
  }, [selectedId, referenceId, detailed]);

  // Warm the cache for the top candidates' study-window images so clicking one shows its picture at once.
  const topIds = listed.slice(0, 3).map((r) => r.site_id).join(",");
  useEffect(() => {
    if (!topIds) return;
    const timer = window.setTimeout(() => {
      for (const id of topIds.split(",")) {
        apiV3.explorer(id).then((w) => { const src = w.imagery ? resolveApiUrl(w.imagery.url) : null; if (src) { const img = new Image(); img.src = src; } }).catch(() => undefined);
      }
    }, 1200);
    return () => window.clearTimeout(timer);
  }, [topIds]);

  const onSelect = useCallback((id: string) => {
    navigate({ site: id }, true);
    if (narrow) requestAnimationFrame(() => viewerRef.current?.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "start" }));
  }, [narrow, reduced]);
  const onReference = useCallback((id: string) => navigate({ reference: id }, true), []);
  const onMode = useCallback((m: CompareMode) => navigate({ compare: m === "terrain" ? null : m }, true), []);
  const onDetailed = useCallback(() => {
    setDetail("detailed");
    requestAnimationFrame(() => requestAnimationFrame(() => fullRef.current?.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "start" })));
  }, [setDetail, reduced]);
  const onHideFull = useCallback(() => setDetail("simple"), [setDetail]);

  const status = selectedSite ? `${selectedSite.name}${referenceInfo ? `, compared with ${referenceInfo.name}` : ""}` : "";

  return (
    <div className="atlas" data-detail={detail}>
      <ControlBar references={references} referenceId={referenceId} onReference={onReference} mode={mode} onMode={onMode} />
      {catalogError && (
        <div className="notice notice-error atlas-notice" role="alert">
          <p>The AlterEcho API is not reachable ({catalogError}). Start the backend on port 8000 and try again.</p>
          <button type="button" className="text-button" onClick={() => setAttempt((n) => n + 1)}>Try again</button>
        </div>
      )}
      <p className="sr-only" aria-live="polite">{status}</p>
      <div className="atlas-body">
        <aside className="atlas-results" aria-label="Earth sites" ref={resultsRef}>
          <ResultsList mode={mode} comparison={current?.data ?? null} context={ctx?.data ?? null} loading={loading} error={(mode === "terrain" ? current?.error : ctx?.error) ?? null}
            sites={sites} selectedId={selectedId} onSelect={onSelect} onRetry={() => setAttempt((n) => n + 1)} />
          {detailed && sites.length > 0 && (
            <div className="overview-wrap">
              <p className="mini-label">Where the Earth sites are</p>
              <OverviewMap sites={sites.filter((s) => !excludedIds.has(s.id))} selectedId={selectedId} onSelect={onSelect} />
            </div>
          )}
        </aside>
        <div className="atlas-site" ref={viewerRef} tabIndex={-1} aria-busy={loading}>
          {selectedSite ? (
            <div key={selectedSite.id} className="site-enter">
              <div className={`result-hero ${selectedSite.aoi_id ? "" : "no-plate"}`}>
                <div className="result-main-col">
                  <header className="site-head">
                    <h2 className="site-name">{selectedSite.name}</h2>
                    <p className="site-meta">{selectedSite.country_or_region} · {coords(selectedSite.latitude, selectedSite.longitude)} · {selectedSite.aoi_id ? "10 km study window" : "regional locator only"}{referenceInfo ? ` · compared with ${shortName(referenceInfo)}` : ""}</p>
                    {narrow && <button type="button" className="text-button back-link" onClick={() => resultsRef.current?.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "start" })}>Back to the list</button>}
                  </header>
                  <div key={`${referenceId}|${mode}`} className="card-enter">
                    <ResultPanel site={selectedSite} comparison={current?.data ?? null} context={ctx?.data ?? null} mode={mode} result={result} onDetailed={onDetailed} />
                  </div>
                </div>
                {selectedSite.aoi_id && <StudyPlate key={selectedSite.id} site={selectedSite} layer={plateLayer} onLayer={setPlateLayer} detailed={detailed} />}
              </div>
              {detailed && mode === "terrain" && current?.data && result && (
                <div ref={fullRef} className="full-wrap">
                  <FullCalculation site={selectedSite} comparison={current.data} result={result} onHide={onHideFull} />
                </div>
              )}
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
