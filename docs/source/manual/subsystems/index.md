# Layer 2: the parts of the model

Up: {doc}`../overview`. Down: {doc}`../modules/index`.

One page per part, in the order a run uses them. Each page says what the part does, which rules run it and what they
write, the settings that change it, what it hands to the next part, and where to read further.

| Part | Does | Rules in |
|---|---|---|
| {doc}`configuration` | turns a scenario id into the merged settings every rule reads | `config/config_loader.py` |
| {doc}`network` | builds the buses and branches, and the limits they put on the solve | `rules/network_build.smk`, `rules/network_clustering.smk` |
| {doc}`demand` | places hourly demand and consumer flexibility on the buses | `rules/demand.smk` |
| {doc}`supply` | adds renewable and thermal generators, their availability and marginal costs | `rules/renewables.smk`, `rules/generators.smk` |
| {doc}`flexibility` | adds storage and the hydrogen system | `rules/storage.smk`, `rules/hydrogen.smk` |
| {doc}`interconnectors` | adds the cables and a foreign market at each far end | `rules/interconnectors.smk` |
| {doc}`dispatch` | solves the finished network: one solve, or wholesale then balancing | `rules/solve.smk`, `rules/market.smk` |
| {doc}`after_the_solve` | results, market accounts, validation, bills | `rules/analysis.smk`, `rules/market.smk`, `rules/consumer_bill.smk`, `rules/public_ownership.smk` |

```{toctree}
:maxdepth: 1

configuration
network
demand
supply
flexibility
interconnectors
dispatch
after_the_solve
```
