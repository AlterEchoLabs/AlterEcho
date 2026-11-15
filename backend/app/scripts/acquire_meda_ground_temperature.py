"""Mars thermal evidence: Mars 2020 MEDA TIRS ground (skin) temperature inside the Jezero AOI.

What is measured
    ``GROUND_TEMP`` (Kelvin) from the MEDA Thermal InfraRed Sensor calibrated product
    (PDS4 bundle ``mars2020_meda``, collection ``data_calibrated_env``). TIRS retrieves ground
    skin temperature from a downward-looking thermal-infrared channel over a few square metres
    next to the rover.

Matching the Earth evidence
    Earth MODIS Aqua view times were measured at ~13:54-14:30 (day) and ~01:54-02:42 (night)
    local solar time, so Mars samples use the same local TRUE solar time windows
    (LTST 13:30-14:30 and 01:45-02:45). Sols are sampled roughly every 28 sols across the first
    Mars year of the mission (sol 10 to ~660) so that every season is represented, matching the
    full calendar year of Earth composites.

Spatial check
    Rover position per sol is taken from the public Mars 2020 waypoint file and must fall inside
    the registered 10 km ``mars-jezero-aoi-v1`` window; samples outside are rejected.

Quality filters (documented in the PDS label)
    ROVER_STILL == 1 and ROVER_LOW_TILT == 1; daytime samples additionally require
    TIRS_GROUND_FOOTPRINT_NOT_IN_SHADOW == 1; a WHEEL_OUTSIDE_TIRS_DOWNWARD_LOOKING_FOV value of 0
    rejects the sample. A window needs >= 300 accepted 1 Hz samples (5 minutes).

Season
    Solar longitude (Ls) is computed for each sampled sol from its UTC (Allison & McEwen 2000),
    anchored to the documented touchdown time. The PDS derived-ancillary column named
    SOLAR_LONGITUDE_ANGLE was inspected and is not the seasonal Ls, so it is not used.

Usage (from ``backend/``)::

    python -m app.scripts.acquire_meda_ground_temperature
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from hashlib import sha256
import io
import json
import math
import re
import time
from urllib.parse import urlsplit

import httpx
import numpy as np

from app.services.geospatial_service import GEO_DATA, load_aoi

BASE = "https://pds-atmospheres.nmsu.edu/PDS/data/PDS4/Mars2020/mars2020_meda/data_calibrated_env/"
WAYPOINTS = "https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_waypoints.json"
ALLOWED_HOSTS = {"pds-atmospheres.nmsu.edu", "mars.nasa.gov"}
RAW = GEO_DATA / "raw" / "meda"
OUTPUT = GEO_DATA / "processed" / "evidence" / "mars-jezero.thermal-v1.json"
MAX_FILE_BYTES = 60_000_000
SAMPLE_SOLS = list(range(10, 670, 28))
SOL_SEARCH_OFFSETS = (0, 1, 2, 3, -1, -2, 4, 5)
DAY_WINDOW = (13.5, 14.5)
NIGHT_WINDOW = (1.75, 2.75)
MIN_WINDOW_SAMPLES = 300
MARS_RADIUS_M = 3_396_190


# Mars 2020 touchdown: 2021-02-18 20:55 UTC at local mean solar time 15:53 on sol 0.
LANDING_UTC = datetime(2021, 2, 18, 20, 55, tzinfo=timezone.utc)
LANDING_LMST_H = 15 + 53 / 60
MARS_SOL_S = 88_775.244
PBS_TERMS = ((0.0071, 2.2353, 49.409), (0.0057, 2.7543, 168.173), (0.0039, 1.1177, 191.837), (0.0037, 15.7866, 21.736),
             (0.0021, 2.1354, 15.704), (0.0020, 2.4694, 95.528), (0.0018, 32.8493, 49.095))


def solar_longitude_deg(moment: datetime) -> float:
    """Areocentric solar longitude Ls (Allison & McEwen 2000, Planet. Space Sci. 48, 215-235)."""
    jd_tt = moment.timestamp() / 86400 + 2440587.5 + 69.184 / 86400
    dt = jd_tt - 2451545.0
    mean_anomaly = math.radians(19.3871 + 0.52402073 * dt)
    alpha_fms = 270.3871 + 0.524038496 * dt
    pbs = sum(a * math.cos(math.radians(0.985626 * dt / tau + phi)) for a, tau, phi in PBS_TERMS)
    nu_minus_m = ((10.691 + 3.0e-7 * dt) * math.sin(mean_anomaly) + 0.623 * math.sin(2 * mean_anomaly)
                  + 0.050 * math.sin(3 * mean_anomaly) + 0.005 * math.sin(4 * mean_anomaly) + 0.0005 * math.sin(5 * mean_anomaly) + pbs)
    return (alpha_fms + nu_minus_m) % 360


def sol_midday_utc(sol: int) -> datetime:
    """UTC of local mean noon on a mission sol (sol 0 starts LANDING_LMST_H before touchdown)."""
    from datetime import timedelta
    sol_zero_start = LANDING_UTC - timedelta(seconds=LANDING_LMST_H / 24 * MARS_SOL_S)
    return sol_zero_start + timedelta(seconds=(sol + 0.5) * MARS_SOL_S)


def _get(client: httpx.Client, url: str, attempts: int = 4, **kwargs) -> httpx.Response:
    if urlsplit(url).hostname not in ALLOWED_HOSTS:
        raise RuntimeError(f"Refusing unexpected host: {url}")
    for attempt in range(attempts):
        try:
            response = client.get(url, **kwargs)
            response.raise_for_status()
            return response
        except (httpx.TransportError, httpx.HTTPStatusError) as error:
            if isinstance(error, httpx.HTTPStatusError) and error.response.status_code < 500:
                raise
            if attempt == attempts - 1:
                raise
            time.sleep(2 * (attempt + 1))
    raise RuntimeError("unreachable")


def _hrefs(client: httpx.Client, url: str) -> list[str]:
    return re.findall(r'href="([^"?/][^"]*)"', _get(client, url).text)


def _range_folder(folders: list[str], sol: int) -> str | None:
    for folder in folders:
        match = re.fullmatch(r"sol_(\d{4})_(\d{4})/", folder)
        if match and int(match.group(1)) <= sol <= int(match.group(2)):
            return folder
    return None


def _ltst_hours(value: str) -> float | None:
    match = re.search(r"(\d{2}):(\d{2}):(\d{2})", value or "")
    return int(match.group(1)) + int(match.group(2)) / 60 + int(match.group(3)) / 3600 if match else None


def _flag(row: dict, name: str) -> str:
    return (row.get(name) or "").strip()


def _window_stats(rows: list[dict], window: tuple[float, float], daytime: bool) -> tuple[float | None, int, float | None]:
    values = []
    for row in rows:
        hours = _ltst_hours(row.get("LTST", ""))
        if hours is None or not (window[0] <= hours < window[1]):
            continue
        if _flag(row, "ROVER_STILL") != "1" or _flag(row, "ROVER_LOW_TILT") != "1":
            continue
        if _flag(row, "WHEEL_OUTSIDE_TIRS_DOWNWARD_LOOKING_FOV") == "0":
            continue
        if daytime and _flag(row, "TIRS_GROUND_FOOTPRINT_NOT_IN_SHADOW") != "1":
            continue
        try:
            temperature, uncertainty = float(row["GROUND_TEMP"]), float(row.get("GROUND_TEMP_UNCERTAINTY") or "nan")
        except (TypeError, ValueError):
            continue
        if math.isfinite(temperature) and 100 < temperature < 350:
            values.append((temperature, uncertainty))
    if len(values) < MIN_WINDOW_SAMPLES:
        return None, len(values), None
    temps = np.array([value[0] for value in values])
    uncertainties = np.array([value[1] for value in values if math.isfinite(value[1])])
    return round(float(np.median(temps)), 2), len(values), (round(float(np.median(uncertainties)), 2) if uncertainties.size else None)


def _rover_position(waypoints: list[dict], sol: int) -> dict | None:
    """Latest published waypoint at or before ``sol``.

    The waypoint file starts at sol 13 with the landing-site position (no drive had happened),
    so earlier sols take that first position.
    """
    known = [item for item in waypoints if item["sol"] is not None]
    prior = [item for item in known if item["sol"] <= sol]
    if prior:
        return max(prior, key=lambda item: item["sol"])
    return min(known, key=lambda item: item["sol"]) if known else None


def _inside_aoi(lon: float, lat: float, aoi) -> bool:
    dx = math.radians(lon - aoi.center_longitude) * MARS_RADIUS_M * math.cos(math.radians(aoi.center_latitude))
    dy = math.radians(lat - aoi.center_latitude) * MARS_RADIUS_M
    return abs(dx) <= aoi.width_m / 2 and abs(dy) <= aoi.height_m / 2


def acquire() -> dict:
    aoi = load_aoi("mars-jezero-aoi-v1")
    RAW.mkdir(parents=True, exist_ok=True)
    samples, inputs = [], []
    with httpx.Client(timeout=httpx.Timeout(60, read=180), follow_redirects=False) as client:
        waypoint_response = _get(client, WAYPOINTS)
        waypoint_sha = sha256(waypoint_response.content).hexdigest()
        waypoints = [{"sol": feature["properties"].get("sol"), "lon": feature["geometry"]["coordinates"][0],
                      "lat": feature["geometry"]["coordinates"][1]} for feature in waypoint_response.json()["features"]]
        folders = _hrefs(client, BASE)
        used_sols: set[int] = set()
        for target in SAMPLE_SOLS:
            record = {"target_sol": target, "status": "no_tirs_file"}
            for offset in SOL_SEARCH_OFFSETS:
                sol = target + offset
                if sol < 0 or sol in used_sols:
                    continue
                folder = _range_folder(folders, sol)
                if not folder:
                    continue
                sol_url = f"{BASE}{folder}sol_{sol:04d}/"
                try:
                    names = _hrefs(client, sol_url)
                except httpx.HTTPStatusError:
                    continue
                tirs = sorted(name for name in names if "CAL_TIRS" in name and name.endswith(".CSV"))
                if not tirs:
                    continue
                name = tirs[-1]
                path = RAW / name
                if not path.exists():
                    content = _get(client, sol_url + name).content
                    if len(content) > MAX_FILE_BYTES:
                        raise RuntimeError(f"{name} exceeds the size cap")
                    path.write_bytes(content)
                data = path.read_bytes()
                inputs.append({"file": name, "sol": sol, "bytes": len(data), "sha256": sha256(data).hexdigest(), "url": sol_url + name})
                solar_longitude = round(solar_longitude_deg(sol_midday_utc(sol)), 1)
                rows = list(csv.DictReader(io.StringIO(data.decode("utf-8", errors="replace"))))
                day, day_n, day_unc = _window_stats(rows, DAY_WINDOW, daytime=True)
                night, night_n, night_unc = _window_stats(rows, NIGHT_WINDOW, daytime=False)
                position = _rover_position(waypoints, sol)
                inside = bool(position and _inside_aoi(position["lon"], position["lat"], aoi))
                record = {"target_sol": target, "sol": sol, "file": name, "solar_longitude_deg": solar_longitude,
                          "rover_lon": position["lon"] if position else None, "rover_lat": position["lat"] if position else None,
                          "rover_inside_aoi": inside,
                          "day_ground_temp_k": day if inside else None, "day_samples": day_n, "day_uncertainty_k": day_unc,
                          "night_ground_temp_k": night if inside else None, "night_samples": night_n, "night_uncertainty_k": night_unc,
                          "status": "ok" if inside and (day is not None or night is not None) else ("outside_aoi" if not inside else "insufficient_window_samples")}
                used_sols.add(sol)
                if day is not None or night is not None:
                    break
            samples.append(record)
            print(target, record.get("sol"), record["status"], record.get("day_ground_temp_k"), record.get("night_ground_temp_k"), record.get("solar_longitude_deg"))

    day = [s["day_ground_temp_k"] for s in samples if s.get("day_ground_temp_k") is not None]
    night = [s["night_ground_temp_k"] for s in samples if s.get("night_ground_temp_k") is not None]
    paired = [s["day_ground_temp_k"] - s["night_ground_temp_k"] for s in samples if s.get("day_ground_temp_k") is not None and s.get("night_ground_temp_k") is not None]
    longitudes = sorted(s["solar_longitude_deg"] for s in samples if s.get("solar_longitude_deg") is not None and (s.get("day_ground_temp_k") is not None or s.get("night_ground_temp_k") is not None))
    pct = lambda values, q: round(float(np.percentile(values, q)), 2) if values else None  # noqa: E731
    summary = {
        "day_temperature_p50_k": pct(day, 50), "day_temperature_p95_k": pct(day, 95),
        "night_temperature_p50_k": pct(night, 50), "night_temperature_p05_k": pct(night, 5),
        "diurnal_range_p50_k": pct(paired, 50), "diurnal_range_p05_k": pct(paired, 5), "diurnal_range_p95_k": pct(paired, 95),
        "day_samples": len(day), "night_samples": len(night), "paired_samples": len(paired), "planned_samples": len(SAMPLE_SOLS),
        "day_local_solar_time_p50_h": sum(DAY_WINDOW) / 2, "night_local_solar_time_p50_h": sum(NIGHT_WINDOW) / 2,
        "solar_longitude_range_deg": [longitudes[0], longitudes[-1]] if longitudes else None,
    }
    artifact = {
        "evidence_version": "thermal-lst-v1",
        "site_id": "mars-jezero", "body": "mars", "dimension": "temperature",
        "quantity": "ground_skin_temperature",
        "status": "measured",
        "aoi_id": aoi.aoi_id,
        "product": {
            "product_id": "mars2020_meda:data_calibrated_env (CAL_TIRS)", "collection": "PDS4 bundle mars2020_meda",
            "platform": "Mars 2020 Perseverance rover", "instrument": "MEDA Thermal InfraRed Sensor (TIRS)",
            "provider": "NASA PDS Atmospheres Node", "source_url": BASE,
            "doi": None,
            "units": "K", "native_resolution_m": None,
            "analysis_resolution": "Point sensor: ground footprint of a few square metres beside the rover, sampled at 1 Hz",
            "observation_period": f"Mission sols {samples[0].get('sol')}–{samples[-1].get('sol')} (first Mars year, all seasons)",
            "temporal_sampling": f"About every 28 sols; window medians of >= {MIN_WINDOW_SAMPLES} accepted 1 Hz samples",
        },
        "local_time_policy": f"LTST {DAY_WINDOW[0]:g}-{DAY_WINDOW[1]:g} h and {NIGHT_WINDOW[0]:g}-{NIGHT_WINDOW[1]:g} h, matched to the measured MODIS Aqua view times.",
        "quality_policy": "ROVER_STILL=1, ROVER_LOW_TILT=1, wheel not in field of view; daytime footprint not in shadow; rover position inside the registered AOI.",
        "summary": summary,
        "samples": samples,
        "inputs": inputs,
        "rover_positions": {"source": WAYPOINTS, "sha256": waypoint_sha},
        "quality_flags": ["point_sensor_vs_aoi_mean", "rover_traverse_samples_several_terrain_units"],
        "limitations": [
            "Point measurement beside the rover, not an AOI-wide mean; the Earth values are AOI means of ~1 km pixels.",
            "Samples follow the rover traverse across crater-floor and delta-front units inside the AOI.",
            "Window medians, not daily extremes; dust-storm sols are included if they were sampled.",
            "Ground skin temperature, not air temperature.",
        ],
        "processing": {"script": "app/scripts/acquire_meda_ground_temperature.py", "generated_at": datetime.now(timezone.utc).isoformat()},
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(artifact, indent=2), encoding="utf-8", newline="\n")
    return artifact


def main() -> None:
    artifact = acquire()
    print(json.dumps(artifact["summary"], indent=2))


if __name__ == "__main__":
    main()
