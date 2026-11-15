# Phase 7/8 audit and method record

Branch `feature/terraluna-phase-6`, checkpoint tag `phase6-checkpoint` (commit 77d8bdd) taken before any scientific calculation changed. Every number below was reproduced from the stored artifacts on 2026-11-14. None was typed in by hand.

## 1. Baseline inventory (before Phase 7 → after)

| Item | Phase 6 baseline | After Phase 7/8 | Status |
|---|---|---|---|
| Earth AOIs with processed terrain | 3 (Atacama, Upper Mustang, Ladakh) | 7 (+ Dallol/Danakil, Craters of the Moon, Hanksville MDRS, Meteor Crater) | done |
| Planetary references | Jezero (CTX DEM 20 m) | Jezero + lunar south pole (LOLA LDEM_875S_20M) | done, lunar marked *limited* |
| Earth DEM | SRTMGL1.003 | SRTMGL1.003 scored; NASADEM and Copernicus GLO-30 as sensitivity checks | done (GLO-30 not measured for Meteor Crater: provider rate limit) |
| Mars DEM cross-check | none | MOLA 463 m vs CTX at 480 m over 30 km | done (regional only) |
| Sentinel-2 crops | 3, two of them stretched | 7, exact AOI grid, AOI cloud/snow from SCL | done |
| Temperature | scored (v1) | audited → context only (v2) | done |
| Terrain methods | terrain-v3.0 | terrain-v3.0 (preserved) + terrain-v4.0 | done |
| Evidence models | analog-evidence-v1.0 | v1.0 (preserved, same endpoints) + analog-evidence-v2.0 | done |
| Profiles | 4 | 5 (adds *Terrain analogy*, the only fully ranked one today) | done |
| Endpoints | `/api/...` v1 | + `/api/v2/{model,profiles,compare,evaluation,thermal-audit,method/worked-example,reports}`, `/api/explore/{preflight,jobs}`, `/api/sites/{id}/terrain/layers` | done |
| Views | atlas, method, sources | + overview map, Elevation mode (hillshade/slope), Moon reference, report page, Explore page | done |
| Backend tests | 155 | 198 | passing |
| Browser tests | 24 (v1 UI) | rewritten for the v2 UI, 3 viewports | see §9 |

## 2. Screenshot claims checked

| Claim (Phase 6 UI) | Finding | Fix |
|---|---|---|
| “51.5/100” and “70% backed” (Mars-base field testing, Atacama) | Reproduces exactly under v1 (`/api/evidence/compare`). But 35 of those 70 points were surface temperature, which fails the new comparability audit (§5). | v2 drops temperature from every index. Mars-base field testing is now *experimental partial*: terrain only, 35% coverage, not ranked. v1 stays reproducible. |
| Profile ranked with only 50% of the weight backed (Balanced science) | v1 allowed ranking at 50% coverage. | v2 ranks only when every task-critical dimension is measured and comparable. Balanced science is now *experimental partial* (30% coverage) and listed without ranks. |
| “100% AOI covered” on Sentinel imagery | False for Upper Mustang and Meteor Crater. The crop was a clipped read of a partial tile overlap, stretched to fill the image. The old Mustang scene (T45RTN, 2026-11-12) covered only part of the window. | Every crop is now warped (WarpedVRT) onto the AOI’s own UTM 10 m grid. Footprint coverage is measured from valid pixels, scenes below 99% are rejected, and a new scene was selected for Mustang (T44RQT, 2026-10-26) and for Meteor Crater. The label says *footprint coverage (not clear sky)*. |
| Scene-wide cloud percentage shown as if it described the AOI | `eo:cloud_cover` describes the ~110 km tile. | AOI cloud and snow fractions are computed from the SCL band over the exact window (cloud = classes 3/8/9/10, snow = 11, invalid = 0/1). Gates: AOI cloud ≤ 5%, snow ≤ 10%. Both values are shown, with their meaning. |
| Dated Ladakh imagery | The scene is 2025-11-26, about 12 months old. That is inside the 365-day search window but was not flagged. | Re-validated under the new rules (AOI cloud 0.0%, snow 4.1%). The legend now prints the age next to the date. |
| Jezero CTX reference | The orthomosaic is equirectangular with latitude of true scale 0°. The DEM uses 18.4663°. The crop was ~5% too narrow east–west (factor 1/cos 18.44° = 1.0541). | Corrected in `acquire_mars_imagery.py`. The registration record stores the factor and the 10 × 10 km ground extent, and a test checks it. |
| Earth skin temperature vs MEDA ground temperature | MODIS MYD11A2 (1 km pixels, AOI mean, 8-day composite) and MEDA TIRS (a few m² beside the rover, per-sol windows) fail spatial support and sampling equivalence. | Temperature is *measured · context only*. It is shown with its audit and never scored (§5). |
| Sensitivity ranges and ranking claims | v1 reported weight-perturbation ranges only. | v2 reports method perturbations (20 configurations), AOI placement (2 km N/S/E/W), alternative DEMs, the no-halo variant and a base rate. Ties are declared from these ranges (§4). |
| Research-context claims (Atacama, Ladakh) | The Phase 6 text implied site-specific analog studies. The Ladakh window is not the ISRO Tso Kar site, and the Atacama window contains infrastructure. | Each research-context entry is marked *about this window* or *region level, not this window*, with its source. None is scored. |

## 3. terrain-v4.0

```
C(f,s)  = 100 · exp(−0.5 · (W1(f,s) / τ_f)²)          per family f and scale s
W1      = Σ_bins |CDF_earth − CDF_planet| · bin width   (identical fixed bins, family units)
C(f)    = Σ_s w_s · C(f,s)                              w_60 = 0.5, w_120 = 0.3, w_240 = 0.2
C_terr  = Σ_f w_f · C(f)                                w_f = 0.25 each
```

The exact Gaussian is S = 100·exp[−0.5((x_E − x_P)/τ)²]. It gives 100 at zero difference, 60.65 at one τ and 13.53 at two τ (tested). Missing values, τ ≤ 0, non-finite inputs and unit mismatches return **no score**, never zero. Distributions are compared with W1, so the difference term is a distance between whole distributions in the family's own units (degrees or metres).

| Family | Distribution | Units | τ | Weight |
|---|---|---|---|---|
| Slope | slope_deg | degrees | 8.0 | 0.25 |
| Local relief (1 km window) | local_relief_m | metres | 200 | 0.25 |
| Roughness (300 m std) | roughness_m | metres | 30 | 0.25 |
| Relative elevation (z − median) | elevation_relative_m | metres | 150 | 0.25 |

- **τ provenance.** Each τ is the terrain-v3.0 distance scale, unchanged. These were set in Phase 5 after the three original sites were seen. They were frozen on 2026-11-14, before the four held-out sites were processed (`frozen_before_sites` in `similarity.v4.json`).
- **No arbitrary thresholds.** Ranks come from the index. Ties come from measured sensitivity ranges, not from a fixed point gap.
- **Redundancy.** Only one distribution per family is scored. Percentiles are shown for interpretation only. Spearman correlation of the family W1 values over 97 windows: slope–roughness 0.994, local relief–roughness 0.987, slope–local relief 0.974, relative elevation–others 0.77–0.81. So three families carry largely the same signal. A redundancy-adjusted weighting (1/6, 1/6, 1/6, 1/2) is included in the sensitivity set. It does not change any rank outside a tie group.
- **v3 preserved.** Atacama 96.1, Upper Mustang 34.1, Ladakh 24.8 (tested).

## 4. analog-evidence-v2.0

- **Partial index** = Σ_{d∈A} w_d·C_d / Σ_{d∈A} w_d over the set A of dimensions that are *measured_comparable*. **Coverage** = Σ_{d∈A} w_d. Both are always shown together.
- **Statuses (7):** measured_comparable, measured_context_only, source_available_unprocessed, missing_earth, missing_planetary, incompatible, review_pending. Only the first enters an index. Nothing missing becomes zero.
- **Profile states:** *ranked* (all task-critical dimensions comparable), *experimental partial* (some evidence, listed without ranks), *not assessed* (no task-critical evidence, no index shown).
- **Ranking eligibility:** two sites are co-ranked only if their eligibility keys match: same reference AOI, terrain method, included dimensions, scales, units and quality gate. Unmeasured sites never block or join a ranking.
- **Tie groups:** sites whose ranges overlap after method perturbation, AOI placement and DEM substitution. Competition ranking applies, so members share a rank shown as “1=”.

| Profile | State today | Included | Coverage |
|---|---|---|---|
| Terrain analogy (default) | ranked | terrain | 100% |
| Balanced science | experimental partial | terrain | 30% |
| Rover mobility | experimental partial (needs field-test suitability) | terrain | 80% |
| Mars-base field testing | experimental partial | terrain | 35% |
| Biosignature fieldwork | not assessed | — | — |

**Terrain analogy vs Jezero (terrain-v4.0):**

| Rank | Site | Index | Method range (20 configs) | AOI moved 2 km | NASADEM | GLO-30 | No halo |
|---|---|---|---|---|---|---|---|
| 1= | Atacama Desert | 99.92 | 99.90–99.93 | 99.67–99.94 | 99.92 | 99.94 | 99.92 |
| 1= | Craters of the Moon | 99.79 | 99.72–99.83 | 99.48–99.80 | 99.79 | 99.77 | 99.80 |
| 1= | Hanksville (MDRS) | 99.70 | 99.61–99.79 | 99.57–99.85 | 99.70 | 99.69 | 99.71 |
| 1= | Meteor Crater | 99.48 | 99.31–99.57 | 99.33–99.64 | 99.48 | not measured | 99.48 |
| 5 | Dallol, Danakil | 98.68 | 98.22–98.94 | 98.65–98.76 | 98.72 | 98.43 | 98.68 |
| 6= | Upper Mustang | 53.31 | 49.28–56.59 | 42.59–60.97 | 53.73 | 52.65 | 53.94 |
| 6= | Ladakh | 35.19 | 31.14–38.25 | 28.96–43.41 | 35.43 | 34.53 | 35.93 |

Holuhraun and McMurdo Dry Valleys stay *not measured* (ArcticDEM/REMA not processed).

**Against the lunar south pole** (limited comparison: LOLA 20 m, polar stereographic): Ladakh 79.61 (1), Upper Mustang 63.59 (2), then a five-site tie group at 20.5–24.9. Steep Himalayan windows are closest to the rim-and-crater relief at the pole. No placement or DEM checks exist for the lunar window, so only method sensitivity is used for its ties.

## 5. Calibration and evaluation findings

- **Saturation / base rate.** 90 unselected windows on a regular grid inside the downloaded SRTM tiles have a median index of 98.16. 44.4% score ≥ 99, 57.8% ≥ 95 and 86.7% ≥ 50. A high terrain index mostly separates low-relief from high-relief landscapes. The app prints this base rate beside every Jezero ranking.
- **Reference stability.** Moving the Jezero window 2 km N/S/E/W gives 99.98, 99.96, 99.90 and 99.70. Removing the halo gives 100.0. Placement noise is at most 0.3 points at the reference, and up to ±9 points for rugged Earth windows (Upper Mustang 42.6–61.0).
- **DEM choice.** NASADEM agrees with SRTMGL1 within 0.5 points everywhere. Copernicus GLO-30 is within 1.0 point where measured.
- **MOLA vs CTX** at 480 m over 30 km: median slope 1.40° vs 1.56°, W1 0.36°. Regional agreement only. MOLA cannot validate the 60–240 m scales.
- **Method sensitivity.** Across 20 configurations (weights ±20%, τ ±20%, three scale schemes, redundancy-adjusted weights), no rank changes. Every observed rank change happens inside a declared tie group, so the ranking is reported as sensitive to method only within those groups.

## 6. Temperature comparability audit

| Check | Required | Result |
|---|---|---|
| Product identity and units | yes | pass: MYD11A2.061 and MEDA CAL_TIRS, both kelvin |
| Same physical quantity | yes | pass: thermal-IR skin temperature (emissivity assumptions differ) |
| Spatial support | yes | **fail**: ~10⁸ m² AOI mean vs a few m² point |
| Sampling equivalence | yes | **fail**: 8-day composites vs per-sol windows |
| Local solar time | yes | pass: matched to measured MODIS view times |
| Seasonal coverage | yes | pass |
| Rover inside the reference AOI | yes | pass |

Decision: **measured · context only** for every Earth site. Day and night medians are still shown side by side, labelled as context.

## 7. Data and provider registry

`backend/app/data/datasets.json` has 22 records, each with product ID, purpose, AOIs covered, resolution, period, authentication, local status and limitations. The Sources page renders it. Resources from the official list that were reviewed but are not processed (EMIT L2B, AW3D30, RADARSAT-1, RCM, the CSA SAR tutorial, ESA OSC, CRISM, SHARAD, LROC/Diviner/LEND/Mini-RF) are marked **evaluated for later use**. No bulk download was made.

## 8. User-AOI screening jobs

`POST /api/explore/jobs` runs a bounded pipeline: one worker, a queue cap of 4, 3 jobs per client per hour, and a global daily cap. The states are queued → acquiring → processing → quality_check → ready, with terminal failed, unsupported and requires_credentials. Each job fetches SRTMGL1 tiles (cached, checksummed), measures the same 10 km window as the showcase sites, applies the same quality gate and compares with terrain-v4.0 against both references. A recent Sentinel-2 crop is added when one passes the same footprint and AOI-cloud rules. Results are labelled *screening*. Jobs interrupted by a restart are marked failed on startup. Outside 56° S–60° N the request is *unsupported* and nothing is fetched. Without an Earthdata token and with no cached tile it is *requires_credentials*, and again nothing is fetched.

## 9. Tests

- Backend: `pytest -q` gives 198 passed. New: `test_terrain_v4.py` (Gaussian reference values, invalid inputs, unit mismatch, W1, weights, hand-computed index, v3 preservation), `test_evidence_v2.py` (statuses, partial index formula, profile states, eligibility, tie ranks, lunar reference, thermal audit, worked example, report reproducibility, imagery metadata, CTX registration), and `test_jobs.py` (bounds, NaN, credentials, every state transition on a synthetic tile, void-window quality failure, rate limit, queue cap, restart recovery, ID validation). External services are mocked. No ordinary test makes a network call.
- Live (opt-in): `TERRALUNA_LIVE=1 pytest tests/test_live_providers.py` runs 10 read-only checks. Each stored Sentinel-2 product ID and acquisition time must match its Planetary Computer STAC record. The GIBS VIIRS layer must still be listed, with a latest date no earlier than the stored one. SRTMGL1.003 must be published in CMR under LPCLOUD. The LOLA LDEM_875S_20M file size must match the manifest (HTTP HEAD). No raster is downloaded and no credential is sent. All 10 passed on 2026-11-14.
- Browser: `frontend/e2e/terraluna.spec.ts` runs against a production build on 1327×660, 1680×1000 and 390 px. Explore job states are mocked with `page.route`, and the v2 contract fixture is the stored real API response.

## 10. Remaining limitations

- Only terrain is scored. Geology (EMIT/CRISM), water/ice, surface processes and subsurface evidence are not processed. Field-test suitability is a documented record, never a score.
- The terrain index saturates for low-relief terrain (§5). It cannot distinguish an alluvial fan from a lava plain.
- τ values were set after three sites were seen. They were frozen before the four held-out sites, but they have not been fitted to independent expert labels.
- The lunar comparison has one 10 km window, no placement or DEM checks, and no illumination or thermal dimension.
- Copernicus GLO-30 is not measured for Meteor Crater because of a Planetary Computer rate limit during the run.
- The Atacama window contains infrastructure in its north-east quadrant, and no disturbance mask is applied.
