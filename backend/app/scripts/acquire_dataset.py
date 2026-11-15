import argparse
import base64
from datetime import date
import os
from pathlib import Path
from urllib.parse import urljoin, urlsplit
import zipfile

import httpx

from app.config import settings
from app.services.geospatial_service import GEO_DATA, load_aoi, load_manifest, sha256_file, write_manifest
from app.services.srtm_service import mosaic_rasters, redact_secret, srtm_archive_name, srtm_download_url, tiles_for_geojson_geometry
from app.services.terrain_service import inspect_dem


class AcquisitionError(RuntimeError):
    pass


def earthdata_headers(environment: dict[str, str]) -> dict[str, str]:
    headers = {"User-Agent": f"{settings.application_id}/{settings.app_version}"}
    token = environment.get("EARTHDATA_TOKEN")
    username, password = environment.get("EARTHDATA_USERNAME"), environment.get("EARTHDATA_PASSWORD")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    elif username and password:
        headers["Authorization"] = "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()
    else:
        raise AcquisitionError("Earthdata credentials missing. Set EARTHDATA_TOKEN or EARTHDATA_USERNAME and EARTHDATA_PASSWORD.")
    return headers


MAX_DOWNLOAD_BYTES = 250_000_000
MAX_EXTRACTED_BYTES = 500_000_000
MAX_REDIRECTS = 10
# Credentials are only ever sent to NASA Earthdata hosts. Redirect targets (S3 / CloudFront signed URLs)
# receive no Authorization header, and any other host is refused.
CREDENTIAL_HOST_SUFFIXES = (".earthdata.nasa.gov", ".earthdatacloud.nasa.gov")
ALLOWED_HOST_SUFFIXES = CREDENTIAL_HOST_SUFFIXES + (".amazonaws.com", ".cloudfront.net", ".usgs.gov")


def _host_ok(host: str | None, suffixes: tuple[str, ...]) -> bool:
    return bool(host) and any(host == suffix.lstrip(".") or host.endswith(suffix) for suffix in suffixes)


def download(url: str, destination: Path, headers: dict[str, str]) -> None:
    secret = headers.get("Authorization")
    temporary = destination.with_suffix(destination.suffix + ".part")
    public_headers = {key: value for key, value in headers.items() if key.lower() != "authorization"}
    try:
        with httpx.Client(timeout=httpx.Timeout(30, read=120), follow_redirects=False) as client:
            current = url
            for _ in range(MAX_REDIRECTS + 1):
                host = urlsplit(current).hostname
                if urlsplit(current).scheme != "https" or not _host_ok(host, ALLOWED_HOST_SUFFIXES):
                    raise AcquisitionError(f"Refusing download host: {host}")
                send = headers if _host_ok(host, CREDENTIAL_HOST_SUFFIXES) else public_headers
                with client.stream("GET", current, headers=send) as response:
                    if response.is_redirect:
                        current = urljoin(current, response.headers["location"])
                        continue
                    response.raise_for_status()
                    total = 0
                    with temporary.open("wb") as output:
                        for chunk in response.iter_bytes(1024 * 1024):
                            total += len(chunk)
                            if total > MAX_DOWNLOAD_BYTES:
                                raise AcquisitionError(f"Download exceeds the {MAX_DOWNLOAD_BYTES} byte cap")
                            output.write(chunk)
                    temporary.replace(destination)
                    return
            raise AcquisitionError("Too many redirects")
    except (httpx.HTTPError, AcquisitionError) as error:
        if temporary.exists():
            temporary.unlink()
        safe = redact_secret(str(error), secret)
        raise AcquisitionError(f"Dataset download failed: {safe}") from None


def extract_dem(archive_path: Path, raw_dir: Path) -> Path:
    if not zipfile.is_zipfile(archive_path): return archive_path
    with zipfile.ZipFile(archive_path) as archive:
        candidates = [info for info in archive.infolist() if info.filename.lower().endswith((".hgt", ".tif", ".tiff"))]
        if len(candidates) != 1: raise AcquisitionError(f"Expected one DEM inside archive, found {len(candidates)}")
        if candidates[0].file_size > MAX_EXTRACTED_BYTES: raise AcquisitionError("Archived DEM exceeds the extraction size cap")
        extracted = Path(archive.extract(candidates[0], raw_dir)).resolve()
        if raw_dir.resolve() not in extracted.parents: raise AcquisitionError("Archive member escapes the raw data directory")
        return extracted


def main() -> None:
    parser = argparse.ArgumentParser(description=f"Acquire or register a {settings.product_name} source dataset")
    parser.add_argument("--source-id", required=True); parser.add_argument("--force", action="store_true")
    args = parser.parse_args(); manifest = load_manifest(args.source_id)
    raw_dir = GEO_DATA / "raw"; raw_dir.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": f"{settings.application_id}/{settings.app_version}"}
    if manifest.planetary_body == "earth": headers = earthdata_headers(dict(os.environ))
    if manifest.planetary_body == "earth" and manifest.aoi_id:
        tile_ids = tiles_for_geojson_geometry(load_aoi(manifest.aoi_id).geometry)
        prior = {tile.get("tile_id"): tile for tile in manifest.tiles}
        tile_entries = [
            {
                **prior.get(tile_id, {}),
                "tile_id": tile_id,
                "filename": srtm_archive_name(tile_id),
                "download_url": srtm_download_url(tile_id),
            }
            for tile_id in tile_ids
        ]
        manifest.tiles = tile_entries
        if len(tile_entries) == 1:
            manifest.download_url = tile_entries[0]["download_url"]
    else:
        tile_entries = manifest.tiles or [{"filename": manifest.filename, "download_url": manifest.download_url}]
    inspected_paths: list[Path] = []; total_size = 0
    for tile in tile_entries:
        if not tile.get("download_url"): raise AcquisitionError("Manifest tile has no download URL")
        archive_path = raw_dir / tile["filename"]
        if not archive_path.exists() or args.force: download(tile["download_url"], archive_path, headers)
        archive_checksum = sha256_file(archive_path); tile["sha256_checksum"] = archive_checksum
        tile["file_size"] = archive_path.stat().st_size; total_size += archive_path.stat().st_size
        extracted = extract_dem(archive_path, raw_dir); tile["extracted_filename"] = extracted.name
        tile["extracted_sha256_checksum"] = sha256_file(extracted); inspected_paths.append(extracted)
    inspect_path = inspected_paths[0]
    if len(inspected_paths) > 1:
        inspect_path = mosaic_rasters(inspected_paths, GEO_DATA / "interim" / f"{manifest.source_id}.mosaic.tif")
        manifest.mosaic_filename = inspect_path.name; manifest.mosaic_sha256_checksum = sha256_file(inspect_path)
    manifest.access_date = date.today().isoformat(); manifest.file_size = total_size
    if len(tile_entries) == 1:
        manifest.sha256_checksum = tile_entries[0]["sha256_checksum"]
        manifest.extracted_filename = tile_entries[0]["extracted_filename"]
        manifest.extracted_sha256_checksum = tile_entries[0]["extracted_sha256_checksum"]
    metadata = inspect_dem(inspect_path)
    manifest.native_crs = metadata["crs"]; manifest.native_bounds = metadata["bounds"]
    manifest.native_nodata = metadata["nodata"]; manifest.native_resolution = metadata["resolution"]
    manifest.processing_status = "inspected"; write_manifest(manifest)
    print(f"Registered {inspect_path}"); print(f"SHA-256: {manifest.mosaic_sha256_checksum or manifest.extracted_sha256_checksum or manifest.sha256_checksum}")


if __name__ == "__main__":
    try: main()
    except AcquisitionError as error: raise SystemExit(str(error))
