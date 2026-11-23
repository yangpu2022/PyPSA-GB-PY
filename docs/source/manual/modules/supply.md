# Supply: `scripts/renewables/`, `scripts/generators/`

Up: {doc}`../subsystems/supply`.

## Renewable profiles

| Module | Rule | Does |
|---|---|---|
| `renewables/prepare_renewable_site_data.py` | `prepare_renewable_site_data` | REPD sites ready for atlite |
| `renewables/prepare_future_pipeline_sites.py` | `prepare_future_pipeline_sites` | the named REPD pipeline for future years |
| `renewables/map_renewable_profiles.py` | `generate_renewable_profiles` | `RenewableProfileGenerator`: capacity-factor profiles from the weather cutout |
| `renewables/generate_marine_profiles.py`, `generate_hydro_profiles.py` | marine and hydro profile rules | synthetic marine and hydro profiles |
| `renewables/large_hydro_inflow.py`, `large_hydro_reservoir.py` | (imported) | monthly-shaped inflow and the reservoir path of large hydro |

## Generators

| Module | Rule | Does |
|---|---|---|
| `generators/integrate_renewable_generators.py` | `add_renewables_to_network` | renewable generators with their profiles (`filter_sites_by_year`, `select_profile_column`) |
| `generators/integrate_thermal_generators.py` | `add_thermal_generators_to_network` | thermal plant, routed by data source; FES plant spread spatially (`distribute_fes_generators_spatially`) |
| `generators/fes_supply.py` | (imported) | the FES long-range supply for a `gsp_block` build |
| `generators/DUKES_generator_data.py` | (data preparation) | historical thermal capacity from DUKES 5.11 |
| `generators/finalize_generator_integration.py` | `finalize_generator_integration` | `add_load_shedding_generators`, capacity summaries and the generator map |
| `generators/apply_marginal_costs.py` | `apply_marginal_costs_to_network` | `calculate_marginal_cost` from fuel, carbon and efficiency; future cost assumptions |

## Conventions

- Convert WGS84 site coordinates to OSGB36 before matching them to buses (`scripts/utilities/spatial_utils.py`).
- Every generator gets a marginal cost in `apply_marginal_costs`, after renewables and thermal plant are both in.
- The breakdown file `{scenario}_marginal_costs_breakdown.csv` must explain every cost: a new cost layer adds a column.

Tests: `tests/unit/test_apply_marginal_costs.py`, `test_aggregate_renewable_generators.py` and the generator tests.
