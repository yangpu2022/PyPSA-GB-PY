# Two-stage market: `scripts/market/`

Up: {doc}`../subsystems/dispatch`. Notebooks: {doc}`../notebooks/two_stage_market`,
{doc}`../notebooks/electricity_buses`.

## The stages

| Module | Rule | Does |
|---|---|---|
| `solve_wholesale.py` | `solve_wholesale_market` | Stage 1: rolling day-ahead windows on the copperplate; scarcity pricing; storage churn checks |
| `copperplate.py` | (from Stage 1) | `collapse_mainland`, `expand_results`: the exact copperplate, mainland on one hub bus |
| `solve_balancing.py` | `solve_balancing_mechanism` | Stage 2: the full network, units anchored to Stage 1 positions, bids and offers |
| `analyze_market.py` | `analyze_market_results` | the market summary, interconnector metrics and dashboard |
| `market_accounting.py` | (from the analysis) | the accounting definitions (`METRIC_DEFINITIONS`) and reconciliation |

## Prices, bids and what is held

| Module | Does |
|---|---|
| `market_utils.py` | bid and offer prices, storage dispatch-cost floors and churn guards, hydrogen offtake and supply prices |
| `cfd_bm_bids.py` | contract-value bids for CfD plant (`ContractValueBids`) |
| `support_bids.py` | bids and offers for a long-range fleet from its support labels |
| `pricing_basis.py` | the balancing stage's pricing basis: bids and offers, or marginal cost |
| `must_take.py` | units never curtailed or redispatched |
| `interconnector_counter_trade.py` | cables re-traded in balancing, and their price |
| `network_delivery.py` | network-delivery cases that undo chosen ETYS upgrades in balancing |
| `forecast_error.py` | day-ahead forecast error in the scheduling stage |
| `scarcity_pricing.py` | the scarcity curve of Stage 1 |
| `seasonal_storage.py` | the two-pass carry of hydrogen storage across independently solved months |
| `wholesale_commitment.py` | Stage 1 unit commitment with prices (a variant) |

## GB electrical buses

`market_accounting._is_gb_electrical_bus(buses)` returns, for a bus table, which buses carry GB electricity:

1. the carrier, trimmed and lower-cased, is in `ELECTRICAL_BUS_CARRIERS` (`""`, `"ac"`, `"dc"`);
2. the name does not contain `External`;
3. where a `country` column exists, it is `GB` or empty.

`_gb_electricity_demand_mwh(network, hours)` applies it: loads on those buses, plus consumer-flexibility draw on them,
plus the positive `p0` of links from a GB electrical bus to a non-electrical bus (electrolysers), each weighted by
the snapshot's hours. `scripts/consumer_bill/project_future_bill._electrical_buses(ds)` applies the same rule to an
open NetCDF file and returns `None` when the file has no bus table.

`tests/unit/test_electricity_buses.py` pins the carriers, case and whitespace handling, the External and country
rules, the snapshot weighting, the electrolyser draw and its sign, and the NetCDF path. A change to the rule changes
every demand total, demand-weighted price and bill: run that file and `tests/unit/test_consumer_flex_is_demand.py`.

## Conventions

- Stage 2 always reloads the network with real ratings; Stage 1's relaxation never reaches it.
- Accounting measures say what they are and are not (`METRIC_DEFINITIONS`): the modelled redispatch cost is not NESO's
  total balancing cost; feasibility slack is reported apart from ordinary redispatch.
