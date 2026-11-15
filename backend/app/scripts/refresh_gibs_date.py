"""Set the GIBS 'latest available observation' date from the official WMTS capabilities.

The date is read from the layer's time dimension (default value), never assumed to be today.
Usage (from backend/): python -m app.scripts.refresh_gibs_date
"""

import json
from pathlib import Path

import httpx

from app.services.imagery_service import parse_gibs_capabilities

PROVIDERS = Path(__file__).resolve().parents[1] / "data" / "imagery.providers.json"


def main() -> None:
    config = json.loads(PROVIDERS.read_text(encoding="utf-8"))
    gibs = config["gibs"]
    with httpx.Client(timeout=120, follow_redirects=False) as client:
        xml = client.get(gibs["capabilities_url"]).raise_for_status().text
    layer = next((item for item in parse_gibs_capabilities(xml) if item["identifier"] == gibs["layer_identifier"]), None)
    if not layer:
        raise SystemExit(f"{gibs['layer_identifier']} is not listed in the capabilities")
    time = layer["dimensions"].get("Time") or layer["dimensions"].get("time") or {}
    latest = time.get("default")
    if not latest:
        raise SystemExit("Capabilities give no default time for the layer")
    gibs["observation_date"] = latest[:10]
    gibs["tile_template"] = gibs["tile_template"].rsplit("/default/", 1)[0] + f"/default/{latest[:10]}/{gibs['tile_matrix_set']}/{{z}}/{{y}}/{{x}}.jpeg"
    from datetime import datetime, timezone
    gibs["verified_at"] = datetime.now(timezone.utc).isoformat()
    PROVIDERS.write_text(json.dumps(config, indent=2), encoding="utf-8", newline="\n")
    print(gibs["layer_identifier"], "latest available:", gibs["observation_date"])


if __name__ == "__main__":
    main()
