# Dispatch

Up: {doc}`index`. Down: {doc}`../modules/dispatch` and {doc}`../modules/market`. Full chapter:
{doc}`/model/dispatch/index`.

## What it does

Decides what runs, hour by hour, on the finished network. There are two ways, chosen by `market.enabled`.

| | Single solve (`market.enabled: false`, the default) | Two-stage market (`market.enabled: true`) |
|---|---|---|
| Question | the cheapest feasible dispatch | what the market schedules, and what it costs to make that schedule fit the network |
| Rules | `finalize_network`, `solve_network` | `finalize_network`, `solve_wholesale_market`, `solve_balancing_mechanism`, `analyze_market_results` |
| Scripts | `scripts/solve/solve_network.py` | `scripts/market/solve_wholesale.py`, `scripts/market/solve_balancing.py` |
| Network limits | all of them, in one optimisation | none in Stage 1 (copperplate); all in Stage 2 |
| Prices | one per bus | one GB wholesale price; nodal prices after balancing |
| Main outputs | `{scenario}_solved.nc`, results tables | `{scenario}_wholesale.nc`, `{scenario}_balancing.nc`, constraint costs, redispatch |

## The two stages

1. **Wholesale (Stage 1).** The mainland is collapsed to one bus (`scripts/market/copperplate.py`); islands and
   foreign buses keep their links and limits. The solve rolls over day-ahead windows and gives every unit a position
   and one GB price.
2. **Balancing (Stage 2).** The network is reloaded with its real ratings. Every unit is anchored to its Stage 1
   position and can move up at its offer or down at its bid (`scripts/market/market_utils.py`); supported plant bid
   what its support scheme would forgo (`cfd_bm_bids.py`, `support_bids.py`). The least-cost set of moves that fits
   the network is the redispatch; its cost is the constraint cost.

The notebook {doc}`../notebooks/two_stage_market` runs both stages on three buses with the model's own copperplate.

The `central` dispatch overlay (`market.dispatch: central`, `config/defaults/dispatch/central.yaml`) is the
alternative in which the operator schedules and corrects at resource cost.

## Settings

`solve.solver` (Gurobi by default, HiGHS as the open alternative), `solve.mode`, `market.wholesale.*`,
`market.balancing.*`, `support.*`, `solve_period`.

Before a run that solves anything, do a dry run (`snakemake -n`): on the full ETYS network a solve can take hours. To
try something, use a one-week `solve_period` on the Reduced or Zonal network.

## Hands on

Solved networks and tables in `resources/network/`, `resources/market/` and `resources/results/`
({doc}`/reference/outputs`), read by {doc}`after_the_solve`.
