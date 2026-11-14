import type { HealthResponse } from "../../../../lib/api";

export default function OverviewStats({ health }: { health: HealthResponse | null }) {
  return <section className="overview-stats" aria-label="Backend data summary">
    <article className="stat-card stat-card-primary"><span className="stat-icon">◎</span><div><small>RANKABLE CANDIDATES</small><strong>{health?.data_counts.rankable_real_candidates ?? "—"}</strong><span>Real processed Earth sites</span></div><i>01</i></article>
    <article className="stat-card"><span className="stat-icon">▦</span><div><small>PROCESSED DATASETS</small><strong>{health?.data_counts.real_processed_sites ?? "—"}</strong><span>Across the connected catalog</span></div><i>02</i></article>
    <article className="stat-card"><span className="stat-icon">◌</span><div><small>PREVIEW FIXTURES</small><strong>{health?.data_counts.demo_fixture_sites ?? "—"}</strong><span>Kept distinct from real data</span></div><i>03</i></article>
    <article className="stat-card"><span className="stat-icon">⌗</span><div><small>METADATA ONLY</small><strong>{health?.data_counts.metadata_only_sites ?? "—"}</strong><span>Not included in rankings</span></div><i>04</i></article>
  </section>;
}
