# Layer 3: modules

Up: {doc}`../subsystems/index`. Hands-on: {doc}`../notebooks/index`. Every module: {doc}`/reference/api/index`.

One page per package, for anyone changing the code. Each page lists the modules a rule runs and the helpers they
share, the functions to start reading from, and the conventions a change must keep. The full module index, generated
from the code, is in {doc}`/reference/api/index`.

| Page | Packages |
|---|---|
| {doc}`config` | `config/config_loader.py` |
| {doc}`network` | `scripts/network_build/`, `scripts/network_clustering/` |
| {doc}`demand` | `scripts/demand/` |
| {doc}`supply` | `scripts/renewables/`, `scripts/generators/` |
| {doc}`flexibility` | `scripts/storage/`, `scripts/hydrogen/` |
| {doc}`interconnectors` | `scripts/interconnectors/` |
| {doc}`dispatch` | `scripts/solve/` |
| {doc}`market` | `scripts/market/` |
| {doc}`after_the_solve` | `scripts/analysis/`, `scripts/consumer_bill/`, `scripts/public_ownership/` |
| {doc}`utilities` | `scripts/utilities/` |

## Conventions for every module

- A script run by a rule's `script:` directive must not use `from __future__` imports (a test enforces it).
- A script run as `python scripts/...` puts the repository root on `sys.path` before importing `scripts.*`.
- Read configuration only through `config/config_loader.py`; a code default must equal the base default.
- Log through `scripts/utilities/logging_config.py`. Type hints, and docstrings with Args and Returns.
- Units: MW, MWh, GBP; costs in the price year the configuration states.
- Editing a file a rule reads makes Snakemake rebuild everything downstream of it: change shared data and helpers
  deliberately, and check which outputs move.

```{toctree}
:maxdepth: 1

config
network
demand
supply
flexibility
interconnectors
dispatch
market
after_the_solve
utilities
```
