# TerraLuna AI

TerraLuna AI is the current working name for Team AlterEcho's interplanetary terrain explorer. The name is intentionally centralized and may be changed later without renaming routes, repository folders, API identifiers, or dataset IDs.

The application compares equal-scale processed elevation-model windows using a transparent terrain-shape similarity index. It is a research-shortlisting tool, not a landing-site selector, safety assessment, scientific confidence model, or NASA endorsement.

## Current production data

| Site | Body | Data | AOI | Harmonized grid | Coverage | Status |
|---|---|---|---|---|---|---|
| Jezero Crater | Mars | USGS/PDS Mars 2020 CTX DEM mosaic | `mars-jezero-aoi-v1` | 60 m, 167 x 167 | 100% | Real processed, integrity checked |
| Atacama Desert | Earth | NASA SRTMGL1.003 | `earth-atacama-aoi-v1` | 60 m, 167 x 167 | 100% | Real processed, integrity checked |
| Upper Mustang | Earth | NASA SRTMGL1.003 | `earth-upper-mustang-aoi-v1` | 60 m, 167 x 167 | 100% | Real processed, integrity checked |
| Ladakh | Earth | NASA SRTMGL1.003 | `earth-ladakh-aoi-v1` | 60 m, 167 x 167 | 100% | Real processed, integrity checked |

Each requested AOI is 10,000 x 10,000 m. The deterministic 167-cell grid produces a recorded 10,020 x 10,020 m processed extent.

Current nominal `terrain-v3.0` Terrain Analogy Index ranking:

1. Atacama: **96.1/100** (tested configuration range 95.2–96.9)
2. Upper Mustang: **34.1/100** (tested configuration range 26.5–40.5)
3. Ladakh: **24.8/100** (tested configuration range 18.0–30.8)

The historical `terrain-v2.0` ranking (99.6, 12.0, 6.4) remains available by explicit API/UI selection and its artifacts were not overwritten. A v3 result compares fixed-bin terrain distributions at 60, 120, and 240 m after halo-safe derivative processing. Neither version is a probability, accuracy, confidence value, complete Mars-likeness measure, or NASA endorsement. The v3 distance scales and weights still require independent scientific review.

## Planned and metadata-only sites

- Holuhraun is planned for ArcticDEM or another documented high-latitude DEM.
- McMurdo/Taylor Valley is planned for REMA.
- Danakil is metadata-only and has no registered terrain AOI.

These sites remain visible for project context, but their comparison controls are disabled and they cannot receive a production score. Production runtime code does not load synthetic terrain fixtures. Test-only fixtures live under `backend/tests/fixtures/`.

## Status definitions

The application keeps three concepts separate:

- `data_status`: `real_processed`, `planned`, `metadata_only`, or `unavailable`.
- `processing_status`: `not_processed`, `processed`, or `integrity_checked`.
- `scientific_validation_status`: `not_reviewed`, `methodology_review_pending`, or `research_reviewed`.

The four real sites are `integrity_checked` and `methodology_review_pending`. Integrity checking verifies files, checksums, dimensions, coverage, and versions. It is not independent scientific validation.

## Terrain Analogy Index (`terrain-v3.0`)

`terrain-v3.0` processes a 1,200 m outer halo and crops derivatives back to the registered core AOI. It records feature-level sample counts and coverage for:

- elevation relative to the local median;
- slope from metric x/y spacing;
- local relief (maximum minus minimum over 1,000 m);
- roughness (local elevation standard deviation over 300 m).

Each feature uses fixed versioned histogram bins. The one-dimensional Wasserstein distance between normalized histograms is converted to similarity as:

```text
feature_similarity = exp(-wasserstein_distance / configured_distance_scale)
```

Feature components are combined at 60, 120, and 240 m using versioned feature and scale weights. Absolute Earth and Mars elevation datums are not compared. The API returns distribution distances, per-scale scores, feature coverage, leave-one-feature-out sensitivity, distance-scale perturbations, and rank stability. Tested ranges are configuration ranges—not statistical confidence intervals. `app/data/similarity.v3.json` is the authoritative formula configuration; `similarity.v2.json` remains unchanged for reproducibility.

## Repository layout

```text
frontend/                       Next.js, MapLibre, Three.js, Playwright
backend/app/                    FastAPI application and processing code
backend/app/data/               Production catalog and methodology configuration
backend/tests/fixtures/         Test-only synthetic inputs
backend/data/aoi/               Versioned study windows
backend/data/manifests/         Dataset provenance and checksums
backend/data/processed/         Terrain summaries and processing reports
backend/data/imagery/           Small scene-selection metadata records
backend/data/raw/               Ignored source rasters
backend/data/interim/           Ignored harmonized rasters
backend/data/cache/             Ignored downloads/cache
```

Raw and interim rasters are excluded from Git. The runtime API reads small processed JSON artifacts, so displaying results does not require the raw DEMs.

## Exact-AOI imagery

The overview globe is retained for exploration, while the scientific site card uses a 2D viewer fitted to the registered AOI.

| Mode | Current implementation | Status |
|---|---|---|
| Earth reference | Sentinel-2 L2A STAC search using the exact AOI and the documented 90-day/10%, 90-day/15%, 365-day/15% policy | Product metadata selected for all three Earth AOIs; protected band retrieval awaits CDSE credentials |
| Latest observation | `VIIRS_NOAA20_CorrectedReflectance_TrueColor` from the official NASA GIBS EPSG:3857 capabilities | Active standard-archive tiles for 2026-11-14; approximately 375 m context, potentially cloudy, not live |
| Terrain analysis | Derived visualization linked to the same terrain-v3 artifact used for numeric analysis | Active for all four processed sites |
| Jezero reference | Official USGS/PDS CTX orthomosaic `JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0` | 6 m source clipped to the exact AOI; source and preview checksums recorded |

Selected Sentinel metadata (the imagery assets themselves are not claimed as retrieved):

- Atacama: `S2B_MSIL2A_20261027T144729_N0513_R139_T19KDP_20261027T200046`, acquired 2026-10-27, catalog cloud cover 0.0%.
- Upper Mustang: `S2A_MSIL2A_20261112T050221_N0513_R119_T45RTN_20261112T100604`, acquired 2026-11-12, catalog cloud cover 0.0%.
- Ladakh: `S2C_MSIL2A_20261109T053031_N0513_R105_T43SGT_20261109T084002`, acquired 2026-11-09, catalog cloud cover 0.01%.

Cloud cover is scene-level catalog metadata, not a guarantee that the AOI is cloud-free. No stock or unrelated fallback image is used.

## Centralized branding

Frontend product strings are in `frontend/config/brand.ts`. Backend equivalents are in `backend/app/config.py` and can be overridden with environment variables shown in `backend/.env.example`. Change those settings when the final product name is selected; do not rename routes, IDs, or data directories.

## Run on Windows PowerShell

Backend:

```powershell
cd backend
uv python install 3.12
uv venv --python 3.12 .venv-geo
uv pip install --python .venv-geo\Scripts\python.exe -r requirements-terrain.txt
.venv-geo\Scripts\python.exe -m app.scripts.validate_catalog_integrity
.venv-geo\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

Frontend, in another terminal:

```powershell
cd frontend
Copy-Item .env.example .env.local -Force
npm.cmd ci
npm.cmd run dev
```

Open <http://localhost:3000>. API documentation is at <http://localhost:8000/docs>.

## Run from Git Bash on Windows

```bash
cd backend
uv python install 3.12
uv venv --python 3.12 .venv-geo
uv pip install --python .venv-geo/Scripts/python.exe -r requirements-terrain.txt
.venv-geo/Scripts/python.exe -m app.scripts.validate_catalog_integrity
.venv-geo/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000
```

In a second Git Bash terminal:

```bash
cd frontend
cp .env.example .env.local
npm ci
npm run dev
```

## Tests

PowerShell:

```powershell
cd backend
.venv-geo\Scripts\python.exe -m app.scripts.validate_catalog_integrity
.venv-geo\Scripts\python.exe -m pytest -q

cd ..\frontend
npm.cmd run lint
npm.cmd exec tsc -- --noEmit
npm.cmd run build
npm.cmd run test:e2e
```

Git Bash:

```bash
cd backend
.venv-geo/Scripts/python.exe -m app.scripts.validate_catalog_integrity
.venv-geo/Scripts/python.exe -m pytest -q
cd ../frontend
npm run lint
npx tsc --noEmit
npm run build
npm run test:e2e
```

Playwright starts the exact workspace on frontend port 3100 and backend port 8100 with build identifier `phase4-e2e`. It never reuses ports 3000/8000 and shuts down both children after the suite.

## Reproduce DEM processing

Set Earthdata credentials only in the current local environment. Never commit them.

```powershell
cd backend
$env:EARTHDATA_TOKEN = "YOUR_LOCAL_TOKEN"
.venv-geo\Scripts\python.exe -m app.scripts.acquire_dataset --source-id earth-atacama-srtmgl1
.venv-geo\Scripts\python.exe -m app.scripts.process_site --site-id earth-atacama --aoi-id earth-atacama-aoi-v1 --source-id earth-atacama-srtmgl1 --input data\raw\S25W070.hgt --target-resolution-m 60
.venv-geo\Scripts\python.exe -m app.scripts.validate_comparison --reference mars-jezero --candidate earth-atacama
```

Equivalent source/AOI pairs are documented in `backend/data/manifests/` and `backend/data/aoi/`. Processing writes a new report and summary only after its current quality gates pass.

### Reproduce Phase 5 artifacts

The v3 command reads the registered raw source, verifies its checksum, reprojects an outer halo, computes 60/120/240 m derivatives, crops to the core AOI, and writes a separate `*.terrain-v3.json` artifact. It never overwrites `*.terrain.json` v2 artifacts.

```powershell
cd backend
.venv-geo\Scripts\python.exe -m app.scripts.process_site_v3 --site-id mars-jezero --aoi-id mars-jezero-aoi-v1 --source-id mars-jezero-ctx-dem --input data\raw\M20_JezeroCrater_CTXDEM_20m.tif
.venv-geo\Scripts\python.exe -m app.scripts.process_site_v3 --site-id earth-atacama --aoi-id earth-atacama-aoi-v1 --source-id earth-atacama-srtmgl1 --input data\raw\S25W070.hgt
.venv-geo\Scripts\python.exe -m app.scripts.process_site_v3 --site-id earth-upper-mustang --aoi-id earth-upper-mustang-aoi-v1 --source-id earth-upper-mustang-srtmgl1 --input data\raw\N29E083.hgt
.venv-geo\Scripts\python.exe -m app.scripts.process_site_v3 --site-id earth-ladakh --aoi-id earth-ladakh-aoi-v1 --source-id earth-ladakh-srtmgl1 --input data\raw\N34E077.hgt

# Public STAC metadata discovery; no protected asset is claimed as downloaded.
.venv-geo\Scripts\python.exe -m app.scripts.discover_sentinel_imagery --site-id earth-atacama --aoi-id earth-atacama-aoi-v1
.venv-geo\Scripts\python.exe -m app.scripts.discover_sentinel_imagery --site-id earth-upper-mustang --aoi-id earth-upper-mustang-aoi-v1
.venv-geo\Scripts\python.exe -m app.scripts.discover_sentinel_imagery --site-id earth-ladakh --aoi-id earth-ladakh-aoi-v1

# Downloads the confirmed 35 MB official CTX ortho to ignored cache and creates a checksummed AOI preview.
.venv-geo\Scripts\python.exe -m app.scripts.acquire_mars_imagery
.venv-geo\Scripts\python.exe -m app.scripts.validate_catalog_integrity
```

For authenticated Sentinel band retrieval, set `CDSE_CLIENT_ID` and `CDSE_CLIENT_SECRET` only in the backend process. For NASADEM cross-validation set `EARTHDATA_TOKEN` (or the username/password pair). The current code never returns or logs these secrets. Public metadata discovery works without them; protected imagery and NASADEM cross-validation remain pending until credentials are supplied.

## API summary

- `GET /api/health` — service/build identity and real/planned counts.
- `GET /api/config` — centralized identity, features, methodology, and counts.
- `GET /api/sites` and `GET /api/sites/{id}` — production catalog.
- `GET /api/sites/{id}/aoi` — registered AOI metadata.
- `GET /api/sites/{id}/terrain` — integrity-checked real summary only.
- `GET /api/sources` and `GET /api/sources/{id}` — source manifests.
- `GET /api/processing-runs/{id}` — processing provenance.
- `GET /api/methodology` — formulas, statuses, interpretation, and limitations.
- `GET /api/datasets` — safe centralized scientific dataset registry.
- `GET /api/sites/{id}/imagery`, `/imagery/latest`, and `/imagery/{imagery_id}` — imagery modes and source metadata.
- `GET /api/sites/{id}/terrain/quality` — terrain-v3 feature coverage, unit, halo, and quality evidence.
- `GET /api/sites/{id}/terrain/distributions` — fixed-bin distributions at every analysis scale.
- `GET /api/sites/{id}/terrain/sensitivity` — deterministic tested-configuration range and influential metrics.
- `POST /api/discover` — defaults to `terrain-v3.0`; pass `methodology_version: "terrain-v2.0"` for the preserved historical result.

Deprecated Phase 3 response aliases remain temporarily for frontend compatibility: `rankable_real_candidates`, `demo_fixture_sites`, and `preview_results`. Their replacements are documented by `/api/config`; `preview_results` is always empty in production.

## Current limitations

- Terrain only: no atmosphere, gravity, radiation, geology, climate, water, habitability, accessibility, or operational safety scoring.
- V3 distribution bins, distance scales, and weights are transparent but not independently calibrated.
- NASADEM Earth cross-validation is pending Earthdata credentials; MOLA regional Mars cross-validation is pending source acquisition.
- Sentinel product metadata is real and traceable, but protected 10 m band assets have not been retrieved; the UI therefore shows an honest authentication-required state instead of imagery.
- GIBS is recent observational context and may contain clouds. It is not live and is too coarse for scoring.
- AOI rationales now record representativeness and selection bias, but independent geomorphology review is still pending.
- Terrain-v3 quality checking is computational integrity evidence, not independent scientific review.
- Moon processing is not implemented.

## Phase 6 roadmap

The best next scientific task is independent source cross-validation before adding more score dimensions:

- retrieve NASADEM for all three Earth AOIs and quantify metric/distribution differences from SRTM;
- retrieve MOLA regional context and state explicitly which scales it can and cannot validate;
- retrieve and checksum B04/B03/B02 Sentinel-2 assets, crop exact AOIs, and validate AOI-level cloud coverage;
- conduct an expert review of AOI centers, v3 histogram bins, distance scales, feature weights, and rank stability;
- publish a signed reproducibility manifest for every v3 and imagery artifact;
- only then consider a versioned multidimensional method. Do not silently alter terrain-v3.0.
