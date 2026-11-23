# Layer 1: the model on one page

Up: {doc}`index`. Down: {doc}`subsystems/index`.

PyPSA-GB answers one kind of question: given a Great Britain electricity system in some year, built from published
data or from a NESO pathway, how is it dispatched hour by hour on its transmission network, and what does that cost?
It does this in four steps, each run by [Snakemake](https://snakemake.readthedocs.io) rules that call Python scripts.

```{mermaid}
flowchart LR
    C["1. Configure<br/>scenario id → merged settings"] --> B["2. Build<br/>network, demand, supply,<br/>flexibility, interconnectors"]
    B --> D["3. Dispatch<br/>single solve, or<br/>wholesale then balancing"]
    D --> A["4. Account<br/>results, market accounts,<br/>validation, bill"]
```

1. **Configure.** A run names a scenario. The loader (`config/config_loader.py`) merges the scenario over layered
   defaults and hands every rule the result. Two declarations decide most of what follows: `targets` (where the
   numbers come from: `historical`, `CP30` or `FES`) and `method` (how the fleet is built: `historical`, `brownfield`
   or `gsp_block`). {doc}`subsystems/configuration`.
2. **Build.** One PyPSA network per scenario, grown in a fixed order: topology, demand, renewables, thermal plant,
   marginal costs, storage, hydrogen, interconnectors, then optional clustering. Each step reads the previous step's
   network and writes a new file with a longer name. The finished network is `resources/network/{scenario}.nc`.
   {doc}`subsystems/network`, {doc}`subsystems/demand`, {doc}`subsystems/supply`, {doc}`subsystems/flexibility`,
   {doc}`subsystems/interconnectors`.
3. **Dispatch.** Either one least-cost optimisation with every network limit in force, or a two-stage market: Stage 1
   clears a GB wholesale market with no internal limits, and Stage 2, the balancing mechanism, moves units off those
   positions until the dispatch fits the network. The cost of those moves is the constraint cost.
   {doc}`subsystems/dispatch`.
4. **Account.** Results tables and dashboards, the market accounts of a two-stage run, checks against outturn and
   published targets, and (for market years) the household bill and public-ownership layers. None of these changes a
   solved network or triggers a solve. {doc}`subsystems/after_the_solve`.

## What is in a network

Everything the model represents is a PyPSA component on a bus.

| Thing | PyPSA component | Built by |
|---|---|---|
| Transmission node | `Bus` (carrier `AC`; `DC` for offshore DC nodes) | network build |
| Overhead line, cable | `Line` | network build |
| Transformer | `Transformer` | network build |
| HVDC link inside GB | `Link` | network build |
| Demand | `Load` on a GB electrical bus | demand |
| Consumer flexibility (EVs, heat, demand response) | `StorageUnit` on a demand bus, carved out of the `Load` | demand |
| Wind, solar, hydro, marine, thermal plant | `Generator` with availability `p_max_pu` and a marginal cost | supply |
| Load shedding | `Generator` at every demand bus, priced at the value of lost load (`solve.voll`) | supply (finalise step) |
| Batteries, pumped hydro, long-duration storage | `StorageUnit` | flexibility |
| Electrolysers, hydrogen turbines | `Link` between an electrical bus and the hydrogen bus | flexibility |
| Hydrogen storage and offtake | `Store` and `Load` on the hydrogen bus (carrier `H2`) | flexibility |
| Interconnector | `Link`s to a foreign bus (`External` in its name) with a price-taking foreign market on it | interconnectors |

So a network holds three kinds of bus: GB electrical buses, the hydrogen bus, and foreign buses. Demand totals,
prices and bills count only the first kind ({doc}`notebooks/electricity_buses`).

## Three choices that change everything

| Choice | Setting | Options |
|---|---|---|
| The system | `targets`, `method`, `modelled_year` | a historical year; Clean Power 2030 (brownfield); a FES pathway and year (GSP blocks) |
| The network | `network_model` (and `network.clustering`) | `ETYS` (about 2,000 buses), `Reduced` (32), `Zonal` (17), or ETYS clustered |
| The dispatch | `market.enabled`, `market.dispatch` | single solve; two-stage market; `central` dispatch overlay |

The weather year (`renewables_year`) and the demand-shape year (`demand_year`) are chosen separately from the modelled
year, and `solve_period` limits a run to part of the year.

## Where things live

| Folder | Holds |
|---|---|
| `config/` | the settings: defaults, scenarios, studies, and the loader |
| `rules/` | Snakemake rules, one file per area |
| `scripts/` | the Python the rules run, one package per area ({doc}`modules/index`) |
| `data/` | tracked input data |
| `resources/` | everything a run builds: networks, results, analyses (not tracked) |
| `logs/` | rule logs, by area |
| `docs/source/` | this documentation |
| `tests/` | the pytest suite |

The default run, `Test_Market`, is six hours of 2035 on the Reduced network, cleared as a two-stage market:

```bash
snakemake -n          # see what it would run
snakemake --cores 4   # run it
```

Next: {doc}`subsystems/index`.
