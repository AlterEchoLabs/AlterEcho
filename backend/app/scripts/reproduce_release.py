"""Recompute registered 60 m terrain from local rasters without replacing artifacts."""
import json
from pathlib import Path
from app.services.terrain_quantiles import measure, landcover_exclusion
from app.services.geospatial_service import BACKEND_ROOT, GEO_DATA


def main():
    out = []
    for path in sorted((GEO_DATA / "processed/terrain-v5").glob("*.json")):
        art = json.loads(path.read_text(encoding="utf-8"))
        mask = GEO_DATA / "processed/landcover" / f"{art['site_id']}.worldcover-v200.tif"
        measured = measure(BACKEND_ROOT / art["source_file"], art["body"], art["center_longitude"], art["center_latitude"],
                           scales=(60,), exclusion=landcover_exclusion(mask) if mask.exists() else None)
        differences = {f: max(abs(x-y) for x, y in zip(measured["60"]["features"][f]["quantiles"], art["scales"]["60"]["features"][f]["quantiles"]))
                       for f in ("slope", "relative_elevation")}
        out.append({"site_id": art["site_id"], "maximum_quantile_difference": differences,
                    "coverage": {f: v["coverage"] for f, v in measured["60"]["features"].items()}})
    (BACKEND_ROOT.parent / "docs/raster-reproduction.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8", newline="\n")
    assert all(max(r["maximum_quantile_difference"].values()) <= 0.0001 for r in out), "Raster reproduction changed"
    print(f"Reproduced {len(out)} source rasters; every scored quantile agrees within 0.0001 native units")


if __name__ == "__main__":
    main()
