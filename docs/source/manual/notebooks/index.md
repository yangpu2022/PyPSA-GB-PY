# Notebooks

Up: {doc}`../index`.

Three short notebooks that run the ideas of the manual on small networks, calling the model's own functions. They
need no workflow outputs, no weather cutouts and no commercial solver: only the `pypsa-gb` environment (PyPSA and
HiGHS). The pages below keep their outputs, so they can be read without running anything.

| Notebook | Shows | Layer 2 | Layer 3 |
|---|---|---|---|
| {doc}`config_layers` | which files make up a scenario's settings, and which file set each value | {doc}`../subsystems/configuration` | {doc}`../modules/config` |
| {doc}`electricity_buses` | the three kinds of bus, the rule that picks GB electrical buses, and GB electricity demand | {doc}`../subsystems/after_the_solve` | {doc}`../modules/market` |
| {doc}`two_stage_market` | the wholesale copperplate and the network-constrained redispatch on three buses | {doc}`../subsystems/dispatch` | {doc}`../modules/market` |

The notebooks are generated: edit `docs/source/manual/notebooks/build_notebooks.py`, not the `.ipynb` files, and
rebuild them from the repository root with

```bash
python docs/source/manual/notebooks/build_notebooks.py
```

which writes and runs every notebook (`--only <name>` for one, `--no-run` to write without running). Rebuild them
after changing a function they call, and commit the notebooks it writes.

```{toctree}
:maxdepth: 1

config_layers
electricity_buses
two_stage_market
```
