# Firm LCOE: renewables + storage (incl. LDES) vs nuclear vs gas CCUS

What does it cost per MWh delivered to meet the GB demand profile at a stated firmness, and
how much of that is storage? Published LCOEs price a MWh at the plant gate. This analysis
prices the service of meeting demand, so overbuild, curtailment, storage capex, round-trip
losses and cycles all come out of one optimisation. Full design:
[`docs/superpowers/specs/2026-11-18-firm-lcoe-weather-year-lp-design.md`](../../../docs/superpowers/specs/2026-11-18-firm-lcoe-weather-year-lp-design.md).

## Running it

All commands run from the repository root.

```bash
python scripts/analysis/firm_lcoe/inputs.py --build      # national CF (41 weather years) + demand -> parquet caches
python scripts/analysis/firm_lcoe/run_sweep.py           # every case and firmness, 41 years, 3-h blocks -> results.csv
python scripts/analysis/firm_lcoe/run_sweep.py --sens all --append   # sensitivities
python scripts/analysis/firm_lcoe/figures.py             # F1-F4 from results.csv
python scripts/analysis/firm_lcoe/report.py              # F1-F6, firm_lcoe.xlsx, firm_lcoe_report.html, output README
```

`figures.py` needs only `results.csv` (pandas, matplotlib), so the four figures can be redrawn
anywhere. `run_sweep.py` needs `gurobipy` and a Gurobi licence; the full sweep at 3-hour blocks
over 41 years is about 1.3 M variables per solve and took about six hours on a 14-core laptop.
For a quick try use `--years 2010 2013 --step 6 --no-recheck`.

| Figure | What it shows | Rows of results.csv used |
|---|---|---|
| F1_firm_lcoe_vs_firmness | firm LCOE against firmness, one line per case | base, all firmness levels |
| F2_cost_decomposition | GBP/MWh split into VRE used, VRE curtailed, battery, LDES, hydrogen, nuclear, gas, hourly top-up | base, firmness 0.99 and 1.0 |
| F3_capacity_mix | GW of generation, GWh of battery + LDES, TWh of hydrogen cavern | base, firmness 1.0 |
| F4_storage_cycles_duration | cycles per year and E/P duration of each store built | base, all firmness levels |

F5 and F6 (2024-25 market bids against the unit cost of shifting a MWh) are drawn by
`report.py` only when `resources/analysis/firm_lcoe/market_bids_2024_25.csv` exists. That file
is built by `market_bids.py`, which depends on the Modo API client in
`scripts/analysis/bidding_behaviour/` and is not in this branch yet.

Outputs go to `resources/analysis/firm_lcoe/` (not tracked).

## Method

- **Model** (`model.py`): one GB node, greenfield capacity expansion, written directly in the
  gurobipy matrix API (no PyPSA). Capacities are chosen jointly over all weather years; each
  store's state of charge is cyclic within each weather year. The objective is the mean annual
  cost over the weather years.
- **Firm LCOE** = annual system cost / annual energy delivered (demand minus unserved), in GBP/MWh,
  real 2024.
- **Firmness f**: in every weather year, unserved energy is at most (1 - f) of that year's demand.
  Unserved energy has no cost; f is swept from 0.90 to 1.0.
- **Time**: 3-hour block averages (119,720 periods over 41 years). Blocks smooth the peak from
  99.8 to 97.2 GW, so every f = 1.0 solve is followed by an hourly top-up: per weather year, an
  hourly capacity LP with the block capacities as lower bounds; the element-wise maximum over
  years is kept. The headline figure (`firm_lcoe_hourly`) includes the top-up cost. An hourly
  fixed-capacity re-check then reports LOLE hours.
- **Cases**: RE + storage (solar, onshore, offshore, battery, LDES, hydrogen); RE + storage with
  unabated CCGT capped at 5% of energy; nuclear + battery + LDES; gas CCUS alone; all
  technologies.

## Assumptions

- **Weather**: 41 years (1985-2025) of atlite REPD fleet output, national CF = fleet output /
  fleet nameplate. 41-year mean CF: solar 12.0% (derated by 11/12 to 11.0%), onshore 37.4%,
  offshore 51.7%.
- **Demand**: FES 2025 Holistic Transition 2050 GB profile (567 TWh, peak 99.8 GW), the same
  shape in every weather year. There is no temperature coupling, so cold, still winter weeks
  are under-stressed.
- **Costs** (`costs.py`): real 2024 GBP, 2030 commissioning. Generation fixed costs are set so a
  MWh taken straight from the plant costs exactly the DESNZ Electricity Generation Costs 2025
  LCOE at the DESNZ load factor, so DESNZ / CEPA 2025 hurdle rates carry through. Nuclear
  GBP 140/MWh at 90% (from NAO HPC and SZC figures). Storage: battery GBP 120/kW + 120/kWh,
  86% RTE; LDES (pumped-hydro class) GBP 1,100/kW + 50/kWh, 40 years, 76% RTE; hydrogen chain
  of electrolyser (70%), salt cavern and turbine (55%).
- **Build ceilings**: onshore 40 GW, solar 100 GW, offshore uncapped (`cap_max=None` is a
  sensitivity).
- **Operation**: nuclear fully flexible; availability nuclear 0.90, gas CCUS 0.83, CCGT 0.93.
- **Not modelled**: interconnectors, demand flexibility, the network, cost trajectories beyond
  2030, a common discount rate.
- **Sensitivities** (`run_sweep.py --sens`): battery energy GBP 80 and 200/kWh, nuclear 120 and
  160 GBP/MWh, gas 40 and 150 p/therm, un-derated solar (12% CF), no build ceilings.

At firmness below 1 the LP puts a GBP 1/MWh tie-break on unserved energy so the barrier
solver does not stall. `model.extract` leaves it out of `cost_total_gbp_yr`. Sweeps run
before that fix carry it in `firm_lcoe`: at most unserved / delivered GBP/MWh, which is
0.11 at f = 0.90 and 0.01 at 0.99.

## Tests

```bash
python -m pytest tests/unit/test_firm_lcoe_figures.py tests/unit/test_firm_lcoe_costs.py \
                 tests/unit/test_firm_lcoe_model.py tests/unit/test_firm_lcoe_inputs.py
```

- `test_firm_lcoe_figures.py`: smoke check that `figures.py` writes all four PNGs from a
  synthetic results table, that the headline is hourly-firm at f = 1, and that cost
  components add up to the firm LCOE (also on the real results.csv when present).
- `test_firm_lcoe_costs.py`: the cost table reproduces the DESNZ figures.
- `test_firm_lcoe_model.py`: toy problems with optima known by hand (skips without gurobipy).
- `test_firm_lcoe_inputs.py`: CF and demand statistics (skips until `inputs.py --build` has run).
