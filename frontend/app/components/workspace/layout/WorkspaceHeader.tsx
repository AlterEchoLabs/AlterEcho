import type { HealthResponse } from "../../../../lib/api";

export default function WorkspaceHeader({ title, health, backendError, onToggleSidebar, sidebarCollapsed }: { title: string; health: HealthResponse | null; backendError: boolean; onToggleSidebar: () => void; sidebarCollapsed: boolean }) {
  return <header className="topbar">
    <div className="topbar-title"><button className="topbar-menu-button" type="button" onClick={onToggleSidebar} aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}>{sidebarCollapsed ? "»" : "«"}</button><div><span>RESEARCH WORKSPACE</span><h1>{title}</h1></div></div>
    <div className="topbar-meta">
      <div className={`connection-pill ${backendError ? "disconnected" : !health ? "checking" : ""}`}>
        <span className="connection-dot" /><span>{backendError ? "Backend unavailable" : !health ? "Connecting to API" : `${health.data_counts.rankable_real_candidates} real Earth sites available`}</span>
      </div>
      <div className="data-mode-pill"><span>DATA MODE</span><strong>{health ? health.data_mode.replaceAll("_", " ") : "—"}</strong></div>
    </div>
  </header>;
}
