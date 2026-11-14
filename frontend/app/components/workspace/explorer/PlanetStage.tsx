"use client";

import dynamic from "next/dynamic";
import SiteImageryViewer from "../../SiteImageryViewer";
import type { AoiFeature, Site, SourceManifest, TerrainSummary } from "../../../../lib/api";
import type { Planet, Section } from "../types";

const CandidateMap = dynamic<{ onZoomChange: (value: boolean) => void; sites: Site[]; aois: AoiFeature[]; focusedSiteId: string | null; onSelect: (site: Site) => void }>(() => import("../../CandidateMap"), { ssr: false });
const SpaceScene = dynamic<{ onMoonClick: () => void; showOrbit: boolean; active: boolean }>(() => import("../../SpaceScene"), { ssr: false });
const PlanetViewer = dynamic(() => import("../../PlanetViewer"), { ssr: false });

export default function PlanetStage({ activePlanet, activeSection, sites, filteredSites, aois, focusedCandidateId, catalogLoading, reference, referenceTerrain, referenceAoi, jezeroSource, isZoomedIn, onPlanetChange, onSiteSelect, onZoomChange }: {
  activePlanet: Planet;
  activeSection: Section;
  sites: Site[];
  filteredSites: Site[];
  aois: AoiFeature[];
  focusedCandidateId: string | null;
  catalogLoading: boolean;
  reference: Site | null;
  referenceTerrain?: TerrainSummary;
  referenceAoi?: AoiFeature | null;
  jezeroSource?: SourceManifest;
  isZoomedIn: boolean;
  onPlanetChange: (planet: Planet) => void;
  onSiteSelect: (site: Site) => void;
  onZoomChange: (zoomedIn: boolean) => void;
}) {
  return <section className={`planet-stage planet-stage-${activePlanet}`} aria-label={`${activePlanet} exploration view`}>
      {activePlanet === "earth" && <>
        <div className="earth-map">
          {catalogLoading ? <div className="stage-message">Loading backend candidates…</div> : sites.length
            ? <CandidateMap sites={filteredSites} aois={aois} focusedSiteId={focusedCandidateId} onSelect={onSiteSelect} onZoomChange={onZoomChange} />
            : <div className="stage-message error-state">No backend candidates are available. Start the API and retry.</div>}
        </div>
        <div className="map-overlay map-overlay-top"><span className="live-indicator" />EARTH · SATELLITE</div>
        <div className="map-overlay map-overlay-bottom">{filteredSites.length} catalog sites <span>·</span> Drag to rotate <span>·</span> Scroll to zoom</div>
      </>}
      {activePlanet === "mars" && <>
        <div className="planet-viewer"><PlanetViewer planet="mars" /></div>
        <div className="reference-overlay">
          <span>PLANETARY REFERENCE · {referenceTerrain?.data_status === "real_processed" ? "PROCESSED TERRAIN" : "CATALOG"}</span>
          <h2>{reference?.name ?? "Jezero Crater"}</h2>
          <p>{reference?.short_description ?? "Reference metadata unavailable while the backend is offline."}</p>
          <small>{referenceTerrain?.aoi_id ?? "AOI unavailable"} · {referenceTerrain?.analysis_width_m ? `${(referenceTerrain.analysis_width_m / 1000).toFixed(2)} km square` : "size unavailable"} · {referenceTerrain?.resolution_m ?? "—"} m grid</small>
          <p className="source-line">{jezeroSource?.provider ?? "Source unavailable"} · {jezeroSource?.instrument ?? "instrument unavailable"}<br />Coverage {referenceTerrain ? `${(referenceTerrain.valid_coverage_fraction * 100).toFixed(1)}%` : "—"} · Method {String(referenceTerrain?.calculation_metadata.methodology_version ?? "—")}</p>
        </div>
        {reference && referenceAoi && <div className="mars-imagery-panel"><SiteImageryViewer site={reference} aoi={referenceAoi} /></div>}
        <div className="map-overlay map-overlay-top">MARS · 3D TERRAIN MODEL</div>
      </>}
      {activePlanet === "moon" && <div className="coming-soon">
        <div className="moon-preview"><PlanetViewer planet="moon" /></div>
        <div className="coming-copy"><span>LUNAR EXPLORATION</span><h2>Interactive lunar surface</h2><p>The 3D Moon model is available to explore. Lunar terrain analysis and comparison are not connected to the current backend.</p><span className="future-badge">ANALYSIS PIPELINE · PLANNED</span></div>
      </div>}
      <SpaceScene onMoonClick={() => onPlanetChange("moon")} showOrbit={!isZoomedIn} active={activeSection !== "data" && activeSection !== "assistant" && activeSection !== "mission" && activeSection !== "reports" && activePlanet === "earth"} />
  </section>;
}
