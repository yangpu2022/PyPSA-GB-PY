# Configuration: `config/config_loader.py`

Up: {doc}`../subsystems/configuration`. Notebook: {doc}`../notebooks/config_layers`.

The one module that reads configuration. Everything else asks it.

| Function | Use |
|---|---|
| `load_config` | the main configuration with every scenario merged; what the `Snakefile` calls |
| `get_scenario`, `get_active_scenarios` | one merged scenario; the ones `run_scenarios` selects |
| `load_defaults` | the base defaults, assembled from `config/defaults/base.yaml` and `base/**` by file path |
| `load_layer` | one overlay (`method`, `source` or `dispatch`) |
| `read_config` | a YAML file, with the loader's checks |
| `load_scenario_entries`, `expand_families` | scenario entries from `scenarios.yaml` and the studies; a family's twelve months |
| `resolve_targets_and_method` | the `targets` and `method` a scenario declares (or, for frozen legacy ids, derives) |
| `validate_scenario`, `check_renamed_keys` | the checks; a renamed key is refused with its new path (`RENAMED_KEYS`) |
| `explain_scenario` | every file merged, and the file that set each leaf value (`--explain`) |
| `model_scenario_param`, `scenario_param` | what build and solve rules, and report rules, receive as the scenario |
| `deep_merge` | the merge: dictionaries merge key by key, anything else is replaced |

## Changing it

- A new key goes in the base defaults file whose path is its key path, with a comment saying what it is, its unit
  and its source. Rationale belongs in the docs.
- A renamed key goes in `RENAMED_KEYS`, so old scenarios fail with a message instead of silently using the default.
- A new scenario writes `targets` and `method` explicitly.

Tests: `tests/unit/` has the loader's tests; run `python -m pytest tests/unit -k config`.
