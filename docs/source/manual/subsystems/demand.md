# Demand

Up: {doc}`index`. Down: {doc}`../modules/demand`. Full chapter: {doc}`/model/demand/index`.

## What it does

Turns the scenario's demand year and targets into `Load`s on the network's buses, hour by hour, and, in the future
builds, carves the part that can move in time out of those loads as consumer flexibility.

| Scenario | Annual energy | Hourly shape | Placement |
|---|---|---|---|
| historical | ESPENI outturn | ESPENI of `demand_year` | fixed weights by GSP or by bus |
| FES (`gsp_block`) | FES consumer demand | a historical `demand_year` | FES GSP demand shares |
| CP30 (`brownfield`) | CP30 demand with losses | built from components, calibrated to a peak | FES 2024 GSP shares plus named transmission loads |
| FES long range | FES demand lines, component by component | built from components on the weather year | GSP demand nodes |

| Rule | Script | Writes |
|---|---|---|
| `build_base_demand` | `scripts/demand/load.py` | `{scenario}_network_demand_base.pkl` |
| `disaggregate_heat_pumps`, `disaggregate_electric_vehicles` | `scripts/demand/heat_pumps.py`, `electric_vehicles.py` | demand components |
| `build_fes_demand_components` | `scripts/demand/fes_demand.py` | FES long-range components and flexibility |
| `finalize_demand` | `scripts/demand/finalize_demand_integration.py` | `{scenario}_network_demand.pkl` and a demand summary |

## Settings

`demand.timeseries`, `demand.disaggregation` (which components are split out) and `demand.flexibility`.

## What a change must respect

Consumer flexibility (smart-charged and vehicle-to-grid EVs, heat, storage heaters, demand response, direct air
capture) is built as `StorageUnit`s on the demand buses, but it is **demand, not storage**: its carriers are listed
once in `scripts/demand/demand_carriers.py`, and every demand total, price weight and settlement counts what it draws.
Loads must sit on GB electrical buses to be counted as GB demand.

## Hands on

A network with demand, to which {doc}`supply` adds generators.
