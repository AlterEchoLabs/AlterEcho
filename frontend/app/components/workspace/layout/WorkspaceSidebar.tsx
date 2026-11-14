import type { Section } from "../types";

const navigation: { id: Section; label: string; icon: string; group: "Research" | "Workspace" }[] = [
  { id: "overview", label: "Overview", icon: "◫", group: "Research" },
  { id: "explorer", label: "Planetary explorer", icon: "◎", group: "Research" },
  { id: "discovery", label: "Analogue discovery", icon: "⌕", group: "Research" },
  { id: "comparison", label: "Comparison lab", icon: "▤", group: "Research" },
  { id: "data", label: "Scientific data", icon: "▦", group: "Workspace" },
  { id: "assistant", label: "Research assistant", icon: "✧", group: "Workspace" },
  { id: "mission", label: "Mission planner", icon: "⌖", group: "Workspace" },
  { id: "reports", label: "Research reports", icon: "↗", group: "Workspace" },
];

export default function WorkspaceSidebar({ activeSection, resultCount, version, onSectionChange }: {
  activeSection: Section;
  resultCount: number;
  version: string;
  onSectionChange: (section: Section) => void;
}) {
  return <aside className="app-sidebar">
    <button className="brand-lockup" type="button" onClick={() => onSectionChange("overview")} aria-label="TerraLuna AI overview">
      <span className="brand-symbol"><span /></span><span className="brand-name">TERRA<span>LUNA</span><small>PLANETARY ANALOGUE RESEARCH</small></span>
    </button>
    <div className="sidebar-project"><span className="project-index">FIELD STUDY / 01</span><strong>Jezero analogue survey</strong><small>Earth ↔ Mars terrain study</small></div>
    <nav className="primary-nav" aria-label="Main navigation">
      {(["Research", "Workspace"] as const).map((group) => <div className="nav-group" key={group}>
        <span className="nav-group-title">{group}</span>
        {navigation.filter((item) => item.group === group).map((item) => <button type="button" key={item.id} aria-label={item.label} className={`nav-link ${activeSection === item.id ? "active" : ""}`} onClick={() => onSectionChange(item.id)} aria-current={activeSection === item.id ? "page" : undefined}>
          <span className="nav-icon" aria-hidden="true">{item.icon}</span><span>{item.label}</span>
          {item.id === "comparison" && resultCount > 0 && <b className="nav-count">{resultCount}</b>}
        </button>)}
      </div>)}
    </nav>
    <div className="sidebar-bottom"><span className="sidebar-bottom-mark">NASA SPACE APPS · 2026</span><p>Explore Earth environments as analogues for planetary terrain.</p><span className="version-label">TERRALUNA AI <i>·</i> {version}</span></div>
  </aside>;
}
