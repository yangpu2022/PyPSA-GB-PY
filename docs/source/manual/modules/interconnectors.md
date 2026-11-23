# Interconnectors: `scripts/interconnectors/`

Up: {doc}`../subsystems/interconnectors`.

| Module | Rule | Does |
|---|---|---|
| `ingest_dukes.py`, `ingest_neso_register.py`, `combine_datasets.py`, `enrich_locations.py`, `clean_interconnectors.py` | register rules | one cleaned register of cables |
| `map_to_buses.py` | `map_to_buses` | landing points to buses (`map_by_coordinates`, `apply_explicit_etys_bus_mapping`); foreign bus names (`create_external_bus_name`) |
| `availability.py` | `availability` | hourly availability, with outages and seasonal variation |
| `price_shape.py`, `build_price_shape.py`, `tyndp_prices.py`, `cp30_foreign_prices.py` | price rules | foreign prices: ENTSO-E shapes conditioned on GB wind, TYNDP, CP30 |
| `add_to_network.py` | `add_interconnectors_to_network` | `add_external_buses`, the cables and the foreign markets |
| `market_coupling.py` | (imported by the solves) | the shared-capacity constraint of directional links; volume tranches |

## Conventions

- A foreign bus name contains `External`. The copperplate (`EXTERNAL_BUS_PATTERN`), clustering and every GB total
  rely on it.
- A cable in a market year is two directional links; their joint limit is a constraint added at solve time, not a
  link attribute.

Tests: the `test_*interconnector*` files.
