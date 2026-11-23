# Configuration

Up: {doc}`index`. Down: {doc}`../modules/config`. Full chapter: {doc}`/model/scenarios_configuration`.

## What it does

Every run names one or more scenarios (`run_scenarios` in `config/config.yaml`, or `--config scenario=<id>`). For
each, `config/config_loader.py` merges six layers, later ones winning:

1. the base defaults, `config/defaults/base.yaml` and `config/defaults/base/**` (the file path is the key path:
   `base/market/balancing.yaml` holds `market.balancing`);
2. the globals in `config/config.yaml`;
3. the overlay for the scenario's `method`, `config/defaults/method/<method>.yaml`;
4. the overlay for its `targets.source`, `config/defaults/source/<source>.yaml`;
5. the overlay for its `market.dispatch`, `config/defaults/dispatch/<dispatch>.yaml` (only `central` exists);
6. the scenario's own entry, from `config/scenarios.yaml` or a study under `config/studies/<study>/`.

It then derives what the scenario implies (year parameters, clustering presets), validates the result and refuses
renamed keys, naming the new path. Build and solve rules receive the scenario through `model_scenario_param(cfg)`,
report rules through `scenario_param(cfg)`.

## The declarations every scenario carries

| Key | Values | Decides |
|---|---|---|
| `targets.source` | `historical`, `CP30`, `FES` | where capacities and demand totals come from |
| `targets.edition`, `targets.pathway` | e.g. `2024`, `HT` | which publication and pathway |
| `method` | `historical`, `brownfield`, `gsp_block` | how the fleet is placed (supported pairs: historical + historical, CP30 + brownfield, FES + gsp_block) |
| `modelled_year` | a year | the system modelled |
| `renewables_year`, `demand_year` | a year | the weather and the demand shape |
| `network_model` | `ETYS`, `Reduced`, `Zonal` | the network ({doc}`network`) |
| `solve_period` | start and end | the hours solved |
| `market.enabled` | `true`, `false` | two-stage market or single solve ({doc}`dispatch`) |

A study (`config/studies/<study>/`) adds templates and families: a family expands to twelve monthly scenarios, each
solving one month on a shared network build.

## Asking where a value comes from

```bash
python config/config_loader.py --explain Test_Market --path solve.solver.name
```

The notebook {doc}`../notebooks/config_layers` does the same for every key of a scenario.

## Hands on

A merged dictionary per scenario. Every later part reads its settings from it and from nowhere else: scripts never
read a scenario file directly, and a code fallback must equal the base default.
