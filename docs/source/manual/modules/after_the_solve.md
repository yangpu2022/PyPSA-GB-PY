# After the solve: `scripts/analysis/`, `scripts/consumer_bill/`, `scripts/public_ownership/`

Up: {doc}`../subsystems/after_the_solve`.

| Package | Start from | Does |
|---|---|---|
| `scripts/analysis/` | `analyze_solved_network.py`, `generate_analysis_notebook.py` | single-solve summaries, dashboards, maps, notebooks |
| `scripts/analysis/docs_figures/` | `common.py` and one script per docs section | the documentation's figures, from `resources/` |
| `scripts/consumer_bill/` | `project_future_bill.py` | a household bill from a solved market year: hourly prices weighted by GB electrical demand (`read_hourly_inputs`) |
| `scripts/public_ownership/` | `build_asset_finance_register.py`, `settlement.py`, `cfd_repricing.py` | an asset register from solved balancing networks, each asset's market and support settlement, and the CfD re-pricing |

## Conventions

- These steps read solved outputs and never trigger a solve. Use `scripts/utilities/fresh.py` (`require_fresh`) to
  refuse outputs Snakemake would rebuild.
- Demand weights use GB electrical buses only ({doc}`market`): the bill's `_electrical_buses` and the market's
  `_is_gb_electrical_bus` are one rule.
- Figures use the shared style in `scripts/analysis/docs_figures/common.py`.
