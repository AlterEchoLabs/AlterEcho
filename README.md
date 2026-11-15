# TerraLuna

Team AlterEcho · NASA Space Apps Challenge 2026 · *Identify Earth locations that analog the permanent Moon base locations and Mars*

Choose a reference site on Mars or the Moon, find comparable Earth terrain, and see what each mission question can and cannot conclude. Every result separates three things: **measured analogy** (a similarity index from comparable measurements), **field-test suitability** (a documented record, never scored) and **evidence quality** (statuses, coverage and sensitivity). There is no synthetic confidence number.

TerraLuna is a research-shortlisting tool. It is not a landing-site selector, a safety assessment or a NASA endorsement.

## What runs on real data today

| Site | Body | Coordinates (centre) | Terrain DEM | Imagery (display only) |
|---|---|---|---|---|
| Jezero Crater (reference) | Mars | 18.44° N, 77.45° E | USGS CTX DEM 20 m | USGS CTX orthomosaic 6 m |
| Gale Crater floor, Aeolis Palus (reference) | Mars | 4.5625° S, 137.4417° E | USGS controlled CTX DTM (20 m), lowest stereo error | CTX orthoimage from the same product |
| Elysium Planitia, InSight site (reference) | Mars | 4.5024° N, 135.6234° E | USGS controlled CTX DTM (20 m) | CTX orthoimage |
| Gusev crater plains, Spirit site (reference) | Mars | 14.5684° S, 175.4726° E | USGS controlled CTX DTM (20 m) | CTX orthoimage |
| Eberswalde crater delta (reference) | Mars | 23.85° S, 33.55° W | USGS controlled CTX DTM (20 m) | CTX orthoimage |
| Lunar south pole, Shackleton rim (reference, *distances only*) | Moon | 90° S | LRO LOLA LDEM_875S_20M | none processed (hillshade) |
| Atacama Desert (south window) | Earth | 24.27° S, 69.90° W | SRTMGL1.003 | Sentinel-2 L2A 2026-09-27 |
| Atacama Desert (original, excluded from v1.0: industrial complex) | Earth | 24.20° S, 69.90° W | SRTMGL1.003 | Sentinel-2 L2A 2026-09-27 |
| Upper Mustang | Earth | 29.10° N, 83.90° E | SRTMGL1.003 | Sentinel-2 L2A 2026-10-26 |
| Ladakh | Earth | 34.20° N, 77.60° E | SRTMGL1.003 | Sentinel-2 L2A 2025-11-26 |
| Dallol, Danakil Depression | Earth | 14.2417° N, 40.2989° E | SRTMGL1.003 | Sentinel-2 L2A 2025-12-03 |
| Craters of the Moon lava field | Earth | 43.42° N, 113.55° W | SRTMGL1.003 | Sentinel-2 L2A 2026-10-19 |
| Hanksville badlands (MDRS) | Earth | 38.4064° N, 110.7919° W | SRTMGL1.003 | Sentinel-2 L2A 2026-09-03 |
| Meteor Crater (Barringer) | Earth | 35.0272° N, 111.0225° W | SRTMGL1.003 | Sentinel-2 L2A 2026-11-12 |

Holuhraun (ArcticDEM) and the McMurdo Dry Valleys (REMA) are listed as planned and are never scored. Any other Earth area between 56° S and 60° N can be screened on the **Explore** page.

## How the index is calculated (analogue-method-v1.0)

A result is conditional on (Earth window E, reference window P, task T, epoch H, method V). It answers a narrow question: does window E resemble window P on the measured terrain at a 60 m grid? It does not say a site is "99 % like Mars" or safe for a base.

```
d_k  = W1(F_E,k, F_P,k) = ∫₀¹ |F_E,k⁻¹(u) − F_P,k⁻¹(u)| du     exact quantile functions of equal-area cells, in degrees or metres
s_k  = exp(−ln 2 · (d_k / τ_k)²)                                d = τ → 0.5, d = 2τ → 0.0625
S_g  = Σ a_k|g · s_k                                              every required feature must be eligible
index = 100 · Σ w_g I_g S_g / Σ w_g I_g,   coverage = Σ w_g I_g    no qualifying family → no index (never 0)
```

- **Features.** Slope and relative elevation are scored on a 60 m grid. Local relief and roughness are shown but not scored, because they measure the same construct as slope (Spearman ρ 0.985–0.998 across 88 unselected windows). The 120 m and 240 m grids are sensitivity checks.
- **Tolerance τ.** τ is the median W1 between unselected pairs of Earth land windows: slope 5.81°, relative elevation 77.1 m. It is accepted only if it is at least 3 times the resolution floor.
- **Resolution floor δ.** δ is what moving the Jezero window 2 km and switching DEM product (SRTM, NASADEM, GLO-30) produce on their own: slope 1.17°, relative elevation 22.2 m. A site within δ on every feature "cannot be told apart" from the reference.
- **Built-up mask.** ESA WorldCover cells that are at least half built-up are excluded.
- **Per-reference floor.** Each reference has its own resolution floor, from moving that window 2 km in four directions. The lunar window fails the 3× rule (relative elevation changes by 195 m against a 77 m tolerance), so lunar comparisons show distances without an index.
- **Background share.** Every candidate also reports the share of the 88 unselected Earth windows that score at least as high against the same reference.
- **Ranking.** Only *Terrain analogy* ranks. Tie groups come from overlapping scenario ranges: placement, reference placement, DEM, grid, τ and weights. Balanced science, Rover mobility and Mars-base field testing show partial evidence with their coverage (30 %, 80 %, 35 %) and are never ranked. Biosignature fieldwork is not assessed.

| Terrain analogy vs Jezero (v1.0) | Index | Scenario range | Rank |
|---|---|---|---|
| Craters of the Moon · Atacama south · Hanksville · Meteor Crater · Dallol | 98.2 · 97.9 · 97.4 · 95.1 · 88.6 | 77–99 overall | 1= (one tie group) |
| Upper Mustang · Ladakh | 0.6 · 0.0 | 0–4 | 6= |
| Atacama (original window) | excluded: contains an industrial complex | — | — |

Craters of the Moon and Atacama south are not resolved from Jezero by the floor tests (a 2 km reference move and a DEM-product swap).

**Discrimination.** Against every Mars reference, 42–49 % of unselected Earth windows score 90 or more, so the index separates low-relief from rugged terrain but does not order low-relief windows. That is why the background share is shown next to each index. Per-feature results, alternative tolerances and leave-one-region-out results (τ ranges from 3.7–9.4° for slope) are on the Method page and in `backend/data/processed/evaluation/analogue-v1-discrimination.json`.

**Why the old values clustered near 99.9.** Under terrain-v4.0 every low-relief window had d/τ between 0.016 and 0.15 on every family. Three correlated families were averaged, and the binned W1 read 10–20 % low. [docs/PHASE9_AUDIT.md](docs/PHASE9_AUDIT.md) shows the step-by-step decomposition and the full trace. The historical methods still reproduce: terrain-v4.0 and analog-evidence-v2.0 at `/api/v2/compare`, analog-evidence-v1.0 at `/api/evidence/compare`.

## Run on Windows

Prerequisites: Python 3.12 or 3.13, Node 20+, Git.

### Git Bash

```bash
# backend (terminal 1)
cd backend
python -m venv .venv-geo
.venv-geo/Scripts/python.exe -m pip install -r requirements-dev.txt
.venv-geo/Scripts/python.exe -m app.scripts.validate_catalog_integrity
.venv-geo/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# frontend (terminal 2)
cd frontend
cp .env.example .env.local
npm ci
npm run dev
```

Open <http://localhost:3000>. API docs are at <http://localhost:8000/docs> and are disabled when `APP_ENV=production`.

> **Do not use `--reload` on Windows.** Its worker process can start with the system Python instead of `.venv-geo`, so rasterio is missing and Explore jobs fail. Restart the server manually after code changes.

### PowerShell

```powershell
cd backend
py -3.13 -m venv .venv-geo
.venv-geo\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv-geo\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
# second terminal
cd frontend; Copy-Item .env.example .env.local; npm.cmd ci; npm.cmd run dev
```

The atlas serves small committed artifacts, so no raw raster or provider call is needed to browse. Explore jobs fetch SRTMGL1 tiles, which needs `EARTHDATA_TOKEN` (or `EARTHDATA_USERNAME`/`EARTHDATA_PASSWORD`) in `backend/.env`; the file is git-ignored. Without credentials, a job reports `requires_credentials` and fetches nothing.

## Tests

```bash
cd backend
.venv-geo/Scripts/python.exe -m app.scripts.validate_catalog_integrity
.venv-geo/Scripts/python.exe -m pytest -q                  # 255 passed, 11 skipped (opt-in live provider checks, TERRALUNA_LIVE=1); external services mocked
TERRALUNA_LIVE=1 .venv-geo/Scripts/python.exe -m pytest -q tests/test_live_providers.py   # opt-in: read-only metadata checks, no downloads, no credentials
.venv-geo/Scripts/python.exe -m pip_audit                   # dependency advisories

cd ../frontend
npm run lint && npx tsc --noEmit && npm run build
npx playwright install chromium                             # once
npm run test:e2e                                            # production build, 1327x660, 1680x1000, 390 px
```

## Reproduce the data (Git Bash, from `backend/`)

Final phase (references, discrimination, research paper):

```bash
.venv-geo/Scripts/python.exe -m app.scripts.register_mars_references    # Gale, InSight, Gusev, Eberswalde from USGS controlled CTX DTMs (STAC, windowed reads)
# then for each new reference: process_site and process_site_v3 on data/raw/mars/<id>-ctx-dtm-local.tif, and acquire_terrain_preview build/build_layers
.venv-geo/Scripts/python.exe -m app.scripts.analogue_v1_references      # reference quantiles + 2 km shifts, per-reference floors, background population, discrimination
.venv-geo/Scripts/python.exe -m app.scripts.build_methods_paper         # docs/paper/{paper-data.json, paper-content.json, methods.md, methods.tex}
cd ../docs/paper && npm install --prefix tools && node tools/build_docx.cjs && xelatex methods.tex   # methods.docx (native equations) and methods.pdf
```

Phase 9 (analogue-method-v1.0):

```bash
.venv-geo/Scripts/python.exe -m app.scripts.assess_aoi_landcover        # ESA WorldCover built-up share per Earth window
.venv-geo/Scripts/python.exe -m app.scripts.register_atacama_south      # uncontaminated Atacama window (rule fixed before measuring)
.venv-geo/Scripts/python.exe -m app.scripts.analogue_v1_calibration     # terrain-v5 quantiles, resolution floor, tau, redundancy, negatives
.venv-geo/Scripts/python.exe -m app.scripts.phase9_audit                # trace and v4 -> v1.0 decomposition tables
```

Earlier phases:

Every script verifies hosts, enforces size caps and timeouts, and writes LF-normalised JSON with checksums.

```bash
set -a; . ./.env; set +a          # loads EARTHDATA_TOKEN from the ignored backend/.env without printing it

# Study windows (run once; the windows are already committed)
.venv-geo/Scripts/python.exe -m app.scripts.register_phase7_sites       # Dallol, Craters of the Moon, Hanksville, Meteor Crater
.venv-geo/Scripts/python.exe -m app.scripts.register_lunar_reference    # LOLA LDEM_875S_20M, verified against its SHA-256
# then for each site: app.scripts.process_site and app.scripts.process_site_v3 (see backend/README.md)

# terrain-v4.0 calibration: placement, halo, NASADEM / GLO-30, base rate, redundancy, MOLA vs CTX
.venv-geo/Scripts/python.exe -m app.scripts.terrain_v4_evaluation

# Imagery (display only): Sentinel-2 warped onto each exact window; CTX with its registration correction
.venv-geo/Scripts/python.exe -m app.scripts.acquire_planetary_computer_imagery --site-id earth-meteor-crater --aoi-id earth-meteor-crater-aoi-v1
.venv-geo/Scripts/python.exe -m app.scripts.acquire_mars_imagery
.venv-geo/Scripts/python.exe -m app.scripts.refresh_gibs_date            # latest VIIRS date from WMTS capabilities

# Temperature context (public, no credentials)
.venv-geo/Scripts/python.exe -m app.scripts.acquire_modis_lst
.venv-geo/Scripts/python.exe -m app.scripts.acquire_meda_ground_temperature

# 3D grids and hillshade/slope layers from the SAME checksum-verified DEMs as the index
.venv-geo/Scripts/python.exe -m app.scripts.acquire_terrain_preview
```

## Research paper

`docs/paper/` holds the Methods and Results sections for the research paper: `methods.md` (Markdown with LaTeX), `methods.tex`, `methods.pdf` and `methods.docx` (native Word equations). They are generated from the running backend by `app.scripts.build_methods_paper`. The worked example (Atacama south against Jezero) is recomputed independently with the methodology handoff's reference arithmetic, and `tests/test_paper_numbers.py` fails if a documented number no longer matches the API.

## Sources and attribution

- Elevation: NASA SRTMGL1.003 (DOI 10.5067/MEaSUREs/SRTM/SRTMGL1.003). NASADEM_HGT.001 and Copernicus DEM GLO-30 via Microsoft Planetary Computer (sensitivity checks; GLO-30 © DLR e.V. 2010–2014 and © Airbus Defence and Space GmbH 2014–2018, provided under COPERNICUS by the European Union and ESA). USGS Mars 2020 CTX DEM mosaic. MGS MOLA 463 m global mosaic (USGS). LRO LOLA LDEM_875S_20M (NASA PDS Geosciences Node).
- Imagery: contains modified Copernicus Sentinel data (2025–2026), processed via Microsoft Planetary Computer. USGS CTX orthomosaic. NASA Worldview/GIBS VIIRS NOAA-20 (latest available, visual context only). Explore base map © OpenStreetMap contributors, served by OpenFreeMap.
- Temperature context: MODIS/Aqua MYD11A2.061 (DOI 10.5067/MODIS/MYD11A2.061). Mars 2020 MEDA calibrated environmental data (PDS Atmospheres Node).
- Field and research context: Sun & Stack (2020) USGS SIM 3464; Kring (2007) on Barringer/Meteor Crater; Mars Desert Research Station; Lim et al. (2019) on Craters of the Moon (BASALT). Each entry is cited on the Sources page.
- Additional Mars references: USGS Astrogeology controlled CTX DTMs and orthoimages (STAC `mro_ctx_controlled_usgs_dtms`, CC0, DOI 10.5066/P9JKVWR3). Context: Grotzinger et al. 2014 (Gale), Golombek et al. 2020 (InSight), Golombek et al. 2006 (Gusev), Malin & Edgett 2003 (Eberswalde).
- Land cover mask: ESA WorldCover 10 m v200 (2021), CC-BY-4.0.
- Globes (orientation only): NASA Blue Marble via GIBS; USGS Viking colour mosaic; NASA SVS CGI Moon Kit.

## Security

- Every path ID is a constrained slug. File access is gated by catalog or manifest allowlists, and job IDs must be 32-hex.
- Request models are bounded and finite (NaN and Infinity are rejected). Validation errors do not echo input, 500s are generic and request bodies are capped at 32 KB.
- Explore jobs run one worker with a queue of 4, 3 jobs per client per hour and 40 per day globally. Interrupted jobs are marked failed on restart.
- Credentials live only in environment variables. They never appear in responses, logs, exports or client bundles. SAS signatures are requested at acquisition time and never stored. Earthdata credentials are stripped on cross-host redirects.
- CSP is limited to the API origin, GIBS and OpenFreeMap.
- This review checked our own code and dependencies. It does not prove the absence of vulnerabilities. Put a reverse proxy with its own rate limiting in front of any public deployment.

## Known limitations

- **The index does not discriminate among low-relief windows.** About half of unselected Earth windows score 90 or more against each Mars reference, and the background sample covers only 4 regions. Read the background share, not the index alone.
- **Distributions ignore spatial arrangement.** A synthetic gentle fractal surface scores 88 against Jezero.
- **CTX stereo noise** inflates 60 m slopes on very smooth plains (InSight median 3.1°). The Gale window's south-east corner includes part of a dark-toned band.

- **Only terrain is scored.** Geology (EMIT, CRISM), water and ice, surface processes and subsurface evidence are not processed. Field-test suitability is a record, not a score. Balanced science, Rover mobility and Mars-base field testing are partial; Biosignature fieldwork is not assessed.
- **Terrain cannot separate low-relief sites.** Five windows form one tie group and two lie within the resolution floor of Jezero. Distributions ignore spatial arrangement: a synthetic gentle fractal surface scores 88.
- τ comes from Earth terrain contrast in 88 unselected windows, not from expert labels. The relative-elevation tolerance only narrowly passes the 3× resolution-floor rule. The candidates were known beforehand, so this is not a blind test. Profile weights await independent review.
- The lunar comparison uses a single 10 km window, with no placement or DEM checks and no illumination or thermal dimension.
- Copernicus GLO-30 was not measured for Meteor Crater because of a provider rate limit.
- The original Atacama window contains an industrial complex that WorldCover does not map, so it is excluded and replaced by a window 8 km south. Tracks and a survey grid remain in the new window. The Ladakh window is not the ISRO Tso Kar analog site. The Ladakh image is about 12 months old, and the legend says so.
- Explore results are *screening* records. They are not peer reviewed and not added to the atlas.
