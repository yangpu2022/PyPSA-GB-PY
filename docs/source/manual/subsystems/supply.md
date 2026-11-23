# Supply

Up: {doc}`index`. Down: {doc}`../modules/supply`. Full chapter: {doc}`/model/generation/index`.

## What it does

Adds every generator: renewables first, with hourly availability from the weather year, then thermal plant, then a
check and finalise step, then every generator's marginal cost.

| Rule | Script | Writes |
|---|---|---|
| `generate_renewable_profiles` and the marine and hydro profile rules | `scripts/renewables/` | capacity-factor profiles from atlite weather cutouts |
| `add_renewables_to_network` | `scripts/generators/integrate_renewable_generators.py` | `..._demand_renewables.pkl` |
| `add_thermal_generators_to_network` | `scripts/generators/integrate_thermal_generators.py` | `..._renewables_thermal.pkl` |
| `finalize_generator_integration` | `scripts/generators/finalize_generator_integration.py` | `..._thermal_generators.pkl`, with a load-shedding generator at every demand bus |
| `apply_marginal_costs_to_network` | `scripts/generators/apply_marginal_costs.py` | `..._generators_costs.pkl` and `{scenario}_marginal_costs_breakdown.csv` |

## Where the fleet comes from

| `method` | Capacity | Placement |
|---|---|---|
| `historical` | DUKES (thermal), REPD (renewables) | each site at its own location |
| `gsp_block` | FES building blocks by GSP and technology | at the GSP; `Direct` rows spread in their licence area |
| `brownfield` | CP30 national and regional totals | named projects first, then FES rows for the residual |

## Settings

`renewables.*` (aggregation, performance factors, hydro), `thermal.*` (availability, outages, ramping),
`marginal_costs.*` (fuel and carbon prices, future costs, calibration), `fleet.*`, and `solve.voll` for load shedding.

## What a change must respect

Site coordinates are WGS84 and buses OSGB36: convert before matching. Support labels (CfD round, RO) set on
generators here decide their bids in the balancing stage ({doc}`dispatch`).

## Hands on

A network with demand and generators, to which {doc}`flexibility` adds storage and hydrogen.
