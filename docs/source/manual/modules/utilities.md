# Utilities: `scripts/utilities/`

Up: {doc}`index`.

| Module | Start from | Use |
|---|---|---|
| `logging_config.py` | `setup_logging`, `get_snakemake_logger` | the logging every script uses; logs under `logs/<area>/` |
| `network_io.py` | `load_network`, `save_network` | fast network reading and writing; NetCDF-safe text columns |
| `spatial_utils.py` | `wgs84_to_osgb36`, `ensure_osgb36_coordinates` | coordinate systems: buses are OSGB36, sites WGS84 |
| `scenario_detection.py` | `target_source`, `build_method`, `is_historical_scenario` | what kind of scenario a merged config is |
| `time_utils.py`, `timeseries_synchronization.py` | `create_canonical_snapshots`, `align_to_snapshots` | snapshots and series on the configured timestep |
| `calendar_year.py` | `on_calendar`, `fill_leap_day` | weather- and source-year series on the modelled year |
| `gsp_nodes.py` | `GspNodeLocator` | the node where a location's GSP takes its demand |
| `carrier_definitions.py` | `add_carriers_to_network` | carrier attributes |
| `fresh.py` | `require_fresh` | refuse stale workflow outputs |
| `code_fingerprint.py` | `fingerprint` | which code an output was built with |
| `prepare_cutouts.py`, `download_cutouts.py` | `prepare_cutouts` | weather cutouts: cached, Zenodo, then ERA5 |
| `retrieve_neso_document.py` | `retrieve` | NESO documents listed in `data/neso_documents.yaml`, checked by SHA-256 |
| `build_reference_tables.py` | | the docs' generated configuration-key and module tables |
