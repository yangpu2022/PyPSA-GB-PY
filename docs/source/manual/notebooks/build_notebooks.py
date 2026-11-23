"""Write and run the manual's notebooks (docs/source/manual/notebooks/*.ipynb).

The manual's notebooks are generated, never edited by hand: each one is defined below as a list of
Markdown and code cells, written with nbformat and executed with nbclient so that the committed
notebook carries its outputs (the docs build does not run notebooks: ``nbsphinx_execute = 'never'``
in docs/source/conf.py). They need no workflow outputs, no weather cutouts and no commercial solver:
only the repository, PyPSA and HiGHS (``highspy``). Each builds a small network or reads the
configuration, and calls the repository's own functions on it.

Usage, from the repository root::

    python docs/source/manual/notebooks/build_notebooks.py            # write and execute all
    python docs/source/manual/notebooks/build_notebooks.py --no-run   # write without executing
    python docs/source/manual/notebooks/build_notebooks.py --only electricity_buses

Re-run it after changing a function a notebook calls, and commit the notebooks it writes.
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Callable, Dict, List, Tuple

import nbformat
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]

logger = logging.getLogger("build_notebooks")

#: The first code cell of every notebook: put the repository root on ``sys.path`` and quieten the
#: libraries, so the notebook runs from its own folder in Jupyter as well as from this builder.
SETUP = '''\
import logging, sys, warnings
from pathlib import Path

ROOT = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / "Snakefile").exists())
for path in (ROOT, ROOT / "config"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
warnings.filterwarnings("ignore")
logging.getLogger("pypsa").setLevel(logging.ERROR)
logging.getLogger("linopy").setLevel(logging.ERROR)
logging.getLogger("scripts").setLevel(logging.WARNING)

import pandas as pd
pd.set_option("display.width", 120)'''

Cell = Tuple[str, str]  # ("md" | "code", source)


def config_layers() -> List[Cell]:
    """How a scenario's settings are assembled from the defaults, the overlays and the scenario."""
    return [
        ("md", """\
# Where a setting comes from

Layer 2: [Configuration](../subsystems/configuration.md). Layer 3: [config_loader](../modules/config.md).

Every run starts from a scenario id. The loader (`config/config_loader.py`) merges, in order, the base defaults
(`config/defaults/base.yaml` and `config/defaults/base/**`), the globals in `config/config.yaml`, the overlay for the
scenario's `method`, the overlay for its `targets.source`, the overlay for its `market.dispatch`, and finally the
scenario's own entry. This notebook asks the loader to explain one scenario, `Test_Market`, the default run."""),
        ("code", SETUP),
        ("code", """\
import config_loader

explained = config_loader.explain_scenario("Test_Market")
layers = explained["layers"]
print(f"{len(layers)} files, merged in this order:")
for i, layer in enumerate(layers, 1):
    print(f"{i:3d}. {layer}")"""),
        ("md", """\
The defaults are split by key path: `config/defaults/base/market/balancing.yaml` holds the keys under
`market.balancing`. The overlays only appear when the scenario declares the matching axis; `Test_Market` is a FES
scenario built by GSP blocks, so `method/gsp_block.yaml` and `source/FES.yaml` are in the list."""),
        ("code", """\
values = pd.DataFrame(explained["values"], columns=["key", "value", "set by"])
print(f"{len(values)} leaf settings")
values["set by"].value_counts().rename("settings").to_frame()"""),
        ("md", """\
Most settings come from the base defaults; the scenario itself sets only what makes it this scenario. The keys that
decide what kind of run it is:"""),
        ("code", """\
keys = ["targets.source", "targets.pathway", "method", "network_model", "modelled_year",
        "market.enabled", "solve.solver.name", "solve_period.start", "solve_period.end"]
values.set_index("key").reindex(keys).dropna(how="all")"""),
        ("md", """\
The same question from the command line, for one key:

```bash
python config/config_loader.py --explain Test_Market --path solve.solver.name
```

Two rules follow from this. Read the configuration only through the loader, never with `yaml.safe_load` on a
scenario file, because a scenario file alone is not the scenario. And when a script falls back to a default, the
fallback must equal the value in `config/defaults/base/`, because that is what every scenario that does not set the
key receives."""),
    ]


def electricity_buses() -> List[Cell]:
    """The three kinds of bus, and the rule that picks the GB electrical ones."""
    return [
        ("md", """\
# Electricity buses, the hydrogen bus and foreign buses

Layer 2: [After the solve](../subsystems/after_the_solve.md). Layer 3: [scripts/market](../modules/market.md).

A PyPSA-GB network has three kinds of bus:

- **GB electrical buses**: the transmission nodes (carrier `AC`, or `DC` for an offshore DC node), where demand,
  generators and storage connect;
- **the hydrogen bus** (carrier `H2`), joined to electrical buses by electrolyser and hydrogen-turbine links, and
  carrying the hydrogen offtake as a Load in MWh of hydrogen;
- **foreign buses**, one at the far end of each interconnector, named with `External` and carrying the foreign
  market as generators and loads.

Every demand total, demand-weighted price and bill counts only the first kind. The rule is one function,
`scripts.market.market_accounting._is_gb_electrical_bus`, and `tests/unit/test_electricity_buses.py` pins it."""),
        ("code", SETUP),
        ("code", """\
import pypsa
from scripts.market import market_accounting as ma

snapshots = pd.date_range("2035-01-01", periods=3, freq="h")
n = pypsa.Network()
n.set_snapshots(snapshots)
n.add("Bus", "north", carrier="AC", country="GB")
n.add("Bus", "south", carrier="AC", country="GB")
n.add("Bus", "offshore hub", carrier="DC", country="GB")
n.add("Bus", "H2", carrier="H2", country="")
n.add("Bus", "FR External", carrier="AC", country="FR")

n.add("Load", "north load", bus="north", p_set=pd.Series([100.0, 110.0, 120.0], index=snapshots))
n.add("Load", "south load", bus="south", p_set=50.0)
n.add("Load", "H2 offtake", bus="H2", p_set=30.0)
n.add("Load", "FR demand", bus="FR External", p_set=1000.0)
n.add("Link", "north electrolysis", bus0="north", bus1="H2", p_nom=40.0, efficiency=0.7)
n.add("Link", "IFA", bus0="south", bus1="FR External", p_nom=2000.0)

buses = n.buses[["carrier", "country"]].copy()
buses["GB electrical"] = ma._is_gb_electrical_bus(n.buses)
buses"""),
        ("md", """\
The rule reads two columns and the name:

1. the carrier, trimmed and lower-cased, must be `ac`, `dc` or empty (`ELECTRICAL_BUS_CARRIERS`);
2. the name must not contain `External`;
3. where there is a `country` column, it must be `GB` or empty.

An empty carrier counts as electrical because older networks leave it blank; an empty country counts as GB because
only the hydrogen bus is blank, and its carrier already excludes it."""),
        ("code", """\
print(sorted(ma.ELECTRICAL_BUS_CARRIERS))
edge_cases = pd.DataFrame({"carrier": [" Ac ", None, "heat", "AC"], "country": ["GB", None, "GB", ""]},
                          index=["spaced", "blank", "heat bus", "IE External"])
edge_cases.assign(**{"GB electrical": ma._is_gb_electrical_bus(edge_cases)})"""),
        ("md", """\
## GB electricity demand

`_gb_electricity_demand_mwh` applies the rule: loads on GB electrical buses, plus consumer flexibility on them, plus
the electricity that conversion links (electrolysers) draw from a GB electrical bus into a non-electrical one. The
hydrogen offtake is MWh of hydrogen, not electricity, and the French load is France's."""),
        ("code", """\
n.links_t.p0 = pd.DataFrame({"north electrolysis": [40.0, 0.0, 20.0], "IFA": [500.0, -300.0, 0.0]},
                            index=snapshots)
hours = n.snapshot_weightings.generators
gb = ma._gb_electricity_demand_mwh(n, hours)
every_load = n.loads_t.p_set.reindex(columns=n.loads.index).fillna(n.loads.p_set).sum().sum()
print(f"GB electricity demand: {gb:,.0f} MWh")
print(f"every Load in the network: {every_load:,.0f} MWh")"""),
        ("md", """\
330 MWh in the north and 150 MWh in the south, plus 60 MWh into the electrolyser: 540 MWh. Summing every Load
instead would add 90 MWh of hydrogen and 3,000 MWh of French demand.

The bill reads the same rule from a saved network file, without loading it into PyPSA
(`scripts.consumer_bill.project_future_bill._electrical_buses`):"""),
        ("code", """\
import tempfile
import xarray as xr
from scripts.consumer_bill.project_future_bill import _electrical_buses

with tempfile.TemporaryDirectory() as folder:
    path = Path(folder) / "network.nc"
    n.export_to_netcdf(path)
    with xr.open_dataset(path) as ds:
        print(sorted(_electrical_buses(ds)))"""),
        ("md", """\
**When you add a bus**, give it a carrier that says what it carries. A new GB electrical node needs `AC` or `DC`; a
new foreign node needs `External` in its name (the interconnector build names them so, see
`scripts/interconnectors/map_to_buses.py`); a bus for another energy carrier needs that carrier. A bus that breaks
these conventions moves demand in or out of every total the market and the bill report."""),
    ]


def two_stage_market() -> List[Cell]:
    """The wholesale copperplate and the network-constrained redispatch on a three-bus toy."""
    return [
        ("md", """\
# Two stages on three buses

Layer 2: [Dispatch](../subsystems/dispatch.md). Layer 3: [scripts/market](../modules/market.md).

The two-stage market first clears a GB wholesale market with no internal network limits (Stage 1), then moves units
off those positions until the dispatch fits the network (Stage 2, the balancing mechanism). This notebook runs the
idea on three GB buses and one foreign bus, using the model's own copperplate: `scripts.market.copperplate`
collapses the synchronous mainland onto one hub bus and writes the results back onto the original network. It needs
only PyPSA and HiGHS.

The toy has cheap wind in the north, demand in the south, and a line between them that is too small for the wind."""),
        ("code", SETUP),
        ("code", """\
import pypsa
from scripts.market.copperplate import collapse_mainland, expand_results

def toy_network():
    snapshots = pd.date_range("2035-01-01", periods=4, freq="h")
    n = pypsa.Network()
    n.set_snapshots(snapshots)
    for name, x in [("north", 0.0), ("middle", 1.0), ("south", 2.0)]:
        n.add("Bus", name, carrier="AC", country="GB", v_nom=400.0, x=x, y=0.0)
    n.add("Bus", "NO External", carrier="AC", country="NO", v_nom=400.0)
    n.add("Line", "north-middle", bus0="north", bus1="middle", x=0.1, r=0.01, s_nom=600.0)
    n.add("Line", "middle-south", bus0="middle", bus1="south", x=0.1, r=0.01, s_nom=600.0)
    n.add("Line", "north-south", bus0="north", bus1="south", x=0.2, r=0.02, s_nom=300.0)
    wind = pd.Series([0.9, 0.8, 0.5, 0.2], index=snapshots)
    n.add("Generator", "north wind", bus="north", carrier="wind", p_nom=1500.0, p_max_pu=wind, marginal_cost=0.0)
    n.add("Generator", "south gas", bus="south", carrier="gas", p_nom=1500.0, marginal_cost=80.0)
    n.add("Generator", "middle gas", bus="middle", carrier="gas", p_nom=500.0, marginal_cost=95.0)
    n.add("Load", "south demand", bus="south", p_set=pd.Series([1000.0, 1100.0, 1200.0, 1100.0], index=snapshots))
    n.add("Generator", "Norway", bus="NO External", carrier="EU_market", p_nom=700.0, marginal_cost=60.0)
    n.add("Link", "NSL", bus0="NO External", bus1="north", p_nom=700.0, p_min_pu=-1.0)
    return n

network = toy_network()
network.buses[["carrier", "country", "x"]]"""),
        ("md", """\
## Stage 1: the copperplate

`collapse_mainland` finds the largest synchronous sub-network among the non-External buses, adds a hub bus
`GB_mainland`, moves every generator and load on the mainland to it, and removes the mainland's lines. The foreign
bus and the interconnector keep their identity and their limit, so the collapse is exact: with unlimited internal
ratings every mainland bus would share one price anyway."""),
        ("code", """\
collapsed, mapping = collapse_mainland(network)
print("hub:", mapping.hub)
print("mainland buses:", mapping.mainland_buses)
print("lines removed:", mapping.removed_lines)
collapsed.buses[["carrier", "country"]]"""),
        ("code", """\
collapsed.optimize(solver_name="highs", solver_options={"output_flag": False})
expand_results(network, collapsed, mapping)
positions = network.generators_t.p.copy()
wholesale_cost = (positions * network.generators.marginal_cost).sum().sum()
print(f"Stage 1 cost: {wholesale_cost:,.0f} GBP")
print("GB price (GBP/MWh), one value per hour on every mainland bus:")
network.buses_t.marginal_price.round(1) + 0.0"""),
        ("md", """\
The schedule uses all the wind. On the real network it cannot all reach the south: see how loaded the lines would
be if the schedule were flowed."""),
        ("code", """\
flowed = toy_network()
flowed.generators_t.p_set = positions
flowed.links_t.p_set = network.links_t.p0
flowed.lpf()
(flowed.lines_t.p0.abs() / flowed.lines.s_nom).round(2).rename(columns=lambda c: f"{c} loading")"""),
        ("md", """\
Loadings above 1 are what Stage 2 has to remove.

## Stage 2: redispatch on the network

Here Stage 2 is the network-constrained least-cost dispatch, and the redispatch is the difference from the Stage 1
positions. The model's balancing stage (`scripts/market/solve_balancing.py`) does more: it anchors every unit to its
Stage 1 position and prices each move at the unit's offer (turn up) or bid (turn down) rather than its marginal cost,
with bids for supported plant set by what the support scheme pays (`scripts/market/cfd_bm_bids.py`). The cost here is
therefore the resource cost of the constraint, not a bid-offer cost."""),
        ("code", """\
constrained = toy_network()
constrained.optimize(solver_name="highs", solver_options={"output_flag": False})
physical = constrained.generators_t.p
redispatch = (physical - positions).round(1)
print("Redispatch, MW (positive: turned up; negative: turned down)")
redispatch"""),
        ("code", """\
constrained_cost = (physical * constrained.generators.marginal_cost).sum().sum()
summary = pd.Series({
    "Stage 1 cost (GBP)": wholesale_cost,
    "network-constrained cost (GBP)": constrained_cost,
    "constraint cost (GBP)": constrained_cost - wholesale_cost,
    "wind turned down (MWh)": -redispatch["north wind"].clip(upper=0).sum(),
}).round(0)
summary.to_frame("toy")"""),
        ("code", """\
print("Nodal prices after redispatch (GBP/MWh): the north is priced by what it can export")
constrained.buses_t.marginal_price[["north", "middle", "south"]].round(1) + 0.0"""),
        ("md", """\
The pattern is the one the GB studies report at scale: wind in the north turned down, gas in the south turned up,
and a constraint cost that the single GB price of Stage 1 does not show. See [Dispatch](../../model/dispatch/index.md) for the
method, and [tutorial 5](../../tutorials/5-two-stage-market-2030.ipynb) for a real week."""),
    ]


NOTEBOOKS: Dict[str, Callable[[], List[Cell]]] = {
    "config_layers": config_layers,
    "electricity_buses": electricity_buses,
    "two_stage_market": two_stage_market,
}


def make_notebook(cells: List[Cell]) -> nbformat.NotebookNode:
    """Build a notebook from ``(kind, source)`` cells.

    Args:
        cells: ``("md", text)`` or ``("code", source)`` pairs, in order.

    Returns:
        The notebook, with the python3 kernel set.
    """
    nb = new_notebook()
    nb.cells = [new_markdown_cell(src) if kind == "md" else new_code_cell(src) for kind, src in cells]
    nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
    nb.metadata["language_info"] = {"name": "python"}
    return nb


def execute(nb: nbformat.NotebookNode, timeout: int = 600) -> None:
    """Run every cell in place, from this folder, stopping at the first error.

    Args:
        nb: the notebook to run.
        timeout: seconds allowed per cell.
    """
    from nbclient import NotebookClient

    NotebookClient(nb, timeout=timeout, kernel_name="python3",
                   resources={"metadata": {"path": str(HERE)}}).execute()


def build(names: List[str], run: bool = True) -> List[Path]:
    """Write (and run) the named notebooks.

    Args:
        names: keys of ``NOTEBOOKS``.
        run: execute the notebooks so they carry outputs.

    Returns:
        The paths written.
    """
    written = []
    for name in names:
        nb = make_notebook(NOTEBOOKS[name]())
        if run:
            logger.info("running %s", name)
            execute(nb)
        path = HERE / f"{name}.ipynb"
        nbformat.write(nb, path)
        logger.info("wrote %s", path.relative_to(REPO_ROOT))
        written.append(path)
    return written


def main(argv=None) -> int:
    """Command line entry point."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--only", nargs="+", choices=sorted(NOTEBOOKS), help="build only these notebooks")
    parser.add_argument("--no-run", action="store_true", help="write the notebooks without executing them")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    build(args.only or list(NOTEBOOKS), run=not args.no_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
