# Phase 9 audit: scientific scoring, explainable results and the planetary explorer

Branch `feature/terraluna-phase-6`, starting commit `3e31b1b` (Phase 7/8 documentation). Inputs: the AlterEcho project handbook (31 pp.), the research handoff, and the analogue-method handoff (`analogue-method-v1.0` proposal). The screenshots mentioned in the request were not attached, so their findings are taken from the request text: scores of about 99.5–99.9 for several Earth sites, Balanced science shown on 30 % of planned evidence, built infrastructure in the Atacama window, and an Earth globe that cannot zoom into the study area.

## 1. What Phases 7–8 actually implemented

- terrain-v4.0. W1 on fixed-bin histograms, with each bin's mass placed at its lower edge. The transform is s = exp(−0.5 (W1/τ)²). τ = 8° / 200 m / 30 m / 150 m, carried over from Phase 5. Four families are equally weighted and averaged over 60, 120 and 240 m.
- analog-evidence-v2.0. Partial index, coverage, profile states, and tie groups from placement, DEM and method ranges.
- Seven Earth windows, a Jezero CTX reference and a limited LOLA lunar reference.
- Sentinel-2 crops, a provider registry, Explore jobs, and Method, Sources and Report pages.
- The Earth "Globe" mode was a three.js sphere with a 4k Blue Marble texture (about 10 km per pixel). `OrbitControls minDistance = 1.7` on a unit sphere stopped the camera about 4,460 km above Earth's surface.
- The overview map is a flat MapLibre map over Blue Marble tiles (max zoom 8). Its fit stopped at zoom 8.5.

## 2. Trace of the near-99.9 cluster (Jezero reference, 60 m grid)

Pipeline for every window:

1. Checksum-verified DEM (SRTMGL1.003 tile, Jezero CTX DEM, or LOLA LDEM).
2. 10 km AOI centred on the registered point, on a local metric grid (UTM; the Jezero DEM is equirectangular true at 18.4663° N, so it has no east–west distortion).
3. 1.2 km halo, then bilinear resampling to 60, 120 and 240 m.
4. Kernels: slope (metric gradient), local relief (1 km max − min), roughness (300 m standard deviation), relative elevation (z − median).
5. Distribution per feature, then W1 against the reference, then τ, then the transform.
6. Family and scale weights, then the API, then the displayed number.

| Site | DEM tile(s) · SHA-256 | Built-up excluded | Slope median E / P (°) | Rel. elev. p10–p90 E / P (m) | Binned W1 slope (v4) | Exact W1 slope | Binned W1 rel. elev. (v4) | Exact W1 rel. elev. |
|---|---|---|---|---|---|---|---|---|
| Atacama (original) | S25W070 · 31ff152bdf60… | 0.00% | 2.43 / 1.83 | −57.2…89.9 / −58.7…105.5 | 0.524 | 0.586 | 4.81 | 6.20 |
| Craters of the Moon | N43W114 · 65076c24d022… | 0.01% | 1.49 / 1.83 | −37.1…60.8 / −58.7…105.5 | 0.617 | 0.689 | 14.81 | 14.92 |
| Hanksville (MDRS) | N38W111 · c71e33cbfedc… | 0.00% | 2.47 / 1.83 | −41.0…72.0 / −58.7…105.5 | 1.079 | 1.250 | 11.08 | 13.45 |
| Meteor Crater | 4-tile mosaic · a839e3a03eae… | 0.01% | 1.23 / 1.83 | −33.5…28.2 / −58.7…105.5 | 0.918 | 1.035 | 23.15 | 25.99 |
| Atacama south (new) | S25W070 · 31ff152bdf60… | 0.00% | 2.69 / 1.83 | −79.8…44.7 / −58.7…105.5 | 0.727 | 0.822 | 14.77 | 15.64 |
| Dallol, Danakil | N14E040 · a7f37842278d… | 0.00% | 1.00 / 1.83 | −1.8…3.9 / −58.7…105.5 | 1.198 | 1.340 | 39.21 | 42.70 |
| Upper Mustang | N29E083 · 7ab9f9c07f8a… | 0.00% | 16.94 / 1.83 | −288.6…541.1 / −58.7…105.5 | 13.107 | 15.384 | 202.88 | 218.99 |
| Ladakh | N34E077 · 01d169724e5c… | 1.01% | 24.60 / 1.83 | −486.5…616.5 / −58.7…105.5 | 16.698 | 20.053 | 311.86 | 297.93 |

d/τ under terrain-v4.0:

| Site | slope | local relief | roughness | rel. elev. | v4 index |
|---|---|---|---|---|---|
| Atacama (original) | 0.065 | 0.039 | 0.016 | 0.032 | 99.92 |
| Craters of the Moon | 0.077 | 0.047 | 0.023 | 0.099 | 99.79 |
| Hanksville | 0.135 | 0.061 | 0.043 | 0.074 | 99.70 |
| Meteor Crater | 0.115 | 0.058 | 0.037 | 0.154 | 99.48 |
| Danakil | 0.150 | 0.092 | 0.054 | 0.261 | 98.68 |
| Upper Mustang | 1.638 | 0.988 | 0.580 | 1.353 | 53.31 |
| Ladakh | 2.087 | 1.275 | 0.773 | 2.079 | 35.19 |

Stepwise decomposition (each column changes one thing):

| Site | v4 published | 60 m only | exact W1 | scored features only | ln 2 transform | τ from Earth contrast (= v1.0) | v1.0 scenario range | v1.0 rank |
|---|---|---|---|---|---|---|---|---|
| Atacama (original) | 99.92 | 99.91 | 99.87 | 99.82 | 99.76 | 99.42 | — | excluded |
| Craters of the Moon | 99.79 | 99.77 | 99.72 | 99.57 | 99.40 | 98.23 | 91.7–99.0 | 1= |
| Hanksville | 99.70 | 99.64 | 99.47 | 99.19 | 98.88 | 97.38 | 92.8–98.7 | 1= |
| Meteor Crater | 99.48 | 99.48 | 99.27 | 98.84 | 98.39 | 95.12 | 85.4–98.3 | 1= |
| Atacama south | 99.77 | 99.74 | 99.67 | 99.47 | 99.26 | 97.90 | 93.1–98.7 | 1= |
| Danakil | 98.68 | 98.74 | 98.35 | 97.32 | 96.31 | 88.61 | 76.7–93.7 | 1= |
| Upper Mustang | 53.31 | 53.03 | 40.45 | 25.09 | 15.26 | 0.57 | 0.0–3.6 | 6= |
| Ladakh | 35.19 | 35.34 | 24.90 | 9.12 | 3.89 | 0.01 | 0.0–0.3 | 6= |

**Root cause.** There was no unit error, duplicate input or masking fault. Every low-relief window had d/τ between 0.016 and 0.15 on every v4 family. At d/τ = 0.065, exp(−0.5 · 0.065²) = 0.998, so the index was saturated by design.

1. The Phase 5 tolerances were 10–20 times the observed differences.
2. Local relief and roughness measure the same construct as slope (Spearman ρ 0.985–0.998 across 88 unselected windows). They also had the smallest ratios, so they pushed the average up.
3. Binned W1 read 10–20 % low because sub-bin differences vanished.
4. The surviving differences are at or below what the data can resolve. Craters of the Moon and Atacama south are within the resolution floor on both scored features.

About half of unselected Earth windows still score 90 or more (49 %; 1 % score 99 or more, against 44 % under v4). A high terrain index mostly means low relief, and the order among low-relief windows is not resolved. The app shows this as one tie group. Scores were not stretched.

## 3. analogue-method-v1.0 (terrain-v5.0)

```
scalar        d_k = |x_E,k − x_P,k|                                  (same units)
distribution  d_k = W1 = ∫₀¹ |F_E,k⁻¹(u) − F_P,k⁻¹(u)| du              (500 midpoint quantiles of equal-area cells)
feature       s_k = exp(−ln 2 · (d_k/τ_k)²)                          d = τ → 0.5, d = 2τ → 0.0625
family        S_g = Σ a_k|g s_k                                        (a sums to 1; every required feature eligible)
profile       observed_index = 100 Σ w_g I_g S_g / Σ w_g I_g           (undefined when no family qualifies)
              evidence_coverage = Σ w_g I_g
```

- **Primary grid:** 60 m. The 120 m and 240 m grids are sensitivity scenarios, as the handoff proposes.
- **Redundancy rule.** Medians with Spearman |ρ| ≥ 0.95 count as one construct. Slope and relative elevation are scored with a = 0.5 each. Local relief and roughness are shown as diagnostics.
- **Resolution floor δ.** δ = √(δ_place² + δ_dem²).
  - δ_place: largest W1 when the Jezero window moves 2 km north, south, east or west.
  - δ_dem: largest W1 between SRTMGL1 and NASADEM or Copernicus GLO-30 for the same Earth window (15 pairs measured; GLO-30 at Meteor Crater was rate-limited and recorded as not measured).
  - Values: slope **1.17°** (placement 0.68°, DEM 0.96°); relative elevation **22.2 m** (placement 22.1 m, DEM 0.89 m).
- **Tolerance τ.** τ is the median W1 between unselected pairs of Earth land windows (Earth terrain contrast), accepted only if τ ≥ 3δ.
  - Slope **5.81°**; leave-one-tile-out range 4.52–6.34°.
  - Relative elevation **77.1 m**; range 55.1–88.6 m. This passes the 3δ test narrowly; with one tile left out it can fail.
  - Population: 88 windows, excluding any within 10 km of a candidate centre. The rules use only the reference, DEM pairs and unselected windows. Candidates were already known, so this is not a blind test.
- **Masks.** ESA WorldCover v200 (2021): a cell is excluded when it is at least 50 % built-up. A first "any pixel + 1 cell" rule removed 11.5 % of Ladakh's valley-floor cells and was replaced because it biased the result towards steep terrain. Built-up share per window ranges from 0 to 1.6 % (Ladakh).
- **Eligibility.** Every attempted feature records a reason: coverage below 90 %, units differ, redundant, or τ below 3δ. A family is eligible only when every scored feature is. Missing data are never scored as zero.
- **Ranking.** Candidates are ranked only on one eligibility key (reference, method, profile, weights, scored features, τ, scale, DEM product, mask). Tie groups come from overlapping scenario ranges: four placements, four reference placements, two DEMs, two grids, τ × 0.75 / 1.25, and feature weights 0.25 / 0.75. Competition ranks are shown as "1=".
- **Compatibility.** terrain-v4.0 and analog-evidence-v2.0 are still served at `/api/v2/compare`, and analog-evidence-v1.0 at `/api/evidence/compare`. The new method is served at `/api/v3/*`.

### Independent checks

| Check | Result |
|---|---|
| Handoff reference arithmetic (section 9) | All asserts pass. `analogue_reference.py` is verbatim; random cross-checks of the production W1 and index agree to 1e-9. |
| Identical copy of Jezero | 100.0 |
| Tilted plane 15° | 2.06 |
| Ridges, 150 m every 2 km | 38.2 |
| Rough fractal relief, 1,500 m | 21.3 |
| Gentle fractal relief, 300 m (look-alike) | 88.4. Its slope and relief distributions really are close to Jezero's. This demonstrates the documented limitation that distributions ignore spatial arrangement. |
| Unselected Earth windows (n = 88) | median 87.4; 49 % ≥ 90; 1 % ≥ 99 |

## 4. Mode-by-mode status

| Mode | State | Measured coverage | What the Simple result says |
|---|---|---|---|
| Terrain analogy (Jezero) | ranked, with ties | 100 % of plan (terrain only) | Close or different on measured terrain at 60 m. Ties are shown where the data cannot separate sites. Terrain only. |
| Terrain analogy (Moon) | ranked, limited | 100 % of plan | Ladakh 47.7 and Upper Mustang 30.4 tie at the top; the others are about 0. One window, no placement or illumination checks. |
| Balanced science | partial, never ranked | 30 % | "Terrain evidence available; 30% of planned science evidence measured." No overall result. |
| Rover mobility | partial | 80 % (field-test gate missing) | Broad 60 m context only. Wheel-scale traversability, rock hazards and soil strength are not observed. |
| Biosignature fieldwork | not assessed | 10 % terrain, not task-critical | No AOI-level mineral, process or preservation evidence. No claim about life. |
| Mars-base field testing | partial | 35 % (thermal fails audit) | Comparable terrain only. Pressure, gravity, radiation, access, logistics and construction are not assessed. Not base suitability. |

## 5. Atacama decision

The original window (centre 24.2000° S, 69.9000° W; W −69.9492, E −69.8508, S −24.2450, N −24.1550) contains a large industrial complex: rectangular pads, buildings and graded ground. ESA WorldCover classes it as bare (0.0014 % built-up), so no automated mask exists. The selection rule was fixed before any terrain value of the new window was computed:

- move due south until the north edge is 3 km past the original centre (8 km);
- accept the new window only if the 10 m Sentinel-2 crop shows no buildings, pads, pits or heaps;
- stay inside the verified tile S25W070.

The new window `earth-atacama-south` (centre 24.2722° S, 69.9005° W; W −69.9498, E −69.8512, S −24.3171, N −24.2273) passed. Unpaved tracks and a survey grid remain; each line is narrower than one 60 m cell. The original site keeps its artifacts so historical methods still reproduce. analogue-method-v1.0 lists it as excluded with the reason.

## 6. Globe and local map

The three.js Earth globe is replaced, for measured Earth sites, by a MapLibre globe projection (maplibre-gl 6.16, already in the project). The globe is orientation only for Mars, the Moon and unmeasured sites.

- **Fly-to.** Selecting a site flies from the globe to the exact 10 km analysis boundary. Corners come from the API's UTM grid, not from the browser.
- **Layers.** The 10 m Sentinel-2 crop is placed as a georeferenced image source, with hillshade and slope layers from the scoring DEM as alternatives. VIIRS (375 m) is an optional context layer.
- **Controls and labels.** Scale bar, north reset, zoom and pan with mouse, touch or keyboard, "Fit study window" and "Whole Earth" buttons, acquisition dates and attribution. Reduced motion turns the animations off.
- **Zoom cap.** Zoom stops half a level past the crop's native 10 m (about 14.3–14.4). The caption reports the display resolution against the source resolution, so no extra detail is implied.
- **Load fix.** The map waits for `style.load` rather than `load`, so overlays appear even while slow GIBS tiles stream in.

## 7. Dataset roles

Served at `/api/v3/data-roles`, with a "Why this data?" dialog on each result and a section on the Sources page.

| Product | Role | Used in | Cannot establish |
|---|---|---|---|
| SRTMGL1.003 (~30 m → 60 m) | scored input | slope and relative-elevation W1 | soil strength, sub-grid rocks, mineralogy, post-2000 change |
| Mars 2020 CTX DEM 20 m | scored input | reference distributions, placement floor | ancient lake conditions, rock size, dust |
| LOLA LDEM_875S_20M | scored input (Moon) | limited lunar reference | illumination, thermal, regolith |
| NASADEM / Copernicus GLO-30 | uncertainty input | δ_dem, DEM scenarios | which DEM is correct |
| ESA WorldCover v200 | quality mask | built-up exclusion | mines and heaps (classed bare), construction dates |
| Sentinel-2 L2A 10 m | display only | inspection, contamination check | geology, terrain shape, current conditions |
| GIBS VIIRS ~375 m | display only | recent regional context | anything at metre scale; not live |
| CTX orthomosaic 6 m | display only | reference view | mineralogy |
| MODIS LST / MEDA | context measurement | thermal audit (fails) | Mars-equivalent conditions |
| MOLA 463 m | uncertainty input | regional CTX check | anything at 60 m |
| Globe textures | display only | orientation | anything about a window |
| Literature | context | research panels | properties of the exact window |

## 8. Validation still required before any accuracy claim

1. Expert-labelled analogue windows, nearby unsuitable windows and distinct negative controls. Evaluate discrimination and precision at k with whole regions held out, then freeze τ and the weights.
2. A morphology descriptor (for example drainage or crater shape) for tasks that need spatial arrangement. The fractal look-alike shows what distributions miss.
3. The geology family (EMIT on Earth, CRISM at Jezero) with a comparability audit. Until then Balanced science and Biosignature fieldwork cannot conclude anything.
4. Wheel-scale terrain (1 m or finer) and soil observations for rover mobility.
5. Lunar placement and illumination checks, and a Copernicus GLO-30 retry for Meteor Crater.
6. Spatial-block resampling for any future interval. The scenario ranges here are sensitivities, not confidence intervals.
