import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import httpx

from app.services.geospatial_service import GEO_DATA, load_aoi
from app.services.imagery_service import rank_sentinel_scenes, sentinel_search_plan


STAC_SEARCH = "https://stac.dataspace.copernicus.eu/v1/search"


def discover(site_id: str, aoi_id: str) -> dict:
    aoi = load_aoi(aoi_id)
    if aoi.site_id != site_id:
        raise ValueError("AOI does not belong to the requested site")
    attempts = []
    selected = None
    with httpx.Client(timeout=45) as client:
        for query in sentinel_search_plan(aoi.geometry):
            response = client.post(STAC_SEARCH, json=query)
            response.raise_for_status()
            features = response.json().get("features", [])
            attempts.append({"datetime": query["datetime"], "cloud_limit_pct": query["query"]["eo:cloud_cover"]["lte"], "result_count": len(features)})
            if features:
                selected = rank_sentinel_scenes(features)[0]
                break
    output = {
        "site_id": site_id, "aoi_id": aoi_id, "provider": "Copernicus Data Space Ecosystem / ESA",
        "collection": "sentinel-2-l2a", "discovered_at": datetime.now(timezone.utc).isoformat(),
        "selection_policy": "90 days <=10% cloud; 90 days <=15%; 365 days <=15%; rank cloud ascending, acquisition time descending, product ID ascending",
        "attempts": attempts, "retrieval_status": "metadata_selected_asset_not_retrieved" if selected else "no_acceptable_scene",
        "selected_scene": None,
    }
    if selected:
        properties = selected.get("properties", {})
        output["selected_scene"] = {
            "product_id": selected.get("id"), "acquisition_datetime": properties.get("datetime") or properties.get("start_datetime"),
            "cloud_cover_pct": properties.get("eo:cloud_cover"), "processing_level": "Sentinel-2 Level-2A",
            "asset_keys": [key for key in ("B02_10m", "B03_10m", "B04_10m", "TCI_10m", "thumbnail") if key in selected.get("assets", {})],
            "official_stac_record": next((link.get("href") for link in selected.get("links", []) if link.get("rel") == "self"), None),
        }
    destination = GEO_DATA / "imagery" / f"{site_id}.sentinel-selection.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(output, indent=2), encoding="utf-8", newline="\n")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover and record an exact-AOI Sentinel-2 scene without downloading protected assets")
    parser.add_argument("--site-id", required=True); parser.add_argument("--aoi-id", required=True)
    args = parser.parse_args()
    result = discover(args.site_id, args.aoi_id)
    print(json.dumps({"site_id": args.site_id, "retrieval_status": result["retrieval_status"], "selected_scene": result["selected_scene"]}, indent=2))


if __name__ == "__main__":
    main()
