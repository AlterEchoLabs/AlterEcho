"use client";

import { useState, type ReactNode } from "react";
import { api, apiV3, safeExternalUrl, resolveApiUrl, type DatasetRecord } from "../../lib/api";
import { RoleCard } from "../components/atlas/ResultPanel";
import { useKeyed } from "../../lib/hooks";
import textures from "../../public/textures/textures.manifest.json";

type Registry = DatasetRecord & { integration_type?: string | null; aois_covered?: string[]; acquisition_period?: string | null; authentication_requirement?: string | null; license_or_usage_notes?: string | null; spatial_resolution: string | null };

function Ext({ href, children }: { href: string | null | undefined; children: ReactNode }) {
  const safe = safeExternalUrl(href);
  return safe ? <a href={safe} target="_blank" rel="noreferrer noopener">{children}</a> : <>{children}</>;
}

const ROLE = (d: Registry) => /quality mask/.test(d.local_status) ? "quality mask"
  : /limited lunar/.test(d.local_status) ? "diagnostic · distances only"
  : d.local_status.startsWith("processed") && !/context|display|sensitivity|regional/.test(d.local_status) ? "scored evidence"
  : /context/.test(d.local_status) ? "context only" : /display|visual/.test(d.local_status) ? "display only" : /sensitivity|regional/.test(d.local_status) ? "check only" : d.local_status;

export default function SourcesContent() {
  const registry = useKeyed("datasets", () => api.datasets() as Promise<Registry[]>);
  const manifests = useKeyed("sources", () => api.sources());
  const roles = useKeyed("roles", () => apiV3.dataRoles());
  const [query, setQuery] = useState("");
  const q = query.trim().toLowerCase();
  const rows = (registry.data ?? []).filter((d) => !q || [d.product_name, d.product_id, d.provider, d.celestial_body, d.scientific_dimension, d.local_status, ...(d.aois_covered ?? [])].join(" ").toLowerCase().includes(q));

  return (
    <article className="page page-wide">
      <h1>Data and sources</h1>
      <p className="intro">Every product AlterEcho uses or has evaluated, with exact IDs, what it is used for and what it is not. Scored evidence, context, display imagery and checks are kept separate. The interactive app never calls a data provider when you click; showcase results come from versioned artifacts produced by the scripts listed at the end.</p>

      <h2 id="why-this-data">Why each dataset is used</h2>
      <p className="muted">What each product measures, which calculation uses it, native versus analysis resolution, and what it cannot establish. Display imagery never enters a number.</p>
      {roles.error && <p className="error-inline">Data roles unavailable: {roles.error}</p>}
      <div className="why-list role-grid" data-testid="data-roles">{(roles.data ?? []).map((r) => <RoleCard key={r.id} role={r} />)}</div>

      <h2>Product registry</h2>
      <p><a href={resolveApiUrl("/api/v3/source-registry") ?? undefined} target="_blank" rel="noreferrer">Open machine-readable provenance</a> — exact local file checksums, source roles, AOI validation and audit scope. Null metadata means it has not been established.</p>
      <input className="search-input" type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search products, bodies, dimensions, sites…" aria-label="Search the product registry" />
      <p className="muted small">{rows.length} of {registry.data?.length ?? 0} records</p>
      {registry.error && <p className="error-inline">Registry unavailable: {registry.error}</p>}
      <div className="table-scroll" tabIndex={0} role="region" aria-label="Scrollable data table"><table className="data-table" data-testid="registry">
        <thead><tr><th>Product</th><th>Body · dimension</th><th>Role in AlterEcho</th><th>Resolution · period</th><th>Access</th><th>AOIs</th><th>Limitations</th></tr></thead>
        <tbody>{rows.map((d) => (
          <tr key={d.dataset_id}>
            <td><Ext href={d.official_landing_page}>{d.product_name}</Ext><br /><span className="mono small">{d.product_id ?? "—"}</span><br /><span className="muted small">{d.provider}</span>{d.doi && <><br /><span className="small">DOI {d.doi}</span></>}</td>
            <td>{d.celestial_body} · {d.scientific_dimension}</td>
            <td><strong>{ROLE(d)}</strong><br /><span className="small">{d.intended_project_use}</span><br /><span className="muted small">{d.integration_type}</span></td>
            <td className="small">{d.spatial_resolution ?? "—"}<br />{d.acquisition_period ?? ""}</td>
            <td className="small">{d.authentication_requirement ?? "—"}<br /><span className="muted">{d.license_or_usage_notes}</span></td>
            <td className="small">{d.aois_covered?.length ? d.aois_covered.join(", ") : "—"}</td>
            <td className="small">{d.known_limitations.join(" ")}</td>
          </tr>
        ))}</tbody>
      </table></div>

      <h2>Source manifests (terrain inputs)</h2>
      {manifests.data && (
        <div className="table-scroll" tabIndex={0} role="region" aria-label="Scrollable data table"><table className="data-table">
          <thead><tr><th>Source</th><th>Product</th><th>SHA-256 of the processed input</th><th>Citation</th></tr></thead>
          <tbody>{manifests.data.map((m) => (
            <tr key={m.source_id}>
              <td><Ext href={m.source_page_url}>{m.title}</Ext><br /><span className="muted small">{m.provider}</span></td>
              <td className="mono small">{m.product_name} {m.product_version ?? ""}</td>
              <td className="mono small">{(m as unknown as { extracted_sha256_checksum?: string; mosaic_sha256_checksum?: string }).mosaic_sha256_checksum ?? (m as unknown as { extracted_sha256_checksum?: string }).extracted_sha256_checksum ?? m.sha256_checksum ?? "—"}</td>
              <td className="small">{m.citation_text}</td>
            </tr>
          ))}</tbody>
        </table></div>
      )}

      <h2>Orientation globes</h2>
      <div className="table-scroll" tabIndex={0} role="region" aria-label="Scrollable data table"><table className="data-table">
        <thead><tr><th>Body</th><th>Mosaic</th><th>Attribution</th><th>Terms</th></tr></thead>
        <tbody>{textures.textures.map((t) => <tr key={t.body}><td>{t.body}</td><td><Ext href={t.landing_page}>{t.title}</Ext></td><td>{t.attribution}</td><td className="small">{t.terms}</td></tr>)}</tbody>
      </table></div>

      <h2>Reproduce (Git Bash, from backend/)</h2>
      <code className="formula" tabIndex={0}>{`python -m app.scripts.validate_catalog_integrity
python -m app.scripts.register_phase7_sites                 # AOIs, manifests, catalog entries
EARTHDATA_TOKEN=… python -m app.scripts.acquire_dataset --source-id earth-danakil-srtmgl1
python -m app.scripts.process_site_v3 --site-id earth-danakil --aoi-id earth-danakil-aoi-v1 --source-id earth-danakil-srtmgl1 --input data/raw/N14E040.hgt
python -m app.scripts.register_lunar_reference              # LOLA clip in metres + manifest
python -m app.scripts.acquire_planetary_computer_imagery --site-id earth-ladakh --aoi-id earth-ladakh-aoi-v1
python -m app.scripts.acquire_modis_lst ; python -m app.scripts.acquire_meda_ground_temperature
python -m app.scripts.terrain_v4_evaluation                 # placement, DEM, base rate, redundancy, MOLA
python -m app.scripts.refresh_gibs_date
python -m app.scripts.assess_aoi_landcover                  # ESA WorldCover built-up check per Earth window
python -m app.scripts.register_atacama_south                # Phase 9 uncontaminated Atacama window
python -m app.scripts.analogue_v1_calibration               # terrain-v5 quantiles, resolution floor, tau, negatives
python -m app.scripts.phase9_audit                          # v4 -> v1.0 decomposition tables`}</code>
    </article>
  );
}
