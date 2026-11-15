"""Opt-in live checks against the real data providers.

Ordinary test runs never touch the network: this whole module is skipped unless TERRALUNA_LIVE=1.
Every check is a read-only metadata request (STAC item JSON, a WMTS capabilities document, a CMR
collection search, one HTTP HEAD). No raster is downloaded and no credential is sent.

    TERRALUNA_LIVE=1 .venv-geo/Scripts/python.exe -m pytest -q tests/test_live_providers.py
"""

import json
import os
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pytest

from app.services.imagery_service import parse_gibs_capabilities

pytestmark = pytest.mark.skipif(os.environ.get("TERRALUNA_LIVE") != "1", reason="live provider checks are opt-in: set TERRALUNA_LIVE=1")

BACKEND = Path(__file__).resolve().parents[1]
SELECTIONS = sorted((BACKEND / "data" / "imagery").glob("earth-*.sentinel-selection.json"))
PROVIDERS = json.loads((BACKEND / "app" / "data" / "imagery.providers.json").read_text(encoding="utf-8"))
LOLA = json.loads((BACKEND / "data" / "manifests" / "moon-south-pole-shackleton-lola-ldem.json").read_text(encoding="utf-8"))
HEADERS = {"User-Agent": "TerraLuna-live-check/1.0"}


@pytest.fixture(scope="module")
def client():
    with httpx.Client(timeout=60, headers=HEADERS, follow_redirects=False) as session:
        yield session


@pytest.mark.parametrize("selection_path", SELECTIONS, ids=lambda p: p.name.split(".")[0])
def test_stored_sentinel_scene_matches_its_official_stac_record(client, selection_path):
    scene = json.loads(selection_path.read_text(encoding="utf-8"))["selected_scene"]
    url = scene["official_stac_record"]
    assert urlsplit(url).hostname == "planetarycomputer.microsoft.com"
    item = client.get(url).raise_for_status().json()
    assert item["id"] == scene["product_id"]
    assert item["collection"] == "sentinel-2-l2a"
    assert item["properties"]["datetime"][:19] == scene["acquisition_datetime"][:19]


def test_gibs_capabilities_still_list_the_viirs_layer(client):
    gibs = PROVIDERS["gibs"]
    xml = client.get(gibs["capabilities_url"]).raise_for_status().text
    layer = next((item for item in parse_gibs_capabilities(xml) if item["identifier"] == gibs["layer_identifier"]), None)
    assert layer is not None, f"{gibs['layer_identifier']} is no longer listed"
    time = layer["dimensions"].get("Time") or layer["dimensions"].get("time") or {}
    latest = date.fromisoformat(time["default"][:10])
    assert latest >= date.fromisoformat(gibs["observation_date"]), "stored observation date is newer than the provider's latest"


def test_srtmgl1_collection_is_published_in_cmr(client):
    response = client.get("https://cmr.earthdata.nasa.gov/search/collections.json", params={"short_name": "SRTMGL1", "version": "003"})
    entries = response.raise_for_status().json()["feed"]["entry"]
    assert entries, "SRTMGL1.003 is not listed in CMR"
    # LPCLOUD is the cloud-hosted LP DAAC provider that serves data.lpdaac.earthdatacloud.nasa.gov (used by srtm_service).
    assert any(entry.get("data_center") == "LPCLOUD" and entry.get("version_id") == "003" for entry in entries)


def test_lola_ldem_file_size_matches_the_manifest(client):
    url = LOLA["download_url"]
    assert urlsplit(url).hostname == "pds-geosciences.wustl.edu"
    response = client.head(url).raise_for_status()
    assert int(response.headers["content-length"]) == LOLA["file_size"]
