# Firm LCOE of renewables plus storage vs nuclear and gas CCUS — weather-year LP design

Date: 2026-11-18. Branch: gap-demand-dispatch. Status: approved 2026-11-18 (11% solar central; market-evidence section added).
Code target: `scripts/analysis/firm_lcoe/`. Outputs: `resources/analysis/firm_lcoe/`.

## Question

What does it cost per MWh delivered to meet the GB demand profile with wind and solar plus
storage, at a stated firmness, and how does that compare with nuclear and with gas CCUS
asked to meet the same profile? The published LCOEs (DESNZ Electricity Generation Costs
2025) price a MWh at the plant gate; this analysis prices the *service* of meeting demand,
so overbuild, curtailment, storage capex, round-trip losses and cycle counts are all
outputs of one optimisation rather than assumptions.

## What exists and what is used

* 41 weather years (1985-2025) of site-level hourly output for solar PV (1,321 sites),
  onshore wind (687) and offshore wind (66) in `resources/renewable/profiles/<tech>_<wy>.csv`
  (MW, REPD fleet, atlite). National fleet capacity factor = row sum / fleet nameplate from
  `resources/renewable/<tech>_sites.csv` (19 offshore names fall back to series maximum).
  41-year mean CF: solar 12.0%, onshore 37.4%, offshore 51.7%, against DESNZ 2025 net load
  factors of 12% / 37% / 49%. Wind is left as modelled. Solar is derated by 11/12 so the
  41-year mean is 11.0% (approved 2026-11-18): DESNZ 2025's 12% is a 52 MW new-build
  reference plant (DESNZ 2023 used 11%), while DUKES fleet-wide load factors were 9.2% in
  2024 and 11.1% in 2025, the sunniest year since 2001, and atlite carries no soiling,
  degradation, clipping or availability losses. The un-derated 12% series is a sensitivity.
* Demand: `resources/demand/HT50_w<wy>_base_profile.csv`, FES 2025 Holistic Transition 2050,
  29 buses summed to GB. The file is identical for every weather year (567.4 TWh, peak
  99.8 GW, minimum 38.1 GW), i.e. demand is a fixed 2050 shape with no temperature
  coupling. This is a stated limitation: cold, still winter weeks are under-stressed.
  A temperature-driven demand (`scripts/gap/demand_weather_model.py`) is a follow-up, not
  part of this build.
* Solver: Gurobi 13 via `gurobipy` in the system Python 3.12 (no PyPSA in that
  environment). The LP is written directly in the gurobipy matrix API; no new packages.
* Machine: 31.5 GB RAM, 14 logical cores, about 4 GB free at design time.

## Model

Single GB node, greenfield, joint capacity expansion over all selected weather years
with each year's storage cycle closed on itself (no state carried between years).

Decision variables
* Capacity (MW): solar, onshore, offshore, nuclear, gas CCUS, unabated CCGT (backup case
  only). Storage: battery power and energy (MW, MWh; duration free), LDES power and energy,
  hydrogen electrolyser (MW_e in), hydrogen turbine (MW_e out), hydrogen cavern (MWh_H2).
* Per period: dispatch of each dispatchable plant, VRE curtailment (one aggregate variable),
  charge / discharge / state of charge per store, unserved energy.

Constraints
* Energy balance every period.
* VRE output ≤ capacity × national CF; dispatchables ≤ capacity × availability
  (nuclear 0.90, gas CCUS 0.83 per DESNZ Annex A, CCGT 0.93).
* Storage: SOC dynamics with round-trip loss split evenly over charge and discharge,
  SOC ≤ energy capacity, flows ≤ power capacity, cyclic within each weather year.
* Firmness: per weather year, unserved energy ≤ (1 − f) × that year's demand. Unserved
  carries no penalty cost; f is swept.
* Backup case: CCGT energy ≤ 5% of each year's demand (Clean Power 2030 convention).
* Nuclear is fully flexible down to zero (favourable to nuclear; a must-run floor is a
  sensitivity switch, default off).
* Build-out ceilings (added after the smoke run of 2026-11-18, which returned 176 GW onshore,
  280 GW solar and no offshore wind): onshore ≤ 40 GW, solar ≤ 100 GW, offshore free, at the
  top of the FES 2025 / CCC Seventh Carbon Budget 2050 ranges. The unconstrained solve is a
  sensitivity (`cap_max=None`).
* Hourly top-up (added 2026-11-18): 3-hour blocks smooth the demand peak from 99.8 to 97.2 GW,
  so a block solution at f = 1.0 leaves hourly unserved energy. For every 100 %-firmness solve
  the block capacities become lower bounds in a per-weather-year hourly capacity LP; the
  element-wise maximum over years is a conservative hourly-feasible capacity set, and
  `firm_lcoe_hourly` = (block cost + top-up fixed cost) / delivered is the headline figure.
  For f < 1 the hourly re-check only measures unserved energy and LOLE.

Objective: average annual cost = Σ annualised fixed cost × capacity + Σ variable cost × energy,
divided by the number of weather years.

Metric: firm LCOE (£/MWh delivered) = objective / mean annual delivered energy, where
delivered = demand − unserved. Reported alongside: capacities, TWh by source, curtailment
share, storage cycles per year (discharged energy / energy capacity), implied LOLE hours,
and the cost decomposition (generation, overbuild curtailed, battery, LDES, hydrogen,
backup gas).

Temporal resolution: 3-hour block averages over all 41 years by default (119,720 periods,
about 2 M variables), chosen for the 4 GB free RAM. Options `--step 1` (hourly) and
`--years` (subset) exist. Feb 29 is dropped so every year is 8,760 h. After each
capacity solve a fixed-capacity hourly dispatch per year re-checks unserved energy and
reports the hourly LOLE; this catches peaks the 3-hour blocks smooth away.

## Cost assumptions (real 2024 £, 2030 commissioning)

Principle: every generation input is a published DESNZ 2025 LCOE and its load factor, so
a MWh taken directly from the plant costs exactly the DESNZ figure; curtailment and
storage then raise it. Annualised fixed cost AFC = (LCOE − VOM) × 8760 × LF / 1000 in
£/kW-yr. Technology-specific hurdle rates are therefore inherited from DESNZ (CEPA 2025:
7.6% solar and onshore, 8.9% offshore and gas, 10.1% novel LDES and hydrogen).

| Technology | Source figure | Derived model input |
|---|---|---|
| Solar PV | LCOE £60, LF 12% | AFC £63/kW-yr, VOM 0; at the modelled 11% CF the direct LCOE is £65 |
| Onshore wind | LCOE £58, LF 37% | AFC £188/kW-yr, VOM 0 |
| Offshore wind (fixed) | LCOE £103, LF 49% | AFC £442/kW-yr, VOM 0 |
| Nuclear | no DESNZ figure; HPC £129-133, SZC £133-155 (NAO) → central £140 at 90% LF, range 120-160 | AFC £1,009/kW-yr, VOM+fuel £12/MWh |
| Gas CCUS | LCOE £105 at 88% LF and £181 at 30% LF (DESNZ 2025) | AFC £303/kW-yr, VOM £66/MWh (fuel, carbon, T&S, O&M) |
| Unabated CCGT (backup) | LCOE £111 at 93%, £424 at 5% (DESNZ 2025) | AFC £145/kW-yr; VOM = 5 + 0.632 × gas p/therm + 0.339 × carbon £/t (71 p/th, £120/t → £91/MWh) |
| Battery | power £120/kW, energy £120/kWh, 15 yr, 8.9%, FOM 2.5% of capex, RTE 86% | £17.8/kW-yr + £17.8/kWh-yr |
| LDES (pumped-hydro class) | power £1,100/kW, energy £50/kWh, 40 yr, 8.9%, FOM 1%, RTE 76% | £112/kW-yr + £5.1/kWh-yr |
| Hydrogen chain | electrolyser £1,000/kW_e 70% eff, 25 yr, 10.1%, FOM 3%; cavern £0.6/kWh_H2 30 yr 8.9%; turbine £887/kW_e 55% eff, 25 yr, 10.1%, FOM £14/kW-yr, VOM £2 | £141/kW-yr; £0.07/kWh-yr; £112/kW-yr |

Storage figures are a synthesis of the costs module already in
`scripts/analysis/storage_value/costs.py` (same sources: NREL 2025, BNEF 2025, LCP Delta /
Regen for DESNZ 2024, Royal Society 2023, Coire Glas and Highview disclosures); the battery
energy cost is taken lower than that module's 2 h figure (£280/kWh) to reflect BNEF's
Dec 2025 Europe turnkey price (~£136/kWh) and is varied in the sensitivity.

Sensitivities (each a separate solve): battery energy £80 / 120 / 200 per kWh; nuclear
LCOE 120 / 140 / 160; gas price for the backup case 40 / 71 / 150 p/therm; solar CF at
the raw 12% instead of the derated 11%.

## Market evidence 2024-2025: what renewables and gas bid, vs the cost of shifting a MWh

Added 2026-11-18. The LP prices storage from capex and cycles; this section asks whether
the market as it stood in 2024 and 2025 actually offered storage that margin. Three
quantities are put side by side, all in £/MWh.

1. What renewables bid. Day-ahead: hours with negative N2EX price (176 in 2024, 177 in
   2025, from `scripts/analysis/bidding_behaviour/data/price_monthly.csv`), the price floor
   reached, and wind and solar output in those hours relative to positive-price hours
   (`tech_vs_price.csv`: wind 1.6x, solar 2.2x). Balancing mechanism: the median turn-down
   bid submitted by representative plants (`/gb/elexon/physical/bod` via the Modo REST
   client already in `scripts/analysis/bidding_behaviour/fetch_modo.py`), sampled over the
   first seven days of every month of 2024 and 2025 to bound request volume. Plants: the
   seven in `plants.py` (London Array ROC, Hornsea One CfD, Whitelee ROC, Larks Green
   solar, Drax, Pembroke CCGT, Pillswood battery) plus further CCGTs and offshore wind
   farms where the endpoint returns data. The bid is read against the subsidy arithmetic:
   a ROC plant loses ROC value (about £64 per ROC x banding) when curtailed, an AR1-3 CfD
   plant loses its strike-minus-reference top-up, an AR4+ plant loses nothing in a
   negative-price hour.
2. What gas bids. Monthly short-run marginal cost of a CCGT from NBP day-ahead gas, UK ETS
   allowance price and the £18/t Carbon Price Support (2024 and 2025 monthly averages,
   sources recorded in the README), against Pembroke's median BM bid and offer and against
   the day-ahead price in hours where gas is marginal (CCGT output above its annual median).
3. What storage needs. The levelised cost of shifting one MWh through each store in the LP
   cost table (battery, LDES, hydrogen), as a curve against cycles per year:
   AFC_power/(cycles x duration) + AFC_energy/cycles + charging price / RTE. The LP's own
   realised cycles and durations are marked on the curve, so the number the system optimum
   implies and the number the 2024-25 market paid are read off the same axis. The market
   side is the mean daily day-ahead spread (£60.5 in 2024, £68.2 in 2025 from
   `price_spread_monthly.csv`), the spread between the median renewable turn-down bid and
   the gas SRMC in the same months, and realised GB battery revenue per MW-yr from
   `bess_revenue_stack_monthly.csv`.

Code: `market_bids.py` in the same folder (pull, cache under
`resources/analysis/firm_lcoe/inputs/market/`, aggregate to `market_bids_2024_25.csv`).
The report gets one tab and the workbook one sheet for this section.

## Cases

| Case | Technologies allowed | Firmness sweep |
|---|---|---|
| RE + storage | solar, onshore, offshore, battery, LDES, hydrogen | 0.90, 0.95, 0.99, 0.999, 1.0 |
| RE + storage + 5% gas | as above plus unabated CCGT capped at 5% energy | 1.0 |
| Nuclear (+ storage) | nuclear, battery, LDES | 0.99, 1.0 |
| Gas CCUS | gas CCUS only | 1.0 |
| All technologies | everything, no energy cap on gas CCUS, no unabated gas | 1.0 |

The "all technologies" case is the system optimum and shows how much each technology the
optimiser chooses when nothing is forced; the single-family cases are the Idel-style
comparison the question asked for.

## Code layout

```
scripts/analysis/firm_lcoe/
  inputs.py     national CF (41 years, 3 techs) and demand; caches to
                resources/analysis/firm_lcoe/inputs/national_cf.parquet and demand.parquet
  costs.py      the table above as data, with the AFC derivations as functions
  model.py      build_lp(data, case, firmness, options) -> gurobipy Model; extract(model) -> dict
  run_sweep.py  CLI: --cases --firmness --step --years --sens; writes results.csv one row per solve
  market_bids.py 2024-25 bids (DA prices, BM bid-offer, BESS revenue) -> market_bids_2024_25.csv
  report.py     ONE workbook (firm_lcoe.xlsx) + ONE tabbed self-contained HTML with vanilla SVG
                (firm_lcoe_report.html), following the repo's analysis-consolidation convention
```

Each unit is independently testable: `inputs.py` is checked against the CF statistics
above; `costs.py` reproduces the DESNZ LCOEs at the DESNZ load factors; `model.py` is
checked on a two-day toy series where the optimum is known by hand.

## Outputs

* `resources/analysis/firm_lcoe/results.csv` — one row per (case, firmness, sensitivity):
  firm LCOE, capacities, TWh flows, curtailment share, cycles per year per store, LOLE
  hours from the hourly re-check, cost components.
* `firm_lcoe.xlsx` (README sheet first) and `firm_lcoe_report.html` with: cost vs firmness
  curves per case; stacked cost decomposition per point; capacity mix; storage duration and
  cycles. A README.md sidecar lists inputs, assumptions and the git commit.

## Out of scope (follow-ups, not built here)

Temperature-driven demand per weather year; interconnectors and demand flexibility;
2050 cost trajectory; a common discount rate across technologies; spatial detail.
