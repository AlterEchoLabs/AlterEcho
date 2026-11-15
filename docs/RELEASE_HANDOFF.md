# AlterEcho production review handoff

15 November 2026. Work performed locally on `main`, which was clean at the start. No deployment, commit, push or history rewrite was performed. The numerical terrain method and existing verified scientific inputs were retained. This is a tested research prototype, not an independently validated mission-planning system.

## 1 What changed

Implemented source auditing, a typed source registry and JSON Schema, versioned acquisition inventory, current-artifact checksum gates, calculation-input hashes in exports, and explicit scientific-status labels. Failed task-critical gates now suppress overall API/export scores and sensitivity indices. Added themes, accessibility repairs, stronger request/download handling, reproducible release scripts and documentation.

## 2 Scientific method version

`analogue-method-v1.0` remains the numerical method. No tolerance, feature or weight was adjusted to make results more attractive. The comparison identity now documents the task-profile configuration R and includes its content digest in eligibility identity. This is a contract/provenance correction; historical endpoints remain versioned separately.

## 3 Processing versions

Current scoring uses `terrain-v5.0`, with 500 midpoint samples of each empirical inverse CDF. The primary grid is 60 m; 120/240 m are scenarios. Terrain-v2/v3 processing records and terrain-v4 historical/Explore results remain explicitly distinct. No claim is made that historical and current outputs may share a ranking.

## 4 Real Earth sites

Eight registered Earth terrain inputs passed byte/metadata checks and exact primary-grid reproduction: Atacama south, original Atacama, Upper Mustang, Ladakh, Dallol, Craters of the Moon, Hanksville/MDRS and Meteor Crater. Seven are current terrain candidates. Original Atacama remains excluded because of industrial contamination. Holuhraun and McMurdo remain planned. Exact centre coordinates and support are in the master guide and machine registry.

## 5 Real planetary references

Five Mars windows retain their official local DEM inputs: Jezero, Gale/Aeolis Palus, InSight/Elysium, Eberswalde delta and Gusev plains. The registered lunar south-pole LOLA derivative also reproduces, but fails the tolerance/resolution-floor gate: measured distances only, no index. A decorative globe is never evidence.

## 6 Sources and checksums

All 14 terrain inputs and 13 imagery records passed the local audit. Every primary-grid scored quantile recomputed exactly from the local rasters. Full binary SHA-256 values, byte sizes, projected raster metadata and LF-normalized derived hashes are in `backend/data/manifests/acquisition-v1/source-registry.json` and `DATA_SOURCE_REGISTRY.md`.

The Atacama-south input is `S25W070.hgt`, SHA-256 `31ff152bdf6000f313f122a8872d68aecb332ab688f3697933dec4c5abb0c11c`. Its compressed SRTMGL1.003 archive SHA-256 is `5def5b1a8ccc9fc9db063f4ef754cf77828db647a15a00041d1a2ca5b90e5078`. All other hashes are provided in full in the registry rather than abbreviated here.

No new scientific products were acquired. No new acquisition was blocked by authentication because none was necessary. Known rejected products/windows remain rejected: original Atacama contamination, poorly covering InSight candidates, and higher-error Mars stereo candidates documented in the historical registration report. Of 27 official landing-page checks, 25 resolved; the two CSA candidate links failed to connect and are not scoring inputs. Eleven live provider tests passed. Link availability and local checksums are not independent validation of the provider's measurements.

## 7 Scored and contextual variables

Scored: slope and relative-elevation distributions, each weight 0.50 within eligible terrain. Diagnostic: relief, roughness, alternative DEM scenarios, current thermal observations and lunar terrain distances. Quality mask: WorldCover built-up fraction >= 0.5 per analysis cell, without the stale documented dilation. Display-only: Sentinel/CTX imagery, hillshade/slope previews and global orientation imagery. Context: analogue history and regional literature. Minerals, resource families, wheel-scale soil/hazards and other critical evidence remain unavailable or planned.

## 8 Saturation and discrimination

The reproduced Atacama-south/Jezero index is **97.903885**, displayed/API **97.90**. Independent arithmetic agrees; all-cell W1 differs from the 500-quantile approximation by about 0.06% for each scored feature in this example. This is numerical agreement, not predictive accuracy.

The recorded Jezero background share >=90 is **0.489 across 88 windows**. Calibration samples come from four regions and share source geography; they are not 88 independent observations. Distribution descriptors do not encode spatial arrangement. Independent expert-labelled discrimination and predictive calibration remain unvalidated. Existing sensitivity outputs are retained and documented; no new expert labels were fabricated.

## 9 Security findings and fixes

Fixed the Content-Length-only body cap: streamed bodies now have a 32768-byte cap and 15-second deadline. ZIP members are checked before writing; extraction refuses to replace differing raw bytes and cleans temporary files. Acquisition refuses to rewrite a known checksum after an archive changes. A changed on-disk method configuration requires a service restart before comparison/export, preventing hashes from describing different inputs than the loaded calculation.

The frontend audit initially found seven moderate development-tool findings through minimatch. A scoped override to minimatch 11.0.8 resolved them; frontend and Python dependency reports contain zero known findings at the time checked. The tracked/nonignored-new-file secret-pattern scan found no credentials. These checks do not prove the application secure. Production hosting still needs HTTPS, explicit origins, reverse-proxy limits, monitoring and operational review. Existing deprecation warnings remain documented in test output.

## 10 Frontend improvements

Added Light/Dark/System preference with pre-paint application, persistence and system-change following. Updated semantic colors and map controls without filtering scientific imagery. Added a source-registry link, corrected mask/lunar role labels, retained detailed evidence, and made scrollable tables and commands keyboard accessible. Mobile navigation wraps cleanly. Explore explicitly names out-of-coverage requests. Existing synchronized views, reference switching and reports remain intact.

## 11 Accessibility

Automated axe WCAG 2 A/AA and 2.1 AA checks cover Atlas, Method, Sources, Explore and Report in both themes, with desktop, wide, tablet and mobile viewports. Release tests also cover reduced motion, theme persistence/system changes, skip navigation and horizontal overflow. Detailed outcomes are in `browser-accessibility-*.json`. Four routes passed a separate 200% CSS-zoom layout check. Physical browser UI zoom and a human screen-reader evaluation were not performed; CSS magnification and automated axe checks do not substitute for those checks.

## 12 Performance

The reproducible test records a single headless Chromium run with 4x CPU slowdown, 40 ms network latency and 1,125,000 bytes/second download throughput in `browser-performance.json`. The result is a host-specific timing, not a production SLO, device benchmark or 60 fps claim. No unsupported animation-performance claim is made.

## 13 Backend tests

Final result recorded after the release run below. The normal suite skips the 11 explicitly opt-in live checks; those were also run separately and all passed. Mathematical, scientific gating, provenance, archive immutability, streaming-body, API and documentation regressions are covered. Raster reproduction is separately recorded in `raster-reproduction.json`.

## 14 Frontend build and static checks

ESLint and TypeScript checks were run. Playwright starts a fresh production build and API server, so browser results exercise the production bundle. Full final outcomes are recorded below. The test interpreter is configurable with `ALTERECHO_PYTHON`; copied virtual environments are not portable.

## 15 Browser tests

The initial existing suite passed 45 tests. Intermediate release runs found a nonfocusable scrollable command block and an out-of-coverage message mismatch, both corrected. An intermediate contract failure occurred because the API server still held the earlier response model while the fixture had been regenerated; the final suite uses a fresh server. Final results are recorded below. Three repeated performance cases are intentionally skipped outside the laptop project; this does not skip route/accessibility coverage.

## 16 Documentation delivered

- `ALTERECHO_SYSTEM_AND_RESEARCH_GUIDE.md`, editable `.docx` and `.pdf`: all 40 requested topics, exact numerical example and AOI table.
- `PUBLIC_GUIDE.md`: concise public introduction.
- `DATA_SOURCE_REGISTRY.md`, `DATA_ACQUISITION_GUIDE.md`, typed registry/schema and acquisition-v1 inventory.
- `architecture.mmd`, `data-flow.mmd`, `calculation-flow.mmd` and generated `api-reference.json`.
- Updated generated paper source, DOCX and PDF, with native editable Word equations.
- Reproduction, dependency, link, accessibility and performance evidence files.

The master guide has nine pages and the methods paper six. Pages were rendered with Microsoft Word and visually inspected; the packaged LibreOffice renderer could not run because LibreOffice was absent. The repeatable Windows PDF export script is `export_word_pdf.ps1`. No fake rendering success is claimed for the unavailable renderer.

## 17 Exact run commands

From the repository root, in separate PowerShell terminals:

```powershell
cd backend
.venv-local/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```powershell
cd frontend
npm.cmd run dev
```

For a fresh checkout, create a new environment and install `backend/requirements-dev.txt`, then run `npm ci` in frontend. Raw data is ignored and must be restored/reacquired for raster reproduction; browsing uses committed small artifacts. No credential is needed merely to view the existing atlas.

## 18 Exact reproduction commands

```powershell
cd backend
.venv-local/Scripts/python.exe -m app.scripts.audit_sources --write
.venv-local/Scripts/python.exe -m app.scripts.reproduce_release
.venv-local/Scripts/python.exe -m app.scripts.build_methods_paper
.venv-local/Scripts/python.exe -m app.scripts.build_methods_paper --check
.venv-local/Scripts/python.exe -m app.scripts.build_system_guide
.venv-local/Scripts/python.exe -m pytest -q
$env:ALTERECHO_LIVE='1'
.venv-local/Scripts/python.exe -m pytest tests/test_live_providers.py -q
.venv-local/Scripts/python.exe -m app.scripts.release_security
cd ../frontend
npm.cmd run lint
npx.cmd tsc --noEmit
$env:ALTERECHO_PYTHON='.venv-local\Scripts\python.exe'
npm.cmd run test:e2e
cd ..
node docs/paper/tools/build_system_guide.cjs
node docs/paper/tools/build_docx.cjs
powershell -NoProfile -ExecutionPolicy Bypass -File docs/export_word_pdf.ps1 -DocumentPath docs/ALTERECHO_SYSTEM_AND_RESEARCH_GUIDE.docx
```

Node document tools require `npm ci --prefix docs/paper/tools`. Standalone `npm run build` can be run in frontend; the browser suite also builds production automatically. Acquisition and write-producing calibration commands are documented separately so reproduction does not silently replace the source science.

## 19 Remaining scientific limitations and unfinished validation

Implemented and tested does not mean independently validated. Expert-labelled/field validation, new compatible mineral and thermal families, resource interpretation, alternate lunar DEM checks, illumination/PSR assessment and full confounder masks remain unavailable. Several registry fields, including exact observation intervals and vertical-reference metadata for some product derivatives, remain null pending product-label review. Effective resolution is not inferred from posting size. Existing acquisition/calibration scripts are not all fully immutable version-store workflows; preserve old outputs before regeneration. Full manual assistive-technology testing and deployment security review remain external release work.

No scientific family was promoted merely to fill a panel. No download credential is currently required from the user to view the retained atlas. Protected re-acquisition needs an Earthdata credential supplied through ignored configuration or environment only.

## 20 Files requiring human review

Review the method-gating/provenance changes in `analogue_v1_service.py`, `provenance_service.py` and the acquisition/security changes before release. A geospatial reviewer should inspect the source registry's null fields, exact AOIs, land-cover limitations, stereo quality and calibration population. Review the master guide and acquisition guide as the research handoff. The generated documents and reports are ready for that review; the work is not represented as peer reviewed or independently scientifically validated.

## Final recorded checks

| Check | Actual result |
|---|---|
| Backend full suite | 278 passed; 11 opt-in provider tests skipped; 17 warnings |
| Live provider suite | 11 passed separately |
| Browser production suite | 50 passed; 3 repeated performance cases intentionally skipped; 6.6 minutes |
| Frontend production build | Passed as part of the fresh Playwright server startup |
| ESLint and TypeScript | Passed on the final frontend files |
| Accessibility | Zero axe violations across five routes, both themes and four viewports |
| 200% CSS magnification | Four routes passed; physical browser UI zoom not tested |
| Performance | Ranked results visible in 4029 ms in the single throttled run |
| Raster reproduction | 14/14 inputs reproduced; zero scored-quantile difference |
| Local source/image audit | 14 terrain inputs and 13 imagery records; zero audit failures |
| Catalog integrity and paper drift | Passed |
| Node/Python dependency audit | Zero known findings in saved reports |
| Credential pattern scan | No findings in tracked/nonignored-new UTF-8 files under the scan size cap |
| External source landing pages | 25/27 resolved; two unused CSA candidates failed to connect |
| Document visual QA | Nine guide pages and six paper pages inspected; native equations retained |

Browser logs included a Windows asyncio connection-reset traceback after browser disconnection; tests passed and no corresponding client application error was reported. This is retained as a host/runtime observation, not hidden as a clean-log claim. The final backend-only configuration-drift regression ran in pytest after the browser server started; it does not alter the frontend build.
