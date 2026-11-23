# After the solve

Up: {doc}`index`. Down: {doc}`../modules/after_the_solve`. Full chapter: {doc}`/model/after_the_solve/index`.

## What it does

Reads solved networks and writes what people use: results tables and dashboards, the market accounts of a two-stage
run, a study's year from its twelve months, checks against outturn and published targets, and the household bill.
None of it changes a solved network, and none of it triggers a solve.

| Output | Rule | Script |
|---|---|---|
| single-solve summary, dashboard, map and notebook | `analyze_and_visualize_solved_network`, `generate_analysis_notebook` | `scripts/analysis/analyze_solved_network.py`, `generate_analysis_notebook.py` |
| market summary and accounts | `analyze_market_results` | `scripts/market/analyze_market.py`, `market_accounting.py` |
| a study's year | `aggregate_CP30_months` | `scripts/market/aggregate_neso_comparator.py` |
| checks against ELEXON, NESO, CP30 and FES | `validate_bm_results`, `validate_neso_constraints`, `validate_CP30_*`, `validate_fes_dispatch` | `scripts/market/`, `scripts/CP30/`, `scripts/FES/` |
| household bill | `project_future_consumer_bill` and the bill rules | `scripts/consumer_bill/` |
| public-ownership accounts | `rules/public_ownership.smk` | `scripts/public_ownership/` |

## The rule every account shares

Demand, demand-weighted prices and bills count only **GB electrical buses**: carrier `AC`, `DC` or empty, not
`External` in the name, country `GB` or empty (`market_accounting._is_gb_electrical_bus`). On those buses they count
the loads, the electricity consumer flexibility draws, and the electricity electrolysers draw. They leave out the
hydrogen offtake (MWh of hydrogen) and foreign demand. The bill applies the same rule to a saved network file
(`project_future_bill._electrical_buses`). The rule, its edge cases and both uses are pinned by
`tests/unit/test_electricity_buses.py` and shown in {doc}`../notebooks/electricity_buses`.

## Settings

`consumer_bill.*` and `public_ownership.*`; the market accounts take their settings from `market.*`.

## Reporting a result

Say which file it came from (`resources/analysis/{scenario}_market_summary.json`, for example), and for a study,
whether it is one month or the year.
