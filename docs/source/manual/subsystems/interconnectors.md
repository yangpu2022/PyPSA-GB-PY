# Interconnectors

Up: {doc}`index`. Down: {doc}`../modules/interconnectors`. Full chapter: {doc}`/model/interconnectors`.

## What it does

Adds each cable in service by `modelled_year`, a foreign bus at its far end, and a price-taking foreign market on that
bus.

| Rule | Script | Does |
|---|---|---|
| `ingest_dukes`, `ingest_neso_register`, `combine_datasets`, `enrich_locations`, `clean` | `scripts/interconnectors/` | one register of cables from DUKES and the NESO register |
| `map_to_buses` | `scripts/interconnectors/map_to_buses.py` | each landing point to a bus of this network; names the foreign buses |
| `availability` | `scripts/interconnectors/availability.py` | hourly availability |
| `build_interconnector_price_shape`, `build_tyndp_price_shape`, `build_cp30_foreign_prices` | `scripts/interconnectors/` | foreign prices |
| `add_interconnectors_to_network` | `scripts/interconnectors/add_to_network.py` | the cables and foreign markets; writes `..._hydrogen_interconnectors.nc` |

## How a cable is represented

In future years (and historical back-tests) a cable is two non-negative links, import and export, with losses in the
direction of flow and a shared-capacity constraint so the two never exceed the rating together
(`scripts/interconnectors/market_coupling.py`). In historical years by default it is fixed to the observed flow. The
foreign market is a supply generator (carrier `EU_market`) and an export sink.

## What a change must respect

Foreign buses carry `External` in their name and a non-GB country. That is how the copperplate leaves them out of the
mainland and how every GB total leaves out their loads and generators.

## Hands on

The finished network, `resources/network/{scenario}.nc` after `finalize_network`, ready for {doc}`dispatch`.
