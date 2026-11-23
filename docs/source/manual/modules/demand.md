# Demand: `scripts/demand/`

Up: {doc}`../subsystems/demand`.

| Module | Rule | Does |
|---|---|---|
| `load.py` | `build_base_demand` | base demand for every scenario type: historical ESPENI, FES and CP30 totals scaled onto GSP shares (`scale_gsp_shares_to_annual_total`, `get_cp30_electricity_demand_gwh`) |
| `heat_pumps.py` | `disaggregate_heat_pumps` | heat-pump demand by bus, and its tank and "cosy" flexibility |
| `electric_vehicles.py` | `disaggregate_electric_vehicles` | EV charging by bus; smart charging and V2G capacity from FES |
| `fes_demand.py` | `build_fes_demand_components` | FES long-range demand components and consumer flexibility |
| `cp30_demand.py` | (with `extract_cp30_demand_inputs`) | CP30 2030 demand: FES 2024 spatial basis, named large loads, a component-built shape |
| `integrate.py` | (from `finalize_demand`) | adds the disaggregated components to the network |
| `add_demand_flexibility.py` | (from `finalize_demand`) | the flexibility units |
| `finalize_demand_integration.py` | `finalize_demand` | `finalize_demand_integration`: the demand network and its summary |
| `demand_carriers.py` | (imported) | the carrier names of demand components and of consumer flexibility (`DEMAND_FLEX_STORAGE_CARRIERS`) |

## Conventions

- `demand_carriers.py` is the one list of consumer-flexibility carriers. The market accounts, the bill and the
  ownership settlement all read it: a new flexibility type goes there, or it will be counted as a storage asset.
- Flexibility is carved from the load it shifts, so the load plus what the flexibility draws is the demand.

Tests: `tests/unit/test_consumer_flex_is_demand.py` and the `test_*demand*` files.
