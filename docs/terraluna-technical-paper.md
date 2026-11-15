# Measuring terrain resemblance between Earth analog sites and Mars and Moon reference windows

**TerraLuna / AlterEcho atlas — technical paper for this build**
Team AlterEcho · NASA Space Apps Challenge 2026 · 15 November 2026
Method `analogue-method-v1.0`, terrain measurement `terrain-v5.0`. Every number in this paper was read from the running backend of this checkout, or recomputed from its stored measurements.

---

## Abstract

Rovers, instruments and field crews rehearse on Earth before they fly, and the choice of rehearsal site is usually argued in words. AlterEcho turns one part of that choice into a measurement. It compares the present-day terrain of a 10 km window on Earth with a 10 km reference window on Mars or the Moon, using only real elevation models, and it reports how far the result can be trusted.

Both windows are resampled to a common 60 m grid. The distributions of slope and relative elevation are compared with the one-dimensional Wasserstein distance, scaled by tolerances taken from 88 ordinary Earth landscapes, and combined into a terrain similarity index from 0 to 100. Each index is then placed against the same 88 ordinary windows scored the same way.

Against the Jezero crater window, the Atacama Desert window scores 97.9 and beats 73 of the 88 ordinary windows. Upper Mustang and Ladakh score below 1. The main finding is less flattering: 42–49% of ordinary Earth windows also score 90 or more against every Mars reference. The index reliably separates gentle terrain from rugged terrain, but it cannot rank one gentle site above another. The atlas therefore shows every index beside its standing among ordinary land, groups sites by terrain class instead of ranking them, and never presents a score as a percentage likeness.

## 1. The question

At a stated pair of windows and a stated grid, how closely do two measured terrain properties agree, and is that agreement larger than the measurement itself can resolve?

A result depends on five choices, and results with different choices are never ranked together:

$$
\mathcal{R} = \mathcal{R}(E,\,P,\,T,\,H,\,V)
$$

- $E$ is the Earth window.
- $P$ is the planetary reference window.
- $T$ is the comparison: terrain shape.
- $H$ is the epoch: today's surface, not the ancient environment that shaped it.
- $V$ is the method version.

The index is not a probability that a place "is like Mars". It does not measure geology, water, temperature, habitability, access or mission safety, and no agency has endorsed it.

## 2. From prototype to this build

| Stage | What it set out to do | What survives in this checkout |
|---|---|---|
| Terrain prototype (terrain-v1 to v3) | Process SRTM tiles into slope, relief and roughness for a few Earth sites and one Jezero window | The processing pipeline and integrity manifests; historical endpoints still reproduce |
| Evidence profiles (analog-evidence-v1/v2) | Combine terrain with geology, temperature and other families under task weights | Kept as `/api/evidence` and `/api/v2`; non-terrain families remain unmeasured or context-only |
| terrain-v4 | Score many features at three grids | Retired for scoring: 44% of ordinary windows scored 99 or more, so the numbers carried no information |
| analogue-method-v1.0 (terrain-v5) | Whole-distribution distances, tolerances from ordinary terrain, resolution floors, removal of duplicate features | The scoring method used everywhere in this build |
| Final references and audit | Four more Mars windows from USGS controlled CTX models; a background test with 88 ordinary windows | Five Mars references and one lunar reference |
| This release pass | Make the numbers readable and honest in the interface | Standing among ordinary land, terrain-class groups instead of rank badges, Explore scoring unified with the atlas, measured temperature and field-test context, KaTeX formulas, a Simple/Detailed reading mode |

## 3. Data

| Role | Product | Body | Native posting | Used for |
|---|---|---|---|---|
| Scored input | NASA SRTMGL1.003 (doi:10.5067/MEaSUREs/SRTM/SRTMGL1.003) | Earth | 1 arc-second (about 30 m), EGM96 metres, Feb 2000 | Slope and relative elevation of every Earth window |
| Scored input | Mars 2020 Science Investigation CTX DEM mosaic (doi:10.5066/P906QQT8) | Mars, Jezero | 20 m | Jezero reference |
| Scored input | USGS controlled CTX DTMs, STAC `mro_ctx_controlled_usgs_dtms` (doi:10.5066/P9JKVWR3, CC0) | Mars | 20 m | Gale, InSight, Gusev and Eberswalde references (lowest stereo error of the covering products) |
| Measured, not scored | LRO LOLA LDEM_875S_20M | Moon | 20 m | Lunar reference; fails its resolution floor, so distances only |
| Uncertainty check | NASADEM_HGT.001 and Copernicus GLO-30 | Earth | 1 arc-second | DEM-product term of the resolution floor; sensitivity scenarios |
| Quality mask | ESA WorldCover 10 m v200 (2021) | Earth | 10 m | Removes cells that are at least half built-up |
| Display only | Sentinel-2 L2A crops; CTX orthoimages; LOLA hillshade | All | 10 m / 6 m / 20 m | What the windows look like; never scored |
| Context, not scored | Aqua MODIS MYD11A2.061 (doi:10.5067/MODIS/MYD11A2.061); Mars 2020 MEDA TIRS (PDS) | Earth / Jezero | 1 km area mean / a few m² point | Surface temperature view; fails the comparability audit |

**Windows.** Seven Earth windows are measured and scored:

- Craters of the Moon (Idaho)
- Hanksville badlands at the Mars Desert Research Station (Utah)
- Dallol in the Danakil Depression (Ethiopia)
- Atacama Desert (Chile)
- Meteor Crater (Arizona)
- Upper Mustang (Nepal)
- Ladakh (India)

Three more windows are registered but not scored:

- **Atacama, first window.** It holds an industrial complex with graded pads that WorldCover classes as bare ground, so it cannot be masked. That flattened ground scored 99.4 against Jezero. It was replaced, under a rule fixed before any terrain was measured, by the window 8 km south, which is the "Atacama Desert" window used everywhere. The first window stays reachable by link, with the reason shown.
- **Holuhraun** (Iceland) and **McMurdo Dry Valleys** (Antarctica) lie outside SRTM coverage (60° N to 56° S) and are listed as not measured.

## 4. Method

### 4.1 Preparing the windows

Each elevation model is resampled bilinearly onto a north-up metric grid centred on the window:

- UTM for Earth;
- a local equirectangular grid, true to scale at the window latitude, for Mars;
- polar stereographic for the Moon.

The analysis grid is 60 m (167 × 167 core cells, at least twice the native posting). A 1.2 km halo keeps neighbourhood statistics complete, and only core cells are summarised. Missing data stay missing. A feature counts only when at least 90% of core cells are valid on both windows. The 60 m grid is a project choice: it cannot resolve rocks, wheel-scale hazards or soil strength [Zhang & Montgomery 1994].

### 4.2 Measurements

$$
\theta = \arctan\sqrt{\left(\frac{\partial z}{\partial x}\right)^{2} + \left(\frac{\partial z}{\partial y}\right)^{2}}, \qquad z_{\text{rel}} = z - \operatorname{median}(z)
$$

$z$ is elevation in metres and $x$, $y$ are ground distances in metres. Relative elevation removes the vertical datum, which cannot be compared between Earth, Mars and the Moon.

Local relief (maximum minus minimum in 1,020 m) and roughness (standard deviation in 300 m) are also measured. Across the ordinary windows their medians correlate with median slope at Spearman ρ = 0.985 and 0.998. Scoring all three would count one property three times, the redundancy that ruggedness indices are known for [Sappington et al. 2007]. They are therefore shown as diagnostics with zero weight. Relative elevation behaves independently (ρ = −0.244 with slope) and is scored.

### 4.3 Distance between two windows

$$
d_k = W_1(F_{E,k}, F_{P,k}) = \int_0^1 \left| F_{E,k}^{-1}(u) - F_{P,k}^{-1}(u) \right| \mathrm{d}u \;\approx\; \frac{1}{500}\sum_{i=1}^{500} \left| Q_{E,k}(u_i) - Q_{P,k}(u_i) \right|, \qquad u_i = \frac{i - \tfrac12}{500}
$$

$F$ is the empirical cumulative distribution of valid cells and $Q$ the inverted-CDF quantile function. $d_k$ has the feature's units: degrees for slope, metres for relief. For Atacama against Jezero, the 500-quantile approximation is within 0.06% of the exact all-cell distance. A distribution ignores where ridges, channels or craters sit.

### 4.4 From distance to similarity

$$
s_k = \exp\!\left[-\ln 2 \left(\frac{d_k}{\tau_k}\right)^{2}\right] = 2^{-(d_k/\tau_k)^2}, \qquad \tau_k = \operatorname*{median}_{i<j} W_1(F_{i,k}, F_{j,k})
$$

The similarity is 1 at zero distance, 0.5 at one tolerance and 0.0625 at two (unit-tested). The tolerance is the median distance over all 3,828 pairs of 88 ordinary Earth windows. These are unselected windows on a regular grid inside the downloaded SRTM tiles, excluding anything within 10 km of a candidate. This gives:

- $\tau_{\text{slope}} = 5.8058°$
- $\tau_{\text{rel}} = 77.1038$ m

A site that differs from the reference as much as two typical Earth landscapes differ from each other therefore scores 0.5. This is a project definition, not a threshold fitted to expert labels. A Gaussian kernel with ½ in the exponent was considered; the ln 2 form was kept because it gives the tolerance a direct meaning, and changing kernels after seeing results was ruled out.

### 4.5 Resolution floor

$$
\delta_k = \sqrt{\delta_{\text{place},k}^{2} + \delta_{\text{dem},k}^{2}}, \qquad \text{scored only if } \tau_k \ge 3\,\delta_k
$$

The two terms are:

- $\delta_{\text{place}}$: the largest change from moving the reference window 2 km north, south, east or west.
- $\delta_{\text{dem}}$: the largest change from swapping SRTMGL1 for NASADEM or Copernicus GLO-30.

For Jezero, $\delta_{\text{slope}} = 1.1708°$ and $\delta_{\text{rel}} = 22.1523$ m. When every scored distance is at or below its floor, the site is reported as "not resolved from the reference by these tests". The lunar window fails the condition: a 2 km move changes its relative elevation by about 195 m against a 77 m tolerance. Lunar comparisons therefore show distances without an index.

### 4.6 Index, coverage and terrain class

$$
S_g = \sum_k a_{k\mid g}\, s_k, \qquad A_{\text{obs}} = 100\,\frac{\sum_g w_g I_g S_g}{\sum_g w_g I_g}, \qquad C = \sum_g w_g I_g
$$

With slope and relative elevation weighted ½ each, and terrain the only measured family, $A_{\text{obs}} = 100\,S_{\text{terrain}}$. Here $C = 1$ means all of the planned terrain evidence was measured; it says nothing about anything else. Missing evidence is excluded from both sums, never counted as zero [OECD/JRC 2008].

A site is in the same terrain class as the reference when every scored distance is below its tolerance, a different class when every one is above it, and partly similar otherwise.

### 4.7 Standing among ordinary land

$$
N_{\text{closer}} = \#\{\, b \in \mathcal{B} : A_b < A_c \,\}, \qquad |\mathcal{B}| = 88
$$

$A_b$ is the index of each ordinary window against the same reference and $A_c$ the candidate's. The interface reads $N_{\text{closer}}$ in quarters:

| Standing | Verdict |
|---|---|
| ≥ 66 of 88 | "closer than most ordinary land" |
| 44–65 | "but so is a lot of ordinary gentle land" |
| fewer than 44 | "many ordinary windows are closer" |

### 4.8 Ties and sensitivity

Each index is recomputed under 15 to 17 scenarios:

- the Earth window moved 2 km four ways;
- the reference window moved 2 km four ways;
- each alternative Earth DEM;
- the 120 m and 240 m grids;
- tolerances × 0.75 and × 1.25;
- feature weights of 0.25 and 0.75.

Sites whose scenario ranges overlap cannot be put in order by the data. They are listed together inside their terrain-class group, without rank numbers. The ranges are sensitivities, not confidence intervals.

## 5. Results

### 5.1 Case study: Atacama Desert against Jezero

| Feature | Atacama (median · p90) | Jezero (median · p90) | $d$ | $\tau$ | $d/\tau$ | $s$ | $\delta$ | Points |
|---|---|---|---|---|---|---|---|---|
| Slope | 2.695° · 6.213° | 1.828° · 5.237° | 0.8225° | 5.8058° | 0.1417 | 0.986185 | 1.1708° | 49.3093 |
| Relative elevation | p90 44.96 m | p90 105.86 m | 15.6373 m | 77.1038 m | 0.2028 | 0.971893 | 22.1523 m | 48.5946 |
| Local relief (diagnostic) | 40.3 · 109.1 m | 33.7 · 81.0 m | 11.96 m | — | — | — | — | 0 |
| Roughness (diagnostic) | 3.61 · 8.26 m | 2.57 · 7.36 m | 1.02 m | — | — | — | — | 0 |

The two contributions add up to $A_{\text{obs}} = 97.9039$, displayed as **98/100** (97.90 in reports). Both distances sit below their floors, so the window is not resolved from Jezero by these tests.

Across 17 scenarios the index ranges from 93.12 to 98.65. It beats **73 of 88** ordinary windows, and it shares the "same terrain class" group with four other sites whose ranges overlap.

**Independent checks.**

- **Scoring code.** Recomputing the distances and similarities from the stored quantiles, outside the service, reproduces every site's index to two decimals.
- **Elevation tile.** Separate code, with its own UTM grid, its own bilinear resampling and NumPy gradients, recomputed slope straight from SRTM tile S25W070. Median slope is 2.687° against 2.695° stored, the 90th percentile 6.205° against 6.213°, and the relative-elevation 90th percentile 44.94 m against 44.96 m. The small gaps are grid alignment.
- **Explore path.** Screening the same centre through Explore, which scores from the raw tile, returns 97.9 and 73 of 88.

### 5.2 Contrast: Ladakh against Jezero

Ladakh's slope distribution differs by 20.05° ($d/\tau = 3.45$, $s = 0.00026$) and its relative elevation by 297.9 m ($d/\tau = 3.86$). The index is 0.01, it beats 6 of 88 ordinary windows, and it is in a different terrain class.

### 5.3 All sites against the five Mars references

Index, with ordinary windows beaten out of 88 in brackets.

| Earth window | Jezero | Gale | InSight | Gusev | Eberswalde |
|---|---|---|---|---|---|
| Craters of the Moon | 98.2 (78) | 98.9 (74) | 96.6 (66) | 96.4 (68) | 95.0 (68) |
| Atacama Desert | 97.9 (73) | 97.0 (64) | 98.4 (83) | 96.8 (73) | 98.3 (86) |
| Hanksville (MDRS) | 97.4 (71) | 96.1 (60) | 98.0 (81) | 97.1 (78) | 95.5 (68) |
| Meteor Crater | 95.1 (58) | 99.4 (79) | 96.2 (64) | 97.2 (79) | 91.7 (53) |
| Dallol | 88.6 (44) | 96.7 (64) | 93.4 (53) | 96.2 (65) | 84.6 (41) |
| Upper Mustang | 0.6 (9) | 0.3 (9) | 0.7 (9) | 0.5 (11) | 0.9 (9) |
| Ladakh | 0.0 (6) | 0.0 (6) | 0.0 (7) | 0.0 (8) | 0.0 (6) |

Against every reference the same five sites form the "same terrain class" group and the two Himalayan sites the "different" group. Within the first group, the scenario ranges overlap for every reference, so no order is claimed. The most distinctive single result is Atacama against Eberswalde: it beats 86 of 88 ordinary windows.

### 5.4 Is the index informative?

| Reference | Median ordinary window | Ordinary windows ≥ 90 |
|---|---|---|
| Jezero | 87.4 | 49% |
| Gale | 86.7 | 44% |
| InSight | 88.4 | 47% |
| Gusev | 85.6 | 42% |
| Eberswalde | 86.8 | 46% |

Nearly half of all ordinary land scores 90 or more. The ordinary windows are 33 km apart and do not overlap, and no unit or mask fault was found, so this is not an artefact. It is what two distribution features can do at 60 m: they separate rugged from gentle terrain, but most gentle windows look alike to them. Other ways of scoring do not fix it:

| Change | Ordinary windows ≥ 90 against Jezero |
|---|---|
| Slope alone | 47% |
| Relative elevation alone | 49% |
| An earlier version's tolerances | 55% |
| Half the current τ | 19% |
| Double the current τ | 58% |

The tolerance was not narrowed to push numbers down: that would make the index look stricter without making it more informative. Synthetic surfaces behave as expected against Jezero:

| Surface | Index |
|---|---|
| Identical copy | 100 |
| 15° plane | 2.06 |
| 150 m ridges every 2 km | 38.23 |
| Rough 1,500 m fractal | 21.25 |
| Gentle 300 m fractal | 88.39 |

The gentle fractal shows that a distribution says nothing about landforms.

### 5.5 Sensitivity

The tolerance depends on the sample:

| Left out | τ slope | τ relative elevation |
|---|---|---|
| One source tile | 4.52–6.34° | 55.1–88.6 m |
| One region | 3.68–9.42° | 42.7–146.7 m |

Against Jezero, the order of the five highest candidates is unchanged when τ is recomputed with each region left out. The ordinary windows come from four regions, all in tiles first downloaded for candidate sites: Western USA (53), Himalaya and Tibet (17), Central Andes (9) and Afar (9). They are not 88 independent samples. The candidate windows were known before the tolerance rule was fixed, so this is not a blind test.

### 5.6 Context shown beside the index

**Surface temperature.** Atacama's median skin temperature is about 48 °C by day and 6 °C at night (Aqua MODIS, 2024, 44 paired 8-day composites). Jezero's, measured by MEDA beside the rover, is about −4 °C by day and −77 °C at night. The two are not scored: an orbital 1 km area mean and a few square metres beside a rover differ in spatial support and sampling, and the audit records both failures.

**Field-test record.** The field-test view lists what each site, or its region, has been used for in published analog research:

| Studied at the window | Studied in the region | No peer-reviewed analog study found |
|---|---|---|
| Dallol, Hanksville (MDRS), Meteor Crater | Atacama, Craters of the Moon, Ladakh | Upper Mustang |

A famous analog is not evidence of terrain resemblance, and the reverse.

## 6. Limitations

What has been checked, and what has not:

- **Arithmetic: verified.** Reference values of the transform, the W₁ implementation, eligibility gates and determinism are verified by automated tests, and the case study was recomputed independently.
- **Scientific usefulness: not validated.** No expert-labelled analog pairs, negative controls or field outcomes have been used. No accuracy figure exists.

Known limits of the method and data:

- **Project definitions.** Tolerances, weights and the redundancy threshold were set by the project and depend on the background sample.
- **No ranking of gentle sites.** The index separates terrain classes but does not order gentle sites. The standing among ordinary land is the more useful number.
- **No landforms.** Distributions ignore spatial arrangement: channels, rims and ridges are invisible.
- **Terrain only.** Geology, water and ice, surface processes, habitability, access and safety are not assessed.
- **Present-day surfaces.** SRTM (2000), CTX stereo (2006 onward) and LOLA record today's surfaces. CTX stereo noise inflates slopes on very smooth plains.
- **Unmasked screening.** Areas screened in Explore are not masked for built-up land.

## 7. Reproducibility

```bash
# backend (from backend/)
.venv-geo/Scripts/python.exe -m uvicorn app.main:app --port 8000      # API used by the atlas
.venv-geo/Scripts/python.exe -m pytest -q                              # unit and API tests
.venv-geo/Scripts/python.exe -m app.scripts.validate_catalog_integrity # artifact checksums
.venv-geo/Scripts/python.exe -m app.scripts.build_methods_paper --check
# frontend (from frontend/)
npm run lint && npx tsc --noEmit && npm run build
npx playwright test          # starts its own API on :8100 and a production build on :3100
```

The scoring source of truth is `backend/app/services/analogue_v1_service.py` (`terrain_features`, `_standing`, `_terrain_class`). The configuration, including these formulas in LaTeX, is in `backend/app/data/analogue.v1.json`. Measurements are in `backend/data/processed/terrain-v5/`, and the background population and discrimination results are in `backend/data/processed/evaluation/`. The atlas, report, JSON export and Explore all read the same API fields.

## References

- Zhang, W. & Montgomery, D. R. (1994). Digital elevation model grid size, landscape representation, and hydrologic simulations. *Water Resources Research* 30, 1019–1028. doi:10.1029/93WR03553
- Sappington, J. M., Longshore, K. M. & Thompson, D. B. (2007). Quantifying landscape ruggedness for animal habitat analysis. *Journal of Wildlife Management* 71, 1419–1426. doi:10.2193/2005-723
- OECD/JRC (2008). *Handbook on Constructing Composite Indicators: Methodology and User Guide.* doi:10.1787/9789264043466-en
- Mangold, N. et al. (2021). Perseverance rover reveals an ancient delta-lake system and flood deposits at Jezero crater, Mars. *Science* 374, 711–717. doi:10.1126/science.abl4051
- Grotzinger, J. P. et al. (2014). A habitable fluvio-lacustrine environment at Yellowknife Bay, Gale Crater, Mars. *Science* 343, 1242777. doi:10.1126/science.1242777
- Golombek, M. et al. (2020). Geology of the InSight landing site on Mars. *Nature Communications* 11, 1014. doi:10.1038/s41467-020-14679-1
- Golombek, M. P. et al. (2006). Geology of the Gusev cratered plains from the Spirit rover transverse. *JGR Planets* 111. doi:10.1029/2005JE002503
- Malin, M. C. & Edgett, K. S. (2003). Evidence for persistent flow and aqueous sedimentation on early Mars. *Science* 302, 1931–1934. doi:10.1126/science.1090544
- NASA Technical Reports Server 20240000586: Atacama field testing report (context for the Atacama region only; not a validation of this window).
- Data products as listed in Section 3, with their DOIs.
