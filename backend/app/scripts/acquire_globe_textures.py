"""Download and downsample observation-derived global textures for the orientation globes.

These textures are ORIENTATION LAYERS only. They are global mosaics, not live imagery and
not site-level observations, and they are never used for scoring.

Sources (all U.S. Government works / public domain; attribution retained in the manifest):
- Earth: NASA "Blue Marble: Next Generation" with shaded relief + bathymetry, via the NASA GIBS WMS
         (the Visible Earth host eoimages.gsfc.nasa.gov was unreachable from the build network).
- Mars:  USGS Astrogeology Viking MDIM colour mosaic, global, 925 m/px.
- Moon:  NASA SVS "CGI Moon Kit" LRO LROC WAC colour mosaic (SVS 4720).

Usage (from ``backend/``)::

    python -m app.scripts.acquire_globe_textures
"""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from app.services.geospatial_service import BACKEND_ROOT, GEO_DATA

FRONTEND_TEXTURES = BACKEND_ROOT.parent / "frontend" / "public" / "textures"
CACHE = GEO_DATA / "cache" / "textures"
OUTPUT_WIDTH = 4096
ALLOWED_HOSTS = {"gibs.earthdata.nasa.gov", "planetarymaps.usgs.gov", "asc-pds-services.s3.us-west-2.amazonaws.com", "svs.gsfc.nasa.gov"}

TEXTURES = [
    {
        "body": "earth",
        "output": "earth-blue-marble-4k.jpg",
        "url": "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi?SERVICE=WMS&REQUEST=GetMap&VERSION=1.3.0&LAYERS=BlueMarble_ShadedRelief_Bathymetry&STYLES=&CRS=EPSG:4326&BBOX=-90,-180,90,180&WIDTH=4096&HEIGHT=2048&FORMAT=image/jpeg",
        "cache_name": "BlueMarble_ShadedRelief_Bathymetry_4096.jpg",
        "max_bytes": 20_000_000,
        "title": "Blue Marble: Next Generation with shaded relief and bathymetry (GIBS layer BlueMarble_ShadedRelief_Bathymetry)",
        "provider": "NASA Earth Observatory Blue Marble, served by NASA GIBS",
        "landing_page": "https://science.nasa.gov/earth/earth-observatory/the-blue-marble-true-color-global-imagery-at-1km-resolution/",
        "attribution": "NASA Earth Observatory Blue Marble: Next Generation, via NASA GIBS",
        "terms": "NASA imagery is generally not subject to copyright in the U.S.; credit NASA. No NASA endorsement implied.",
    },
    {
        "body": "mars",
        "output": "mars-viking-mdim-4k.jpg",
        "url": "https://planetarymaps.usgs.gov/mosaic/Mars_Viking_ClrMosaic_global_925m.tif",
        "max_bytes": 900_000_000,
        "title": "Mars Viking Colorized Global Mosaic 925 m",
        "provider": "USGS Astrogeology Science Center / NASA",
        "landing_page": "https://astrogeology.usgs.gov/search/map/mars_viking_global_color_mosaic_925m",
        "attribution": "USGS Astrogeology / NASA Viking — colour mosaic",
        "terms": "USGS-authored data are public domain; cite USGS Astrogeology.",
    },
    {
        "body": "moon",
        "output": "moon-lroc-wac-2k.jpg",
        "url": "https://svs.gsfc.nasa.gov/vis/a000000/a004700/a004720/lroc_color_2k.jpg",
        "max_bytes": 20_000_000,
        "title": "CGI Moon Kit — LRO LROC WAC colour map (2k)",
        "provider": "NASA Scientific Visualization Studio (Ernie Wright) / LRO LROC team",
        "landing_page": "https://svs.gsfc.nasa.gov/4720/",
        "attribution": "NASA SVS CGI Moon Kit — LRO LROC WAC",
        "terms": "NASA SVS media are generally free to use with NASA credit.",
    },
]


def _download(url: str, destination: Path, max_bytes: int) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        return sha256(destination.read_bytes()).hexdigest()
    digest, total = sha256(), 0
    partial = destination.with_suffix(destination.suffix + ".part")
    with httpx.Client(timeout=httpx.Timeout(60, read=120), follow_redirects=True) as client:
        with client.stream("GET", url) as response:
            host = urlsplit(str(response.url)).hostname
            if host not in ALLOWED_HOSTS:
                raise RuntimeError(f"Unexpected host after redirects: {host}")
            response.raise_for_status()
            with partial.open("wb") as stream:
                for chunk in response.iter_bytes(1024 * 1024):
                    total += len(chunk)
                    if total > max_bytes:
                        raise RuntimeError(f"{url} exceeds the {max_bytes} byte cap")
                    digest.update(chunk)
                    stream.write(chunk)
    partial.replace(destination)
    return digest.hexdigest()


def _resample_to_jpeg(source: Path, output: Path) -> tuple[int, int]:
    from PIL import Image

    Image.MAX_IMAGE_PIXELS = 400_000_000
    if source.suffix.lower() == ".tif":
        import numpy as np
        import rasterio
        from rasterio.enums import Resampling

        with rasterio.open(source) as dataset:
            height = round(OUTPUT_WIDTH * dataset.height / dataset.width)
            data = dataset.read([1, 2, 3], out_shape=(3, height, OUTPUT_WIDTH), resampling=Resampling.average)
        image = Image.fromarray(np.moveaxis(data, 0, -1).astype("uint8"), "RGB")
    else:
        image = Image.open(source).convert("RGB")
        if image.width > OUTPUT_WIDTH:
            image = image.resize((OUTPUT_WIDTH, round(OUTPUT_WIDTH * image.height / image.width)), Image.LANCZOS)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, "JPEG", quality=86, optimize=True, progressive=True)
    return image.width, image.height


def main() -> None:
    records = []
    for texture in TEXTURES:
        source = CACHE / (texture.get("cache_name") or Path(urlsplit(texture["url"]).path).name)
        source_sha = _download(texture["url"], source, texture["max_bytes"])
        output = FRONTEND_TEXTURES / texture["output"]
        width, height = _resample_to_jpeg(source, output)
        records.append({
            "body": texture["body"],
            "file": f"/textures/{texture['output']}",
            "width": width,
            "height": height,
            "projection": "equirectangular (simple cylindrical), 0° longitude at image centre",
            "title": texture["title"],
            "provider": texture["provider"],
            "source_url": texture["url"],
            "landing_page": texture["landing_page"],
            "attribution": texture["attribution"],
            "terms": texture["terms"],
            "source_sha256": source_sha,
            "output_sha256": sha256(output.read_bytes()).hexdigest(),
            "use": "orientation layer only — global mosaic, not live imagery, not a site observation, never scored",
        })
        print(f"{texture['body']}: {width}x{height} -> {output.name}")
    manifest = {"generated_at": datetime.now(timezone.utc).isoformat(), "textures": records}
    (FRONTEND_TEXTURES / "textures.manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
