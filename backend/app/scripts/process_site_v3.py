import argparse
import json

from app.services.terrain_v3_service import process_site_v3


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a versioned halo-correct terrain-v3 artifact without modifying terrain-v2")
    parser.add_argument("--site-id", required=True)
    parser.add_argument("--aoi-id", required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--input", required=True)
    args = parser.parse_args()
    result = process_site_v3(args.input, args.site_id, args.aoi_id, args.source_id)
    print(json.dumps({"site_id": result.site_id, "methodology_version": result.methodology_version,
                      "quality_status": result.quality_status, "scales": list(result.scales)}, indent=2))


if __name__ == "__main__":
    main()
