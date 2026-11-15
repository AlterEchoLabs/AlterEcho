# Data acquisition and reproduction

Retain verified local products. This review acquired no new scientific datasets: all 14 terrain inputs and 13 imagery records were present and passed the local audit. A cached crop is a derived artifact, not an immutable copy of its remote parent. Do not overwrite a verified input to improve its appearance.

## Audit before acquisition

From `backend`, using a fresh Python environment with `requirements-dev.txt`:

```powershell
python -m app.scripts.audit_sources --write
python -m app.scripts.validate_catalog_integrity
python -m app.scripts.reproduce_release
```

The first command writes `data/manifests/acquisition-v1/source-registry.json`, validates the schema and hashes raw inputs, extracted tiles, local crops and display images. The second checks historical processed provenance. The third recalculates all registered primary-grid scored distributions without replacing them. JSON text checksums normalize CRLF to LF; binary checksums hash exact bytes. The source registry records both explicitly.

## Earth terrain

Discover SRTMGL1.003 through [NASA CMR](https://cmr.earthdata.nasa.gov/search/site/docs/search/api.html) or [Earthdata Search](https://search.earthdata.nasa.gov/). Register the exact product, tile, AOI and official download URL in a manifest before acquisition. SRTM is a radar surface model, with vegetation/structure effects and approximately 60 N to 56 S coverage. NASADEM is related to SRTM and is not independent ground truth.

Set `EARTHDATA_TOKEN`, or both `EARTHDATA_USERNAME` and `EARTHDATA_PASSWORD`, in the process environment or ignored `backend/.env`. Never paste a credential into a command committed to Git. Then run:

```powershell
python -m app.scripts.acquire_dataset --source-id earth-atacama-south-srtmgl1
python -m app.scripts.process_site --site-id earth-atacama-south --aoi-id earth-atacama-south-aoi-v1 --source-id earth-atacama-south-srtmgl1 --input data/raw/S25W070.hgt
python -m app.scripts.assess_aoi_landcover
python -m app.scripts.analogue_v1_calibration
```

Acquisition requires credentials even when invoked manually against an existing manifest. Do not run it merely to audit cached files. Missing credentials must produce an explicit failure; the existing atlas does not require a provider call. The calibration command regenerates scientific artifacts and should be run in a separate checkout or after preserving the existing outputs for review. Do not silently accept changed scores.

The current mask excludes a 60 m analysis cell when at least half its area is WorldCover built-up class 50. It does not apply the older one-cell dilation described in stale prose. The original Atacama industrial complex was not detected by WorldCover and remains explicitly excluded. Vegetation, water and snow are not fully quantified terrain exclusions in the current method; their effects remain a limitation.

## Mars references

Use the [USGS controlled CTX DTM catalogue](https://stac.astrogeology.usgs.gov/docs/data/mars/ctxdtms/) and its documented STAC API. Preserve the collection item and asset, body radius, projected CRS, source posting, nodata, quality statistics and crop method. The current local crops retain their exact checksums; their parent archive file is not falsely described as a locally downloaded full raster.

```powershell
python -m app.scripts.register_mars_references
python -m app.scripts.analogue_v1_references
```

These commands can write scientific artifacts. Review source selection and generated diffs. Gale, InSight, Gusev and Eberswalde already have official products; no alternative is needed merely because it is higher resolution. Jezero keeps its existing window and DEM. A new reference needs full AOI/halo support, stereo-quality review, provenance, display assets and reference-switching regression tests before acceptance.

## Lunar terrain

Use [PDS LOLA](https://pds-geosciences.wustl.edu/missions/lro/lola.htm) labels and archived products. The existing command is:

```powershell
python -m app.scripts.register_lunar_reference
python -m app.scripts.analogue_v1_references
```

The registered local LOLA derivative is in metres. Preserve the conversion and crop provenance. The lunar reference currently fails the tolerance/resolution-floor condition, so re-acquisition alone does not authorize a lunar score. Illumination, polar track density, interpolation and permanently shadowed-region assessment need separate expert review.

## Imagery and other families

```powershell
python -m app.scripts.acquire_planetary_computer_imagery --site-id earth-meteor-crater --aoi-id earth-meteor-crater-aoi-v1
python -m app.scripts.acquire_mars_imagery
python -m app.scripts.acquire_modis_lst
python -m app.scripts.acquire_meda_ground_temperature
```

Sentinel-2 and CTX imagery are display-only. Preserve exact scene IDs, timestamps, rendered/native pixels, AOI coverage, SCL cloud/shadow/snow statistics, registration and crop checksum. Do not save expiring signed URLs. Temperature remains diagnostic: current MODIS area composites and MEDA rover-point samples differ in support and temporal sampling. Mineralogy, resource evidence, Diviner, SAR and additional agency products remain planned until a specific comparable measurement is justified. No acquisition was blocked by authentication in this review because no new protected download was necessary; this is not a claim that credentials are available.

## Storage and release discipline

Raw/interim/cache files and credentials remain ignored. Commit manifests, small derived artifacts, scripts, schemas and checksum records. Archive a prior manifest before accepting changed product bytes. Local release audit and reproduction are repeatable; older acquisition/calibration scripts are not all immutable-output workflows. In particular, do not use their force/regeneration options without preserving the old version. Complete acquisition timestamps, vertical datum labels and upstream effective-resolution metadata remain explicit product-review gaps where the source registry has null fields.

## Reproduce a result without downloads

```powershell
python -m app.scripts.reproduce_release
python -m app.scripts.build_methods_paper
python -m app.scripts.build_methods_paper --check
python -m app.scripts.build_system_guide
python -m pytest tests/test_paper_numbers.py tests/test_provenance.py -q
```

The `/api/v3/result` JSON includes exact calculation-input hashes for the selected Earth/reference pair, configuration, calibration and background population. Source byte hashes are in the acquisition registry. This establishes reproducibility and traceability, not independent scientific validity.
