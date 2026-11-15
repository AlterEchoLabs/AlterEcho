# Final pass: audit, discrimination analysis, Mars references and research paper

Branch `feature/terraluna-phase-6`. Method `analogue-method-v1.0` / `terrain-v5.0`; the historical methods are still served at `/api/v2/compare` (terrain-v4.0, analog-evidence-v2.0) and `/api/evidence/compare` (analog-evidence-v1.0).

## 1. Audit of the system as found

**Traced and reproduced.** For Atacama south against Jezero, the whole chain was traced and then recomputed independently with the methodology handoff's reference code (`build_methods_paper.py`). The service and the recomputation agree exactly (difference below 10⁻⁹ index points). The chain:

- SRTMGL1.003 tile S25W070 (SHA-256 `31ff152b…`) and the Jezero CTX DEM (`ba7f706e…`)
- 10 km AOI, 1.2 km halo, bilinear resampling to 60 m, then the kernels
- 500 inverted-CDF quantiles, then W1, τ, s, the family score and the observed index
- tie groups, then the API, then the UI

| Quantity | Value |
|---|---|
| Slope d | 0.82249° |
| Slope τ | 5.8058° |
| Slope s | 0.986185 |
| Relative-elevation d | 15.6373 m |
| Relative-elevation τ | 77.1038 m |
| Relative-elevation s | 0.971893 |
| Weights | a = 0.5 each |
| Family score S | 0.979039 |
| A_obs | 97.9039 (API 97.90) |
| Coverage | C = 1.0 |
| Resolution floors | 1.1708° and 22.1523 m |

The four-decimal similarities shown in the UI recombine to 97.905; the difference is display rounding only. The 500-quantile W1 differs from the exact all-cell W1 by 0.06 %.

**Proven by tests:**

- the reference values of the transform
- W1 against the reference implementation
- the gates (coverage, units, τ ≥ 3δ, critical families)
- determinism
- ties, profile states, exclusions
- explorer corners
- data roles
- reference provenance and projection
- reference switching
- background shares
- consistency between the paper and the API

**Defects found and fixed in this pass:**

1. *Atacama south was measured without its land-cover mask.* The WorldCover check had run before the window was registered. After assessment the window is 0 % built-up, and re-measuring with the mask reproduced every quantile exactly; the provenance record is corrected.
2. *Jezero's resolution floor was applied to the lunar reference.* That had produced a lunar ranking (Ladakh 47.7). The lunar window's own 2 km placement test gives δ = 3.35° and 194.7 m, which fails τ ≥ 3δ, so lunar comparisons now show distances without an index.
3. *The family score was rounded to six decimals before computing the index.* It is now full precision internally and rounded only for display.
4. *Wording.* "Cannot be told apart" overstated what two uncertainty tests show. It now reads "not resolved from the reference by these tests (2 km reference move and DEM-product swap)". The index is named the "experimental terrain evidence index".
5. *Gale documentation.* It claimed the window lies wholly on the plains; the CTX image shows a dark-toned band in its south-east corner. Corrected.
6. *Mars-base text.* It asserted a failed thermal audit for references that have no thermal record. It is now conditional.
7. *UI.* The frontend hard-coded Jezero text and thumbnails; the reference catalogue is now API-driven (`/api/v3/references`). Mobile layout overflow from a new grid rule is fixed. Explore now blocks duplicate submissions while a job runs.

## 2. Is the index informative? (discrimination analysis)

Files: `analogue-v1-population.json` (88 unselected windows, 60 m quantiles) and `analogue-v1-discrimination.json`. The scenario ranges and background shares below describe a sample; they are not confidence intervals.

| Reference | Background median | Share ≥ 90 | δ slope | δ relative elevation | Scored |
|---|---|---|---|---|---|
| Jezero | 87.4 | 49 % | 1.17° | 22.2 m | yes |
| Gale (Aeolis Palus) | 86.7 | 44 % | 1.10° | 15.3 m | yes |
| InSight (Elysium Planitia) | 88.4 | 47 % | 0.96° | 3.8 m | yes |
| Gusev plains | 85.6 | 42 % | 0.96° | 3.7 m | yes |
| Eberswalde delta | 86.8 | 46 % | 1.00° | 17.5 m | yes |
| Lunar south pole | – | – | 3.35° | 194.7 m | distances only |

**Findings:**

- **No artefact behind the high share.** The background windows don't overlap (33 km spacing), and no unit or mask fault was found.
- **Why the share is high.** It reflects a real limitation: at 60 m, slope and relative-elevation distributions separate rugged from low-relief terrain but don't order low-relief windows. The background distribution is bimodal: about 60 % of windows score above 75 and about 33 % below 50.
- **Single features and alternative tolerances.** Slope alone and relative elevation alone give 47 % and 49 % at 90 or more against Jezero. The Phase 5 tolerances give 55 %, half the current τ gives 19 %, and double gives 58 %.
- **The tolerance depends on the sample.** Leaving one region out gives τ_slope 3.68–9.42° and τ_rel 42.7–146.7 m.
- **The candidate order is stable.** The top-five order is unchanged when τ is recomputed with each region left out.
- **The background sample is limited.** It covers only 4 regions (Western USA 53 windows, Himalaya 17, Central Andes 9, Afar 9), all in tiles first downloaded for candidate sites, so it is not 88 independent samples.
- **Synthetic controls.**

  | Control | Index |
  |---|---|
  | 15° tilted plane | 2.1 |
  | 150 m ridges every 2 km | 38.2 |
  | Rough 1,500 m fractal relief | 21.3 |
  | Identical copy of Jezero | 100 |
  | Gentle 300 m fractal relief | 88.4 |

  The last one shows that distributions ignore spatial arrangement.

**Decision.** The index was not altered: no cosmetic tolerance change and no new version. The UI and the paper now report each candidate's background share (for example, 17 % of background windows score at least as high as Atacama south against Jezero), and the Method page states the limitation plainly. A better-discriminating method needs a justified spatial descriptor and expert-labelled validation; that is left as open work, not done here.

## 3. Mars references

Accepted references are listed below. Selection rule: among STAC products covering at least 99 % of the window and 98 % of the halo, take the one with the lowest median stereo intersection error. Each window is read with HTTP range requests and reprojected once onto a local equirectangular grid true to scale at its latitude. All products are CC0, DOI 10.5066/P9JKVWR3.

| Reference | Product (STAC item) | Asset | Core valid | Intersection error (median / p95) | Clip SHA-256 |
|---|---|---|---|---|---|
| Gale Crater floor (Aeolis Palus), 4.5625° S, 137.4417° E | T01_000815_1749_XN_05S222W__K19_060629_1752_XI_04S222W | geoid_adjusted_dem | 99.94 % | 0.49 / 1.50 m | `e258cc97…` |
| Elysium Planitia (InSight), 4.5024° N, 135.6234° E | N15_068239_1823_XN_02N224W__F18_042827_1842_XN_04N224W | geoid_adjusted_dem | 99.97 % | 0.44 / 1.37 m | `4be42bd3…` |
| Gusev crater plains (Spirit), 14.5684° S, 175.4726° E | P22_009530_1653_XI_14S184W__P06_003333_1652_XI_14S184W | geoid_adjusted_dem | 100 % | 4.23 / 6.31 m | `05c903c1…` |
| Eberswalde crater delta, 23.85° S, 33.55° W | B22_018056_1559_XN_24S033W__G01_018557_1555_XN_24S033W | dtm | 99.98 % | 0.65 / 2.54 m | `015a2b90…` |

- **Gale.** The first candidate product had a 47 m median intersection error and was rejected by the quality-first rule.
- **Gusev.** Only one fully covering product had a low error; the other four had errors of 70–112 m.
- **InSight.** The first product covered only 13 % of the window.
- **Other candidates.** The Gale merged 1 m DEM, the InSight far-east and far-west CTX DTMs, Oxia Planum and Meridiani were not needed once four diverse references passed. The CTX-DTM collection covers Oxia Planum and Meridiani, so they remain candidates for a later version.
- **Context citations** (all verified through Crossref): Grotzinger et al. 2014, Golombek et al. 2020, Golombek et al. 2006, Malin & Edgett 2003. They are regional or rover-scale context, never evidence about a window.

## 4. Visual evidence and frontend

**Earth window:**

- a MapLibre globe flies to the exact 10 km grid boundary;
- the 10 m Sentinel-2 crop, with hillshade and slope from the scoring DEM, and VIIRS context;
- a scale bar, north arrow, dates and attribution;
- zoom capped half a level past native detail.

**Every reference:**

- its own CTX orthoimage (LOLA hillshade for the Moon), hillshade and slope;
- a new synchronised compare, which shows the Earth and reference windows at the same ground scale with shared zoom and pan by mouse, touch or keyboard, capped at 4×, with display against source resolution in the caption.

**Interface changes:**

- reference cards for five Mars windows and the Moon;
- candidate search, filter and ordering (by rank or background share only when results are comparable);
- a background-check line in the Simple result;
- discrimination in Full evidence;
- a larger type scale (16 px body) and larger maps;
- reduced-motion support throughout.

## 5. Tests and checks

All results are from the final state of this branch, on 15 November 2026.

| Check | Command | Result |
|---|---|---|
| Backend tests | `cd backend && .venv-geo/Scripts/python.exe -m pytest -q` | 255 passed, 11 skipped (all opt-in live provider checks, run with TERRALUNA_LIVE=1); external services mocked |
| Paper drift check | `python -m app.scripts.build_methods_paper --check` | passes (exit 0): `docs/paper/methods.md` matches a rebuild from the live service |
| Paper numbers against the API | `tests/test_paper_numbers.py` (part of the suite) | passes; the worked example agrees with the API within 10⁻⁸ |
| Artifact integrity | `python -m app.scripts.validate_catalog_integrity` | `passed` (artifact integrity only; no scientific validation) |
| Type check | `cd frontend && npx tsc --noEmit` | clean |
| Lint | `npm run lint` | clean |
| Browser tests | `npx playwright test` (production build, API on 8100) | 45 passed in 5.6 min, at desktop 1327 px, wide 1680 px and mobile 390 px |
| Secret scan | grep over tracked and untracked files for token, key and signed-URL patterns | no credential values found; `backend/.env` is git-ignored |

**Performance.** These numbers come from the production build on this Windows 11 laptop, run in headless Chromium with software rendering (SwiftShader). Each figure is the median of three fresh browser contexts at 1366 × 768. This is a throttled laptop, not a real low-end device.

| Measure | Unthrottled | CPU 4× slower, about 9 Mbit/s with 40 ms latency |
|---|---|---|
| Load event | 0.17 s | 1.13 s |
| DOMContentLoaded | 0.05 s | 0.35 s |
| Largest contentful paint | 0.52 s | 3.82 s |
| Ranked results visible | 1.18 s | 5.51 s (range 3.34–6.32 s) |
| Switching reference to Gale, until its result shows | 0.22 s | 0.93 s (4.0 s on the first, cold run) |
| JavaScript transferred | 717 KB | 717 KB |

Under throttling, most of the time before results appear goes to the comparison request and to starting the globe. This pass did not optimise either. Script: a Playwright and Chrome DevTools Protocol script that applies the throttling and reads the Performance API. It is not committed.
