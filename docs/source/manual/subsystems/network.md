# Network

Up: {doc}`index`. Down: {doc}`../modules/network`. Full chapter: {doc}`/model/network/index`.

## What it does

Builds the buses and branches of the scenario's `network_model`, and later, at solve time, the limits they impose.

| `network_model` | Buses | Built by |
|---|---|---|
| `ETYS` | about 2,000, from NESO's Electricity Ten Year Statement appendices, with the upgrades due by `modelled_year` | `process_ETYS_data` then `build_ETYS_base_network` |
| `Reduced` | 32 | `build_reduced_base_network` |
| `Zonal` | 17 | `build_zonal_base_network` |
| `ETYS` + `network.clustering` | as few as you choose | `cluster_network`, after the full build |

| Rule | Script | Writes |
|---|---|---|
| `process_ETYS_data` | `scripts/network_build/process_ETYS_data.py` | standard CSVs from the ETYS workbooks |
| `build_ETYS_base_network` | `scripts/network_build/ETYS_network.py` | `resources/network/{scenario}_network.nc` |
| `build_reduced_base_network`, `build_zonal_base_network` | `scripts/network_build/build_network.py` | `resources/network/{scenario}_network.nc` |
| `cluster_network` (optional) | `scripts/network_clustering/cluster_network.py` | the clustered network and `{scenario}_clustering_busmap.csv` |

## What a change must respect

- **Impedances** are carried as per unit on 100 MVA and converted to PyPSA's units once
  (`scripts/network_build/branch_units.py`). Change a transformer's rating only through
  `set_transformer_s_nom_preserving_impedance`, or its impedance changes with it.
- **Coordinates** of buses are OSGB36 (EPSG:27700) metres. Site data are WGS84, so convert before any nearest-bus
  match (`scripts/utilities/spatial_utils.py`). Everything landing on one corner bus is the sign of a mix-up.
- **Bus carriers** say what a bus carries: `AC` (or `DC`) for GB electrical nodes. Foreign buses carry `External` in
  their name. See {doc}`../notebooks/electricity_buses`.

## Constraints at solve time

The solve stage (`scripts/solve/`) adds what the topology alone does not: seasonal line ratings, a voltage floor below
which branches are relaxed, secured boundary limits with outage factors (`secured_boundaries.py`) for future years,
and, in the balancing stage, network-delivery cases that undo chosen ETYS upgrades (`scripts/market/network_delivery.py`).

## Hands on

A network of buses, lines, transformers and internal DC links, which {doc}`demand` fills next.
