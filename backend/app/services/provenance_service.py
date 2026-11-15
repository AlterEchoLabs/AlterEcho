"""Validate the exact scored artifacts, and expose portable calculation provenance.

Raw-file verification is an explicit release operation, not a multi-GB API read.
Serving uses the committed derived checksum and source-manifest chain.
"""
from datetime import datetime, timezone
import json
from math import isfinite
from pathlib import Path
from urllib.parse import urlparse

from app.services.geospatial_service import BACKEND_ROOT, GEO_DATA, canonical_text_sha256

OFFICIAL_HOSTS = {"search.earthdata.nasa.gov", "data.lpdaac.earthdatacloud.nasa.gov",
    "astrogeology.usgs.gov", "stac.astrogeology.usgs.gov", "pds-geosciences.wustl.edu",
    "planetarycomputer.microsoft.com", "doi.org", "pds.nasa.gov"}


def official_url(value: str | None) -> bool:
    parsed = urlparse(value or "")
    return parsed.scheme == "https" and parsed.hostname in OFFICIAL_HOSTS and not parsed.username


def future_date(value: str | None, now: datetime | None = None) -> bool:
    if not value:
        return False
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp > (now or datetime.now(timezone.utc))


def validate_scoring_artifact(path: Path, art: dict) -> list[str]:
    errors = []
    checksum = path.with_suffix(".sha256")
    if not checksum.exists() or checksum.read_text().strip() != canonical_text_sha256(path):
        errors.append("derived checksum missing or mismatched")
    if art.get("methodology_version") != "terrain-v5.0":
        errors.append("unsupported processing method")
    if any(word in str(art.get("source_file", "")).lower() for word in ("fixture", "demo", "synthetic")):
        errors.append("test evidence prohibited")
    try:
        # IDs come from the catalog; prohibit path components even in edited artifacts.
        for field in ("source_id", "aoi_id", "site_id"):
            value = art[field]
            if not isinstance(value, str) or not value or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in value):
                raise ValueError("invalid identity")
        manifest = json.loads((GEO_DATA / "manifests" / f"{art['source_id']}.json").read_text(encoding="utf-8"))
        aoi = json.loads((GEO_DATA / "aoi" / f"{art['aoi_id']}.geojson").read_text(encoding="utf-8"))["properties"]
        if not official_url(manifest.get("source_page_url")):
            errors.append("official source missing")
        hashes = {manifest.get(k) for k in ("sha256_checksum", "extracted_sha256_checksum", "mosaic_sha256_checksum")}
        hashes.update(t.get("extracted_sha256_checksum") for t in manifest.get("tiles", []))
        if not art.get("source_sha256") or art["source_sha256"] not in hashes:
            errors.append("source checksum not registered")
        if art.get("body") not in {"earth", "mars", "moon"} or art["body"] != aoi["planetary_body"] or art["body"] != manifest["planetary_body"]:
            errors.append("body mismatch")
        for field, limit in (("center_latitude", 90), ("center_longitude", 180)):
            v = art[field]
            if not isinstance(v, (int, float)) or not isfinite(v) or abs(v) > limit or abs(v - aoi[field]) > 1e-6:
                errors.append("invalid or inconsistent coordinates")
        if art["core_width_m"] != aoi["width_m"] or not 0 < aoi["width_m"] <= 10000:
            errors.append("invalid spatial support")
        if art["site_id"] != aoi["site_id"]:
            errors.append("site identity mismatch")
        if future_date(art.get("generated_at")) or future_date(manifest.get("access_date")):
            errors.append("future product or processing date")
        if art.get("primary_scale_m") != 60 or art.get("quantile_grid", {}).get("n") != 500:
            errors.append("incompatible analysis grid")
        for name, unit in (("slope", "degrees"), ("relative_elevation", "metres")):
            f = art["scales"]["60"]["features"][name]
            q = f["quantiles"]
            if f["units"] != unit or len(q) != 500 or any(not isfinite(v) for v in q) or any(a > b for a, b in zip(q, q[1:])):
                errors.append("invalid units or quantile distribution")
            config = json.loads((BACKEND_ROOT / "app/data/analogue.v1.json").read_text(encoding="utf-8"))
            if not config["minimum_feature_coverage"] <= f["coverage"] <= 1:
                errors.append("feature coverage below threshold")
    except (KeyError, ValueError, TypeError, OSError):
        errors.append("invalid or missing provenance metadata")
    return sorted(set(errors))


def calculation_inputs(site_ids: list[str]) -> dict:
    """Portable paths and content digests of the inputs read by the calculation."""
    paths = [BACKEND_ROOT / "app/data/analogue.v1.json", BACKEND_ROOT / "app/data/data_roles.json",
             GEO_DATA / "processed/evaluation/analogue-v1-calibration.json",
             GEO_DATA / "processed/evaluation/analogue-v1-discrimination.json",
             GEO_DATA / "processed/evaluation/analogue-v1-population.json"]
    for sid in site_ids:
        p = GEO_DATA / "processed/terrain-v5" / f"{sid}.terrain-v5.json"
        if p.exists():
            art = json.loads(p.read_text(encoding="utf-8"))
            paths.extend([p, GEO_DATA / "manifests" / f"{art['source_id']}.json", GEO_DATA / "aoi" / f"{art['aoi_id']}.geojson"])
    files = [{"path": p.relative_to(BACKEND_ROOT).as_posix(), "sha256_lf": canonical_text_sha256(p)} for p in paths]
    return {"schema_version": "calculation-inputs-v1", "checksum_encoding": "UTF-8 bytes with CRLF normalized to LF", "files": files}
