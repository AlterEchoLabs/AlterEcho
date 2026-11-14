export type Planet = "earth" | "mars" | "moon";
export type Section = "overview" | "explorer" | "discovery" | "comparison" | "data" | "assistant" | "mission" | "reports";
export type DataFilter = "all" | "real_processed" | "planned" | "metadata_only";

export const sectionTitles: Record<Section, string> = {
  overview: "Research overview",
  explorer: "Planetary explorer",
  discovery: "Analogue discovery",
  comparison: "Comparison lab",
  data: "Scientific data center",
  assistant: "AI research assistant",
  mission: "Mission planner",
  reports: "Research reports",
};
