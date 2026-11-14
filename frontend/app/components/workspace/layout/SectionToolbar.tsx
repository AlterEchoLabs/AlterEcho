import type { HealthResponse } from "../../../../lib/api";
import type { Section } from "../types";

export default function SectionToolbar({ section, title, health }: { section: Section; title: string; health: HealthResponse | null }) {
  const heading = section === "overview" ? "Explore the analogue landscape" : title;
  const eyebrowLabels: Record<Section, string> = {
    overview: "LIVE EXPLORATION",
    explorer: "INTERACTIVE GLOBE",
    discovery: "DISCOVERY WORKFLOW",
    comparison: "TERRAIN EVIDENCE",
    data: "SCIENTIFIC DATA",
    assistant: "AI RESEARCH",
    mission: "MISSION WORKSPACE",
    reports: "RESEARCH OUTPUTS",
  };
  const eyebrow = eyebrowLabels[section];

  return <div className="section-toolbar">
    <div><span className="eyebrow">{eyebrow}</span><h2>{heading}</h2></div>
    <div className="section-toolbar-meta"><span className="live-indicator" />{health ? `Updated from API · ${new Date(health.timestamp).toLocaleDateString()}` : "Waiting for backend data"}</div>
  </div>;
}
