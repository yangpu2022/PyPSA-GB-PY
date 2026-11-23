# Network: `scripts/network_build/`, `scripts/network_clustering/`

Up: {doc}`../subsystems/network`.

## Modules the rules run

| Module | Rule | Does |
|---|---|---|
| `network_build/process_ETYS_data.py` | `process_ETYS_data` | raw ETYS workbooks to standard CSVs; buses from line data; GSP locations; repairs disconnected components |
| `network_build/ETYS_network.py` | `build_ETYS_base_network` | the ETYS network from those CSVs; buses on land; topology checks; coordinate overrides |
| `network_build/build_network.py` | `build_reduced_base_network`, `build_zonal_base_network` | `build_reduced_network`, `build_zonal_network` |
| `network_clustering/cluster_network.py` | `cluster_network` | `NetworkClusterer`: GSP, k-means, hierarchical or custom busmaps; keeps non-AC and External buses out of clustering |

## Helpers they share

| Module | Start from |
|---|---|
| `branch_units.py` | `line_pu100_to_pypsa`, `transformer_pu100_to_pypsa`, `convert_network_pu100_to_pypsa`, `set_transformer_s_nom_preserving_impedance` |
| `ETYS_upgrades.py` | the Appendix B upgrades and CP30 dated works applied by year (`add_cp30_dated_works`, `record_appendix_b_works`) |
| `appendix_b_record.py` | what each applied Appendix B row did, so a network-delivery case can undo it |
| `branch_attributes.py` | seasonal ratings and transmission licensee on each branch (`seasonal_rating_factors`) |
| `parallel_links.py` | `merge_parallel_internal_links` |
| `etys_file_registry.py` | the ETYS files of each publication year |
| `network_clustering/boundary_busmap.py`, `neso_zone_busmap.py` | boundary-respecting and NESO 17-zone busmaps |
| `network_clustering/aggregate_components.py` | merge identical components without changing the optimum |

## Conventions

- Impedances are per unit on 100 MVA until `convert_network_pu100_to_pypsa`; convert once, never twice.
- Bus `x`, `y` are OSGB36 metres.
- Non-AC buses (the hydrogen bus) and External buses are never clustered into GB AC clusters.

Tests: `tests/unit/test_ETYS_upgrades.py` and the other `test_*network*`, `test_*branch*` and `test_*cluster*` files.
