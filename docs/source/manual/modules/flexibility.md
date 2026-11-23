# Flexibility: `scripts/storage/`, `scripts/hydrogen/`

Up: {doc}`../subsystems/flexibility`.

| Module | Rule | Does |
|---|---|---|
| `storage/storage_from_repd.py` | `extract_storage_from_repd` | storage sites from REPD, GB only, with commissioning years |
| `storage/storage_from_tec.py`, `storage_parameters.py` | (data preparation) | TEC register storage, and the parameters (energy capacity, efficiencies) |
| `storage/add_storage.py` | `add_storage_to_network` | storage units filtered by commissioning year, scaled for future scenarios, placed at FES GSPs (`GspLocator`) |
| `hydrogen/add_hydrogen_system.py` | `add_hydrogen_system` | the `H2` bus, electrolysers (`place_fes_electrolysers`), turbines, store and offtake |
| `hydrogen/fes_hydrogen.py` | (from `add_hydrogen_system`) | the FES long-range hydrogen system (`add_fes_hydrogen_system`) |

## Conventions

- The hydrogen bus has carrier `H2`. Electrolysers are links with `bus0` on an electrical bus and `bus1` on the
  hydrogen bus; turbines the other way. The accounts find electrolysers by exactly that shape.
- Consumer flexibility is not built here (see {doc}`demand`).

Tests: `tests/unit/test_add_storage.py`, the `test_*hydrogen*` files, and `tests/unit/test_electricity_buses.py` for
how the hydrogen bus is kept out of GB demand.
