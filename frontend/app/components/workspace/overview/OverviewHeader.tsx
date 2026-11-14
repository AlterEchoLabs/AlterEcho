import type { TerrainSummary } from "../../../../lib/api";

export default function OverviewHeader({ referenceName, referenceTerrain }: { referenceName: string; referenceTerrain?: TerrainSummary }) {
  return <section className="overview-intro">
    <div>
      <p className="eyebrow">PLANETARY ANALOGUE RESEARCH <span>·</span> WORKSPACE 01</p>
      <h2>Earth terrain.<br /><em>Planetary perspective.</em></h2>
      <p>Explore terrestrial environments and compare validated terrain metrics with the Jezero Crater reference on Mars.</p>
    </div>
    <div className="overview-intro-aside"><span className="intro-orbit">◎</span><div><span>ACTIVE REFERENCE</span><strong>{referenceName}</strong><small>MARS · {referenceTerrain?.resolution_m ? `${referenceTerrain.resolution_m} M GRID` : "TERRAIN GRID UNAVAILABLE"}</small></div></div>
  </section>;
}
