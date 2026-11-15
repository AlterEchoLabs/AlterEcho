"""Read-only data audit; writes a versioned registry/report only with --write.

No provider downloads, credentials or scientific parameter changes. Unknown metadata
remain null and are listed, never inferred from imagery or regional descriptions.
"""
import argparse
from datetime import datetime, timezone
from functools import lru_cache
import json
from pathlib import Path

from app.services.geospatial_service import BACKEND_ROOT, GEO_DATA, canonical_text_sha256, sha256_file
from app.services.provenance_service import future_date, validate_scoring_artifact
from app.models.provenance import SourceRegistry

APP_DATA = BACKEND_ROOT / "app/data"
OUT = GEO_DATA / "manifests/acquisition-v1"


@lru_cache(maxsize=128)
def binary_info(filename: str, expected: str | None) -> dict:
    path = (BACKEND_ROOT / filename).resolve()
    if not path.is_relative_to(BACKEND_ROOT.resolve()) or path.is_symlink():
        return {"path": filename, "status": "rejected", "reason": "unsafe path"}
    if not path.is_file():
        return {"path": filename, "status": "blocked", "reason": "local source absent"}
    actual = sha256_file(path)
    out = {"path": filename, "byte_size": path.stat().st_size, "sha256": actual,
           "expected_sha256": expected, "status": "verified" if actual == expected else "rejected"}
    if path.suffix.lower() in {".tif", ".hgt", ".img"}:
        import rasterio
        with rasterio.open(path) as src:
            out["raster"] = {"driver": src.driver, "crs": str(src.crs), "resolution": list(src.res),
                "bounds": list(src.bounds), "nodata": src.nodata, "dimensions": [src.width, src.height], "units": list(src.units)}
            if not src.crs:
                out["status"] = "rejected"
    return out


def build() -> dict:
    datasets = json.loads((APP_DATA / "datasets.json").read_text(encoding="utf-8"))
    roles = json.loads((APP_DATA / "data_roles.json").read_text(encoding="utf-8"))["roles"]
    rolemap = {"scored_input": "scored", "uncertainty_input": "diagnostic", "quality_input": "quality-mask",
               "display_context": "display-only", "context_measurement": "diagnostic", "literature_context": "context-only"}
    records = []
    for d in datasets:
        role = next((r for r in roles if r.get("registry_id") == d["dataset_id"]), {})
        records.append({"dataset_id": d["dataset_id"], "provider": d["provider"], "mission_instrument": role.get("product"),
            "product_collection": d.get("product_id"), "collection_version": d.get("version"),
            "official_landing_page": d.get("official_landing_page"), "doi_or_pds_identifier": d.get("doi"),
            "discovery_endpoint": d.get("api_endpoint"), "body": d["celestial_body"], "measured_variable": role.get("measures"),
            "native_resolution": d.get("spatial_resolution"), "analysis_resolution": role.get("analysis_resolution"),
            "spatial_support": d.get("aois_covered"), "crs": None, "vertical_datum": None, "units": None,
            "observation_interval": d.get("temporal_coverage"), "processing_level": d.get("integration_type"),
            "retrieval_date": None, "license": d.get("license_or_usage_notes"), "authentication": d.get("authentication_requirement"),
            "raw_filename": None, "byte_size": None, "sha256": None, "processing_software": None,
            "role": rolemap.get(role.get("role"), "context-only"), "known_limitations": d["known_limitations"],
            "status": "planned", "status_reason": "Collection metadata; exact artifacts are separately audited below, not all collection products are verified."})
    sites = []
    config = json.loads((APP_DATA / "analogue.v1.json").read_text(encoding="utf-8"))
    for p in sorted((GEO_DATA / "processed/terrain-v5").glob("*.json")):
        a = json.loads(p.read_text(encoding="utf-8"))
        m = json.loads((GEO_DATA / "manifests" / f"{a['source_id']}.json").read_text(encoding="utf-8"))
        errors = validate_scoring_artifact(p, a)
        source = binary_info(a["source_file"], a["source_sha256"])
        files = [source]
        for tile in m.get("tiles", []):
            for name, key in (("filename", "sha256_checksum"), ("extracted_filename", "extracted_sha256_checksum")):
                if tile.get(name):
                    files.append(binary_info("data/raw/" + tile[name], tile.get(key)))
        exclusion = config["aoi_exclusions"].get(a["site_id"])
        eligible = not errors and source["status"] == "verified" and not exclusion and a["body"] != "moon"
        records.append({"dataset_id": a["source_id"], "provider": m["provider"], "mission_instrument": f"{m['mission']} / {m['instrument']}",
            "product_collection": m["product_name"], "collection_version": m.get("product_version"),
            "official_landing_page": m["source_page_url"], "doi_or_pds_identifier": m.get("doi"), "discovery_endpoint": m["download_url"],
            "body": a["body"], "measured_variable": "surface elevation", "native_resolution": m["native_resolution"],
            "analysis_resolution": "60 m primary; 120/240 m sensitivity", "spatial_support": a["aoi_id"],
            "crs": source.get("raster", {}).get("crs"), "vertical_datum": None, "units": "metres",
            "observation_interval": None, "processing_level": "local elevation input; may be reprojected crop or mosaic, not necessarily immutable archive file",
            "retrieval_date": m["access_date"], "license": m["license_or_use_constraints"],
            "authentication": "Earthdata for SRTM re-acquisition" if a["body"] == "earth" else "public",
            "raw_filename": a["source_file"], "byte_size": source.get("byte_size"), "sha256": source.get("sha256"),
            "processing_software": {"method": a["methodology_version"], "command": "python -m app.scripts.analogue_v1_calibration" if a["body"] == "earth" or a["site_id"] == "mars-jezero" else "python -m app.scripts.analogue_v1_references"},
            "role": "scored" if eligible else "diagnostic", "known_limitations": ["No field validation. Source vertical datum and exact observation interval require product-label review.", "Native post spacing is not effective resolution."],
            "status": "verified" if not errors and source["status"] == "verified" else "rejected",
            "status_reason": "Byte integrity and recorded provenance checked; not independent scientific validation.",
            "artifact": {"path": p.relative_to(BACKEND_ROOT).as_posix(), "sha256_lf": canonical_text_sha256(p)},
            "quality": {"feature_coverage": {k: v["coverage"] for k, v in a["scales"]["60"]["features"].items()}, "mask": a.get("exclusion")},
            "files": files})
        sites.append({"site_id": a["site_id"], "body": a["body"], "aoi_id": a["aoi_id"],
            "center": [a["center_longitude"], a["center_latitude"]], "width_m": a["core_width_m"],
            "source_status": source["status"], "validation_errors": errors, "scoring_eligible": eligible,
            "exclusion_reason": exclusion or ("Reference fails tolerance/resolution-floor gate; distances only" if a["body"] == "moon" else None)})
    imagery = []
    for p in sorted((GEO_DATA / "processed/imagery").glob("*.json")):
        a = json.loads(p.read_text(encoding="utf-8"))
        if "imagery_id" not in a:
            continue
        filename = (a.get("preview_url") or "").split("/")[-1]
        local = GEO_DATA / "processed/imagery" / filename
        errors = []
        for key in ("acquisition_datetime", "publication_datetime", "cache_date"):
            if future_date(a.get(key)):
                errors.append(f"future {key}")
        if a.get("preview_checksum") and (not local.is_file() or sha256_file(local) != a["preview_checksum"]):
            errors.append("display checksum mismatch or absent file")
        imagery.append({"metadata_path": p.relative_to(BACKEND_ROOT).as_posix(), "product_id": a.get("product_id"),
            "site_id": a["site_id"], "role": "display-only", "acquisition_datetime": a.get("acquisition_datetime"),
            "sha256": a.get("preview_checksum"), "validation_errors": errors})
    return {"schema_version": "source-registry-v1", "audited_at": datetime.now(timezone.utc).isoformat(),
        "verification_scope": "Local byte checksums, recorded official provenance, AOI identity, dates and measurement metadata; not external or expert validation.",
        "records": records, "sites": sites, "imagery": imagery,
        "unknown_metadata_policy": "Null means not established; collection-level entries do not claim local acquisition.",
        "new_products_acquired": [], "blocked_acquisitions": [],
        "scientific_limitations": ["Only terrain may score. No expert-labelled predictive accuracy.", "Archive labels, effective resolution and vertical datum need specialist review."]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    result = build()
    SourceRegistry.model_validate(result)
    if args.write:
        OUT.mkdir(parents=True, exist_ok=True)
        text = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
        (OUT / "source-registry.json").write_text(text, encoding="utf-8", newline="\n")
        schema = APP_DATA / "source-registry.schema.json"
        schema.write_text(json.dumps(SourceRegistry.model_json_schema(), indent=2) + "\n", encoding="utf-8", newline="\n")
    failures = [s for s in result["sites"] if s["validation_errors"] or s["source_status"] != "verified"]
    failures += [i for i in result["imagery"] if i["validation_errors"]]
    print(json.dumps({"sites": len(result["sites"]), "imagery": len(result["imagery"]), "failures": failures}, indent=2))
    raise SystemExit(bool(failures))


if __name__ == "__main__":
    main()
