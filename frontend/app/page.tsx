"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import PlanetSelector from "./components/PlanetSelector";
import AssistantPage from "./components/workspace/pages/AssistantPage";
import CandidatePanel from "./components/workspace/discovery/CandidatePanel";
import DataCenterPage from "./components/workspace/pages/DataCenterPage";
import MissionPlannerPage from "./components/workspace/pages/MissionPlannerPage";
import OverviewHeader from "./components/workspace/overview/OverviewHeader";
import OverviewStats from "./components/workspace/overview/OverviewStats";
import PlanetStage from "./components/workspace/explorer/PlanetStage";
import ReportsPage from "./components/workspace/pages/ReportsPage";
import ResultsPanel from "./components/workspace/discovery/ResultsPanel";
import SectionToolbar from "./components/workspace/layout/SectionToolbar";
import WorkspaceHeader from "./components/workspace/layout/WorkspaceHeader";
import WorkspaceSidebar from "./components/workspace/layout/WorkspaceSidebar";
import { api, type AoiFeature, type ComparisonResult, type HealthResponse, type Site, type SourceManifest, type TerrainSummary } from "../lib/api";
import { BRAND } from "../config/brand";
import type { DataFilter, Planet, Section } from "./components/workspace/types";
import { sectionTitles } from "./components/workspace/types";

export default function Home() {
  const [activeSection, setActiveSection] = useState<Section>("overview");
  const [activePlanet, setActivePlanet] = useState<Planet>("earth");
  const [isZoomedIn, setIsZoomedIn] = useState(false);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [backendError, setBackendError] = useState(false);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [sites, setSites] = useState<Site[]>([]);
  const [reference, setReference] = useState<Site | null>(null);
  const [focusedCandidateId, setFocusedCandidateId] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [dataFilter, setDataFilter] = useState<DataFilter>("real_processed");
  const [candidateQuery, setCandidateQuery] = useState("");
  const [regionFilter, setRegionFilter] = useState("all");
  const [environmentFilter, setEnvironmentFilter] = useState("all");
  const [methodologyVersion, setMethodologyVersion] = useState<"terrain-v3.0" | "terrain-v2.0">("terrain-v3.0");
  const [aois, setAois] = useState<AoiFeature[]>([]);
  const [terrain, setTerrain] = useState<Record<string, TerrainSummary>>({});
  const [sources, setSources] = useState<SourceManifest[]>([]);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [comparisonLoading, setComparisonLoading] = useState(false);
  const [comparisonError, setComparisonError] = useState<string | null>(null);
  const [comparisonAttempted, setComparisonAttempted] = useState(false);
  const [resultsStale, setResultsStale] = useState(false);
  const [terrainError, setTerrainError] = useState<{ siteId: string; message: string } | null>(null);
  const [results, setResults] = useState<ComparisonResult[]>([]);

  useEffect(() => {
    let active = true;
    Promise.all([api.health(), api.sites("earth"), api.sites("mars")])
      .then(([healthResponse, earthSites, marsSites]) => {
        if (!active) return;
        setHealth(healthResponse);
        setSites(earthSites);
        setBackendError(false);
        setCatalogError(null);
        setReference(marsSites.find((site) => site.id === "mars-jezero") ?? null);
        setSelectedIds(earthSites.filter((site) => site.data_status === "real_processed").map((site) => site.id));
      })
      .catch((error) => {
        if (active) {
          setBackendError(true);
          setCatalogError(error instanceof Error ? error.message : "Backend unavailable");
        }
      })
      .finally(() => { if (active) setCatalogLoading(false); });

    Promise.allSettled([
      api.aoi("earth-atacama"),
      api.aoi("earth-upper-mustang"),
      api.aoi("earth-ladakh"),
      api.aoi("mars-jezero"),
      api.terrain("mars-jezero"),
      api.terrain("earth-atacama"),
      api.sources(),
    ]).then((items) => {
      if (!active) return;
      setAois(items.slice(0, 4).flatMap((item) => item.status === "fulfilled" ? [item.value as AoiFeature] : []));
      const summaries = items.slice(4, 6).flatMap((item) => item.status === "fulfilled" ? [item.value as TerrainSummary] : []);
      setTerrain(Object.fromEntries(summaries.map((summary) => [summary.site_id, summary])));
      if (items[6].status === "fulfilled") setSources(items[6].value as SourceManifest[]);
    });
    return () => { active = false; };
  }, []);

  const clearComparisonState = useCallback(() => {
    setResults([]);
    setResultsStale(false);
    setComparisonError(null);
    setComparisonAttempted(false);
  }, []);

  const handleSiteSelect = useCallback((site: Site) => {
    setFocusedCandidateId(site.id);
    setResultsStale(false);
  }, []);

  const toggleCandidate = useCallback((id: string) => {
    clearComparisonState();
    setSelectedIds((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);
  }, [clearComparisonState]);

  const focusCandidate = useCallback((id: string) => {
    setFocusedCandidateId(id);
    clearComparisonState();
  }, [clearComparisonState]);
  const selectAllReal = useCallback(() => {
    setSelectedIds(sites.filter((site) => site.data_status === "real_processed").map((site) => site.id));
    clearComparisonState();
  }, [sites, clearComparisonState]);

  const compareTerrain = useCallback(async () => {
    const eligibleIds = selectedIds.filter((id) => sites.some((site) => site.id === id && site.data_status === "real_processed"));
    if (!eligibleIds.length) {
      setComparisonError("Select at least one real Earth site.");
      setComparisonAttempted(true);
      return;
    }
    setComparisonLoading(true);
    setComparisonError(null);
    setComparisonAttempted(true);
    try {
      const response = await api.discover(eligibleIds, methodologyVersion);
      setResults(response.real_results);
      setResultsStale(false);
      setActiveSection("comparison");
    } catch (error) {
      setResultsStale(results.length > 0);
      setComparisonError(error instanceof Error ? error.message : "Comparison request failed");
    } finally {
      setComparisonLoading(false);
    }
  }, [selectedIds, sites, results.length, methodologyVersion]);

  const downloadResult = useCallback((result: ComparisonResult) => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(result, null, 2)], { type: "application/json" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${result.reference_site.id}-${result.candidate_site.id}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }, []);

  const downloadReport = useCallback(() => {
    const report = {
      generated_at: new Date().toISOString(),
      reference_site_id: results[0]?.reference_site.id ?? null,
      methodology_version: results[0]?.methodology_version ?? health?.methodology_version ?? null,
      results,
    };
    const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: "application/json" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `terraluna-research-report-${new Date().toISOString().slice(0, 10)}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }, [health?.methodology_version, results]);

  const selectedSite = useMemo(
    () => sites.find((site) => site.id === focusedCandidateId) ?? sites.find((site) => site.id === "earth-atacama") ?? sites[0] ?? null,
    [sites, focusedCandidateId],
  );
  useEffect(() => {
    if (!selectedSite || selectedSite.data_status !== "real_processed" || terrain[selectedSite.id]) return;
    const controller = new AbortController();
    api.terrain(selectedSite.id, controller.signal)
      .then((summary) => {
        setTerrain((current) => ({ ...current, [summary.site_id]: summary }));
        setTerrainError((current) => current?.siteId === summary.site_id ? null : current);
      })
      .catch((error) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setTerrainError({ siteId: selectedSite.id, message: error instanceof Error ? error.message : "Terrain summary unavailable" });
      });
    return () => controller.abort();
  }, [selectedSite, terrain]);

  const candidateCounts = useMemo(() => ({
    all: sites.length,
    real_processed: sites.filter((site) => site.data_status === "real_processed").length,
    planned: sites.filter((site) => site.data_status === "planned").length,
    metadata_only: sites.filter((site) => site.data_status === "metadata_only").length,
  }), [sites]);

  const regions = useMemo(() => [...new Set(sites.map((site) => site.country_or_region))].sort(), [sites]);
  const environments = useMemo(() => [...new Set(sites.map((site) => site.analog_type))].sort(), [sites]);
  const filteredSites = useMemo(() => sites.filter((site) => {
    const matchesStatus = dataFilter === "all" || site.data_status === dataFilter;
    const search = candidateQuery.trim().toLowerCase();
    const matchesQuery = !search || [site.name, site.country_or_region, site.short_description, ...site.relevant_characteristics].some((value) => value.toLowerCase().includes(search));
    return matchesStatus && matchesQuery && (regionFilter === "all" || site.country_or_region === regionFilter) && (environmentFilter === "all" || site.analog_type === environmentFilter);
  }), [sites, dataFilter, candidateQuery, regionFilter, environmentFilter]);

  const earthAois = useMemo(() => aois.filter((aoi) => aoi.properties.planetary_body === "earth"), [aois]);
  const referenceTerrain = terrain["mars-jezero"];
  const selectedAoi = aois.find((aoi) => aoi.properties.site_id === selectedSite?.id);
  const referenceAoi = aois.find((aoi) => aoi.properties.site_id === "mars-jezero") ?? null;
  const selectedTerrain = selectedSite ? terrain[selectedSite.id] : undefined;
  const selectedSourceId = selectedSite ? ({
    "earth-atacama": "earth-atacama-srtmgl1",
    "earth-upper-mustang": "earth-upper-mustang-srtmgl1",
    "earth-ladakh": "earth-ladakh-srtmgl1",
  } as Record<string, string>)[selectedSite.id] : undefined;
  const selectedSource = sources.find((source) => source.source_id === selectedSourceId);
  const jezeroSource = sources.find((source) => source.source_id === "mars-jezero-ctx-dem");
  const selectedRealCount = selectedIds.filter((id) => sites.some((site) => site.id === id && site.data_status === "real_processed")).length;
  const comparisonButtonLabel = comparisonLoading ? "Comparing..." : selectedRealCount ? `Compare ${selectedRealCount} site${selectedRealCount === 1 ? "" : "s"}` : "Select real sites to compare";
  const activeTitle = sectionTitles[activeSection];
  const realResultCount = results.filter((result) => result.comparison_classification === "real_comparison").length;
  const previewResultCount = results.filter((result) => result.comparison_classification !== "real_comparison").length;
  const sharedWorkspace = ["overview", "explorer", "discovery", "comparison"].includes(activeSection);

  return <main className="app-shell" data-application-id={BRAND.applicationId} data-build-identifier={BRAND.buildIdentifier} data-application-version={BRAND.applicationVersion}>
    <WorkspaceSidebar activeSection={activeSection} resultCount={results.length} version={health?.application_version ?? "FRONTEND"} onSectionChange={setActiveSection} />
    <div className="app-main">
      <WorkspaceHeader title={activeTitle} health={health} backendError={backendError} />
      <div className="page-content">
        {activeSection === "overview" && <OverviewHeader referenceName={reference?.name ?? "Jezero Crater"} referenceTerrain={referenceTerrain} />}
        {activeSection === "overview" && <OverviewStats health={health} />}
        <div className={`workspace-shell ${sharedWorkspace ? "is-visible" : "is-hidden"}`} aria-hidden={!sharedWorkspace}>
          <SectionToolbar section={activeSection} title={activeTitle} health={health} />
          <div className="selector-container"><PlanetSelector activePlanet={activePlanet} onChange={setActivePlanet} /></div>
          <div className={`dashboard-grid dashboard-grid-${activeSection}`} data-testid={activeSection === "explorer" ? "planetary-explorer-view" : undefined}>
            {activeSection !== "comparison" && <PlanetStage
              activePlanet={activePlanet}
              activeSection={activeSection}
              sites={sites}
              filteredSites={filteredSites}
              aois={earthAois}
              focusedCandidateId={focusedCandidateId}
              catalogLoading={catalogLoading}
              reference={reference}
              referenceTerrain={referenceTerrain}
              referenceAoi={referenceAoi}
              jezeroSource={jezeroSource}
              isZoomedIn={isZoomedIn}
              onPlanetChange={setActivePlanet}
              onSiteSelect={handleSiteSelect}
              onZoomChange={setIsZoomedIn}
            />}
            {activeSection !== "explorer" && activeSection !== "comparison" && <section className={`workspace-panel workspace-panel-${activeSection}`} aria-label="Terrain comparison workspace">
              <CandidatePanel
                sites={filteredSites}
                selectedIds={selectedIds}
                focusedCandidateId={focusedCandidateId}
                dataFilter={dataFilter}
                candidateCounts={candidateCounts}
                candidateQuery={candidateQuery}
                regionFilter={regionFilter}
                environmentFilter={environmentFilter}
                regions={regions}
                environments={environments}
                reference={reference}
                referenceTerrain={referenceTerrain}
                catalogLoading={catalogLoading}
                catalogError={catalogError}
                realSitesAvailable={candidateCounts.real_processed > 0}
                selectedRealCount={selectedRealCount}
                comparisonButtonLabel={comparisonButtonLabel}
                comparisonLoading={comparisonLoading}
                backendError={backendError}
                comparisonError={comparisonError}
                methodologyVersion={methodologyVersion}
                onQueryChange={setCandidateQuery}
                onRegionChange={setRegionFilter}
                onEnvironmentChange={setEnvironmentFilter}
                onDataFilterChange={(filter) => { setDataFilter(filter); clearComparisonState(); }}
                onSelectAll={selectAllReal}
                onToggle={toggleCandidate}
                onFocus={focusCandidate}
                onCompare={compareTerrain}
                onMethodologyChange={(value) => { setMethodologyVersion(value); clearComparisonState(); }}
              />
              {activeSection === "overview" && <ResultsPanel
                results={results}
                resultsStale={resultsStale}
                comparisonAttempted={comparisonAttempted}
                realResultCount={realResultCount}
                previewResultCount={previewResultCount}
                selectedSite={selectedSite}
                selectedAoi={selectedAoi}
                selectedTerrain={selectedTerrain}
                selectedSource={selectedSource}
                terrainError={terrainError}
                onDownload={downloadResult}
              />}
            </section>}
            {activeSection === "comparison" && <section className="comparison-lab" data-testid="comparison-lab-view" aria-label="Comparison results">
              <div className="comparison-lab-actions">
                <p className="panel-muted">{results.length ? "Review the returned terrain evidence and provenance below." : "Run a comparison from Analogue Discovery to see evidence here."}</p>
                <button className="button button-secondary" type="button" onClick={() => setActiveSection("discovery")}>Edit site selection <span>→</span></button>
              </div>
              <ResultsPanel
                results={results}
                resultsStale={resultsStale}
                comparisonAttempted={comparisonAttempted}
                realResultCount={realResultCount}
                previewResultCount={previewResultCount}
                selectedSite={selectedSite}
                selectedAoi={selectedAoi}
                selectedTerrain={selectedTerrain}
                selectedSource={selectedSource}
                terrainError={terrainError}
                onDownload={downloadResult}
              />
            </section>}
          </div>
        </div>
        {activeSection === "data" && <DataCenterPage sites={sites} sources={sources} terrain={terrain} aois={aois} onNavigate={setActiveSection} />}
        {activeSection === "assistant" && <AssistantPage />}
        {activeSection === "mission" && <MissionPlannerPage reference={reference} referenceTerrain={referenceTerrain} selectedRealCount={selectedRealCount} realCandidateCount={candidateCounts.real_processed} results={results} onNavigate={setActiveSection} />}
        {activeSection === "reports" && <ReportsPage results={results} health={health} onDownload={downloadResult} onDownloadReport={downloadReport} onNavigate={setActiveSection} />}
      </div>
      <footer className="app-footer"><span>TERRALUNA AI <i>·</i> SCIENTIFIC EXPLORATION WORKSPACE</span><span>Terrain similarity is a partial analogue, not a measure of habitability.</span></footer>
    </div>
  </main>;
}
