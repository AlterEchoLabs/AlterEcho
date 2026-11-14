# Geospatial data artifacts

- `aoi/`: versioned GeoJSON study windows.
- `manifests/`: source products, access metadata, and checksums.
- `processed/`: real terrain summaries and processing-run reports used at runtime.
- `raw/`, `interim/`, and `cache/`: local-only ignored data.

The four production windows use 10,000 m requested extents, 60 m cells, 167 x 167 grids, and 10,020 m actual processed extents. Run `python -m app.scripts.validate_catalog_integrity` from `backend/` to verify catalog/artifact consistency. This verifies engineering integrity, not independent scientific validity.
