# Flexibility: storage and hydrogen

Up: {doc}`index`. Down: {doc}`../modules/flexibility`. Full chapter: {doc}`/model/flexibility/index`.

## What it does

Adds what moves electricity in time as an asset: storage, and the hydrogen system. Consumer flexibility is built with
demand ({doc}`demand`).

| Rule | Script | Adds |
|---|---|---|
| `extract_storage_from_repd` | `scripts/storage/storage_from_repd.py` | storage sites from REPD |
| `add_storage_to_network` | `scripts/storage/add_storage.py` | batteries, pumped hydro, long-duration storage as `StorageUnit`s |
| `add_hydrogen_system` | `scripts/hydrogen/add_hydrogen_system.py` (and `fes_hydrogen.py` for FES long range) | the `H2` bus, electrolyser and turbine `Link`s, hydrogen `Store`, hydrogen offtake `Load` |

## How they enter the solve

- **Storage** charges and discharges against prices within each solve window. Round-trip efficiencies, dispatch costs
  and standing losses are set by `storage.*`.
- **Hydrogen** joins the power system through links: electrolysers draw electricity from an electrical bus into the
  `H2` bus, turbines turn hydrogen back into electricity. The store carries hydrogen between seasons; studies solved
  month by month carry it across months with a seasonal pass (`scripts/market/seasonal_storage.py`).

## What a change must respect

The hydrogen bus is not an electrical bus. Its offtake `Load` is MWh of hydrogen, and the electricity electrolysers
draw is counted as GB demand through their links, not through the hydrogen bus ({doc}`../notebooks/electricity_buses`).

## Hands on

A network with every domestic asset, to which {doc}`interconnectors` adds the cables.
