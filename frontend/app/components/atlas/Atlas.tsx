"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { api, apiV3, type Site } from "../../../lib/api";
import { PROFILE_IDS_V3, type CompareV3, type ProfileIdV3, type ProfileV3, type ReferenceV3, type ViewMode } from "../../../lib/analogue";
import { coords } from "../../../lib/format";
import { useNarrow, useReducedMotion } from "../../../lib/hooks";
import ReferenceBand from "./ReferenceBand";
import ResultPanel from "./ResultPanel";
import ResultsList from "./ResultsList";
import SiteViewer from "./SiteViewer";

const OverviewMap = dynamic(() => import("./OverviewMap"), { ssr: false, loading: () => <div className="overview-map placeholder" /> });

const subscribeLocation = (callback: () => void) => { window.addEventListener("popstate", callback); return () => window.removeEventListener("popstate", callback); };
const useQueryString = () => useSyncExternalStore(subscribeLocation, () => window.location.search, () => "");
const slug = (value: string | null) => (value && /^[a-z0-9-]{1,64}$/.test(value) ? value : null);

function fromQuery(search: string) {
  const params = new URLSearchParams(search);
  const profile = params.get("profile") as ProfileIdV3 | null;
  const view = params.get("view");
  return {
    profile: profile && PROFILE_IDS_V3.includes(profile) ? profile : null, site: slug(params.get("site")), reference: slug(params.get("reference")),
    view: (view === "full" ? "full" : view === "simple" ? "simple" : null) as ViewMode | null,
  };
}

export default function Atlas() {
  const linked = fromQuery(useQueryString());
  const [sites, setSites] = useState<Site[]>([]);
  const [profiles, setProfiles] = useState<ProfileV3[]>([]);
  const [references, setReferences] = useState<ReferenceV3[]>([]);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [profileChoice, setProfile] = useState<ProfileIdV3 | null>(null);
  const [referenceChoice, setReference] = useState<string | null>(null);
  const [selectedChoice, setSelected] = useState<string | null>(null);
  const [viewChoice, setView] = useState<ViewMode | null>(null);
  const [comparison, setComparison] = useState<{ key: string; data: CompareV3 | null; error: string | null } | null>(null);
  const [attempt, setAttempt] = useState(0);
  const viewerRef = useRef<HTMLDivElement | null>(null);
  const narrow = useNarrow();
  const reduced = useReducedMotion();

  const profileId: ProfileIdV3 = profileChoice ?? linked.profile ?? "terrain_analogy";
  const referenceId = referenceChoice ?? (linked.reference && references.some((r) => r.id === linked.reference) ? linked.reference : "mars-jezero");
  const view: ViewMode = viewChoice ?? linked.view ?? "simple";
  const key = `${referenceId}|${profileId}`;

  useEffect(() => {
    let active = true;
    Promise.all([api.sites(), apiV3.profiles(), apiV3.references()])
      .then(([siteList, profileList, refList]) => { if (active) { setSites(siteList); setProfiles(profileList); setReferences(refList); setCatalogError(null); } })
      .catch((error: unknown) => { if (active) setCatalogError(error instanceof Error ? error.message : "Catalog unavailable"); });
    return () => { active = false; };
  }, [attempt]);

  useEffect(() => {
    if (!sites.length) return;
    let active = true;
    apiV3.compare(referenceId, profileId)
      .then((data) => { if (active) setComparison({ key, data, error: null }); })
      .catch((error: unknown) => { if (active) setComparison({ key, data: null, error: error instanceof Error ? error.message : "Comparison unavailable" }); });
    return () => { active = false; };
  }, [key, referenceId, profileId, sites.length, attempt]);

  const current = comparison?.key === key ? comparison : null;
  const shown = current?.data ?? comparison?.data ?? null;
  const loading = sites.length > 0 && !current;
  const wanted = selectedChoice ?? linked.site;
  const firstListed = shown?.results.find((r) => r.state !== "excluded" && r.state !== "not_measured")?.site_id ?? null;
  const selectedId = wanted && sites.some((s) => s.id === wanted && s.body === "earth") ? wanted : firstListed;
  const selectedSite = sites.find((s) => s.id === selectedId) ?? null;
  const reference = sites.find((s) => s.id === referenceId) ?? null;
  const result = current?.data?.results.find((r) => r.site_id === selectedId) ?? null;

  useEffect(() => {
    if (!selectedId) return;
    const url = new URL(window.location.href);
    url.searchParams.set("site", selectedId);
    url.searchParams.set("profile", profileId);
    url.searchParams.set("reference", referenceId);
    if (view === "full") url.searchParams.set("view", "full"); else url.searchParams.delete("view");
    window.history.replaceState(null, "", url);
  }, [selectedId, profileId, referenceId, view]);

  const onSelect = useCallback((id: string) => {
    setSelected(id);
    if (narrow) requestAnimationFrame(() => viewerRef.current?.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "start" }));
  }, [narrow, reduced]);

  return (
    <div className="atlas">
      <ReferenceBand references={references} referenceId={referenceId} onReference={setReference} profiles={profiles} profileId={profileId} onProfile={(id) => setProfile(id as ProfileIdV3)} />
      {catalogError && (
        <div className="notice notice-error atlas-notice" role="alert">
          <p>The AlterEcho API is not reachable ({catalogError}). Start the backend on port 8000 and try again.</p>
          <button type="button" className="text-button" onClick={() => setAttempt((n) => n + 1)}>Try again</button>
        </div>
      )}
      <div className="atlas-body">
        <aside className="atlas-results" aria-label="Earth sites">
          <div className="step-label"><span className="mono">3</span> Earth candidates</div>
          {sites.length > 0 && <OverviewMap sites={sites} selectedId={selectedId} onSelect={onSelect} />}
          <ResultsList comparison={shown} loading={loading} error={current?.error ?? null} sites={sites} selectedId={selectedId} onSelect={onSelect} onRetry={() => setAttempt((n) => n + 1)} />
        </aside>
        <div className="atlas-site" ref={viewerRef} tabIndex={-1} aria-live="polite" aria-busy={loading}>
          {selectedSite ? (
            <div key={selectedSite.id} className="site-enter">
              <header className="site-head">
                <div className="step-label"><span className="mono">4</span> Result, imagery and evidence</div>
                <div className="site-title-row">
                  <h2 className="site-name">{selectedSite.name}</h2>
                  <p className="site-meta">{selectedSite.country_or_region} · {coords(selectedSite.latitude, selectedSite.longitude)} · {selectedSite.aoi_id ? "10 km study window" : "regional locator only"}</p>
                </div>
                {narrow && <a className="text-button back-link" href="#main" onClick={(e) => { e.preventDefault(); window.scrollTo({ top: 0, behavior: reduced ? "auto" : "smooth" }); }}>Back to results</a>}
              </header>
              <ResultPanel site={selectedSite} reference={reference} comparison={current?.data ?? null} result={result} view={view} onView={setView} />
              <SiteViewer site={selectedSite} reference={reference} referenceInfo={references.find((r) => r.id === referenceId) ?? null} />
            </div>
          ) : (
            <div className="viewer-placeholder tall">{catalogError ? "Waiting for the API." : "Loading sites…"}</div>
          )}
        </div>
      </div>
    </div>
  );
}
