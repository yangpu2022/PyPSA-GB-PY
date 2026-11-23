#!/usr/bin/env python3
"""
41-weather-year residual-demand / surplus duration curves for 2030 and 2040.

The policy-brief residual-demand figure has two kinds of panel:

* the weather-year-2010 panels, drawn by ``plot_rdc_combined.R::proc_bot`` from a
  whole-network PyPSA-GB dispatch (``HT30_disp_w2010`` / ``HT40_disp_w2010``), and
* the "41-weather-year mean" panels, drawn by ``plot_rdc_combined.R::proc_top``
  from ``resources/analysis/weatheryears/<ty>_wy<wy>_genmix.parquet``. Those
  parquets come from ``seasonal_storage_weatheryears.py``, a *single-node* LP with
  a different demand model (national temperature response) and national fleet
  capacity factors, so the two kinds of panel are not like for like.

This script computes the 41-year panels with the SAME residual accounting as the
2010 dispatch panel, applied to one network dispatch per weather year, and draws
them in the same format as the published panels. It can also re-run the published
single-node method on the genmix parquets, so the two can be compared side by side.

Residual accounting (identical to ``proc_bot``)
    demand   = sum of all generator output + storage-unit net output
               + hydrogen net electrical output (turbine p0 x efficiency - electrolysis p0)
    residual = demand - wind - solar - nuclear - must-run firm group
    residual demand  = sum of positive hourly residual  (TWh/yr)
    residual surplus = - sum of negative hourly residual (TWh/yr)
Generator classes are matched on component name with the same regular expressions
as ``plot_rdc_combined.R`` (``GEN_PATTERNS`` below).

Ensemble statistics (identical to ``proc_top``)
    each year's residual is sorted into a duration curve and interpolated onto 400
    points of "percentage of hours"; the panel shows the mean curve and the P10-P90
    band across years, and the annotated TWh values are the mean of the per-year
    residual demand and residual surplus.

Sources (``--source``)
    network  per weather year, the wholesale CSV triple
             ``resources/market/<scn>_wholesale_{dispatch,storage,links}.csv``
             (what the 2010 panel reads), or, failing that, the solved network
             ``resources/network/<scn>_solved.nc`` (needs pypsa). ``<scn>`` comes
             from ``--scenario-template``, e.g. ``HT{yy}_disp_w{wy}`` (default),
             ``HT{yy}_gap_w{wy}`` (gap-demand campaign, market off) or
             ``HT{yy}_esp_w{wy}`` (two-stage market campaign).
    screen   the single-node LP genmix parquets that the published 41-year panels
             were drawn from (reproduces the published numbers when they exist).
    both     run both and write a comparison.

Outputs (``--out``, default resources/analysis/rdc_weatheryear_ensemble/)
    rdc_wy_<source>_per_year.csv     one row per (target year, weather year)
    rdc_wy_<source>_curves.csv       mean / P10 / P90 duration curve per target year
    rdc_wy_summary.csv               ensemble means next to the published values
    rdc_wy_inputs.csv                every input file looked for, found or missing
    rdc_wy_<source>.png / .pdf       the two panels, in the published format

Usage
    python scripts/analysis/rdc_weatheryear_ensemble.py
    python scripts/analysis/rdc_weatheryear_ensemble.py --source both
    python scripts/analysis/rdc_weatheryear_ensemble.py \\
        --scenario-template "HT{yy}_gap_w{wy}" --source network
    # check only which inputs are present:
    python scripts/analysis/rdc_weatheryear_ensemble.py --inventory-only
"""

import argparse
import logging
import re
import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logger = logging.getLogger("rdc_weatheryear_ensemble")

TARGET_YEARS = (2030, 2040)
WEATHER_YEARS = tuple(range(1985, 2026))          # 41 ERA5 weather years
N_GRID = 400                                      # points on the duration curve (as proc_top)
H2_TURBINE_EFF = 0.50                             # as plot_rdc_combined.R / add_hydrogen_system.py

# Numbers printed on the published 41-weather-year panels (TWh/yr):
# (residual demand, residual surplus).
PUBLISHED = {2030: (60.1, 20.2), 2040: (69.9, 62.6)}

# --- residual accounting, mirrored from plot_rdc_combined.R -------------------
# Network (proc_bot): regexes on component names, first match wins.
GEN_PATTERNS = {
    "wind": r"wind_onshore|wind_offshore",
    "solar": r"solar_pv",
    "nuclear": r"nuclear",
    "firm": r"biomass|biogas|landfill_gas|sewage_gas|waste_to_energy|"
            r"advanced_biofuel|large_hydro|geothermal",
}
STO_PATTERNS = {"Battery": r"Battery", "Pumped hydro": r"Pumped[ _]Storage", "LAES": r"LAES"}
# Screen (proc_top): exact carrier columns of the genmix parquets.
SCREEN_VRE = ("wind_onshore", "wind_offshore", "solar_pv")
SCREEN_FIRM = ("nuclear", "biomass", "biogas", "landfill_gas", "sewage_gas",
               "waste_to_energy", "advanced_biofuel", "large_hydro", "geothermal")

# Published panel style (plot_rdc_combined.R::top_panel).
NAVY, DRED, DGRN = "#22305f", "#7a1f1f", "#1f5a2a"
RED_FILL, GREEN_FILL, BAND = "#d62728", "#2ca02c", "#737373"


# ============================================================================ #
# Core accounting
# ============================================================================ #
def classify(columns, patterns):
    """Label each column with the first pattern it matches.

    Args:
        columns: Component names.
        patterns: Ordered mapping label -> regular expression.

    Returns:
        List of labels, ``None`` where nothing matched.
    """
    out = []
    for c in columns:
        lab = None
        for k, pat in patterns.items():
            if re.search(pat, str(c)):
                lab = k
                break
        out.append(lab)
    return out


def network_residual(dispatch, storage, links, h2_turbine_eff=H2_TURBINE_EFF):
    """Hourly residual demand (MW) from one network dispatch, as ``proc_bot``.

    Args:
        dispatch: Generator output, MW (snapshots x generators).
        storage: Storage-unit net output, MW, discharge positive.
        links: Link ``p0``, MW (only ``electrolysis*`` and ``H2_turbine*`` are used).
        h2_turbine_eff: Electrical efficiency of the H2 turbines (p1 = eff x p0).

    Returns:
        DataFrame indexed like ``dispatch`` with columns demand, vre, firm,
        residual and one signed net column per storage technology (MW).
    """
    lab = classify(dispatch.columns, GEN_PATTERNS)
    g = {k: dispatch.loc[:, [c for c, l in zip(dispatch.columns, lab) if l == k]].sum(axis=1)
         for k in GEN_PATTERNS}
    ely = links.loc[:, [c for c in links.columns if str(c).startswith("electrolysis")]].sum(axis=1)
    h2t = links.loc[:, [c for c in links.columns if str(c).startswith("H2_turbine")]].sum(axis=1)
    h2_net = h2t * h2_turbine_eff - ely

    out = pd.DataFrame(index=dispatch.index)
    out["demand"] = dispatch.sum(axis=1) + storage.sum(axis=1) + h2_net
    out["vre"] = g["wind"] + g["solar"]
    out["firm"] = g["nuclear"] + g["firm"]
    out["residual"] = out["demand"] - out["vre"] - out["firm"]
    slab = classify(storage.columns, STO_PATTERNS)
    for k in STO_PATTERNS:
        cols = [c for c, l in zip(storage.columns, slab) if l == k]
        if cols:
            out[f"net_{k}"] = storage.loc[:, cols].sum(axis=1)
    out["net_Hydrogen"] = h2_net
    return out


def screen_residual(genmix):
    """Hourly residual demand (MW) from a single-node genmix parquet, as ``proc_top``.

    Args:
        genmix: Hourly table with a ``demand`` column and carrier columns (MW).

    Returns:
        Series of residual demand, MW.
    """
    vre = genmix.loc[:, [c for c in SCREEN_VRE if c in genmix.columns]].sum(axis=1)
    firm = genmix.loc[:, [c for c in SCREEN_FIRM if c in genmix.columns]].sum(axis=1)
    return genmix["demand"] - vre - firm


def year_metrics(residual_mw):
    """Annual residual demand, surplus and peak from an hourly residual.

    Args:
        residual_mw: Hourly residual demand, MW.

    Returns:
        Dict with rd_twh, su_twh, pk_gw and n_hours.
    """
    r = np.asarray(residual_mw, dtype=float)
    return {"rd_twh": float(np.clip(r, 0, None).sum()) / 1e6,
            "su_twh": float(-np.clip(r, None, 0).sum()) / 1e6,
            "pk_gw": float(r.max()) / 1e3,
            "n_hours": int(r.size)}


def duration_curve(residual_mw, n_grid=N_GRID):
    """Sorted residual (GW) on a fixed percentage-of-hours grid, as ``proc_top``.

    R's ``approx(..., rule = 2)`` clamps at the ends, which ``np.interp`` does too.

    Args:
        residual_mw: Hourly residual demand, MW.
        n_grid: Number of grid points between 0 and 100 %.

    Returns:
        Array of length ``n_grid``, GW, from highest to lowest.
    """
    r = np.sort(np.asarray(residual_mw, dtype=float) / 1e3)[::-1]
    p = 100 * (np.arange(1, r.size + 1) - 0.5) / r.size
    return np.interp(np.linspace(0, 100, n_grid), p, r)


def ensemble(curves):
    """Mean and P10/P90 across weather years (R ``quantile`` type 7 = numpy linear).

    Args:
        curves: 2-D array, weather years x grid points.

    Returns:
        DataFrame with pct, mean, lo (P10) and hi (P90).
    """
    m = np.vstack(curves)
    return pd.DataFrame({"pct": np.linspace(0, 100, m.shape[1]),
                         "mean": m.mean(axis=0),
                         "lo": np.quantile(m, 0.1, axis=0),
                         "hi": np.quantile(m, 0.9, axis=0)})


# ============================================================================ #
# Input readers
# ============================================================================ #
@dataclass
class Inventory:
    """Every input file looked for, so missing inputs can be named exactly."""
    rows: list = field(default_factory=list)

    def add(self, source, target_year, weather_year, path, found):
        self.rows.append({"source": source, "target_year": target_year,
                          "weather_year": weather_year, "path": str(path), "found": bool(found)})

    def frame(self):
        return pd.DataFrame(self.rows, columns=["source", "target_year", "weather_year",
                                                "path", "found"])


def scenario_name(template, ty, wy):
    """Fill a scenario template such as ``HT{yy}_disp_w{wy}``."""
    return template.format(yy=str(ty)[2:], ty=ty, wy=wy)


def _read_csv(path):
    df = pd.read_csv(path, index_col=0)
    return df.apply(pd.to_numeric, errors="coerce").fillna(0.0)


def read_network(market_dir, network_dir, scn, inv, ty, wy):
    """Load dispatch, storage and links for one scenario, CSV triple first.

    Args:
        market_dir: Directory holding ``<scn>_wholesale_*.csv``.
        network_dir: Directory holding ``<scn>_solved.nc``.
        scn: Scenario id.
        inv: Inventory to record the lookup in.
        ty: Target year (for the inventory).
        wy: Weather year (for the inventory).

    Returns:
        (dispatch, storage, links, h2_turbine_eff, source_path) or None if absent.
    """
    trio = [market_dir / f"{scn}_wholesale_{k}.csv" for k in ("dispatch", "storage", "links")]
    if all(p.exists() for p in trio):
        inv.add("network", ty, wy, trio[0], True)
        return (*[_read_csv(p) for p in trio], H2_TURBINE_EFF, trio[0])
    nc = network_dir / f"{scn}_solved.nc"
    if nc.exists():
        inv.add("network", ty, wy, nc, True)
        import pypsa  # only needed on this path
        n = pypsa.Network(str(nc))
        tb = n.links.index[n.links.index.str.startswith("H2_turbine")]
        eff = float(n.links.loc[tb, "efficiency"].mean()) if len(tb) else H2_TURBINE_EFF
        return (n.generators_t.p, n.storage_units_t.p, n.links_t.p0, eff, nc)
    inv.add("network", ty, wy, trio[0], False)
    inv.add("network", ty, wy, nc, False)
    return None


def collect(source, years, wyears, args, inv):
    """Per-year metrics and duration curves for one source.

    Args:
        source: ``network`` or ``screen``.
        years: Target years.
        wyears: Weather years.
        args: Parsed command-line arguments.
        inv: Inventory of inputs.

    Returns:
        (per_year DataFrame, {target_year: ensemble DataFrame})
    """
    rows, curves = [], {}
    for ty in years:
        cs = []
        for wy in wyears:
            if source == "network":
                scn = scenario_name(args.scenario_template, ty, wy)
                got = read_network(args.market_dir, args.network_dir, scn, inv, ty, wy)
                if got is None:
                    continue
                disp, sto, lnk, eff, path = got
                res = network_residual(disp, sto, lnk, eff)["residual"]
            else:
                path = args.screen_dir / f"{ty}_wy{wy}_genmix.parquet"
                inv.add("screen", ty, wy, path, path.exists())
                if not path.exists():
                    continue
                res = screen_residual(pd.read_parquet(path))
            met = year_metrics(res)
            if met["n_hours"] < 8700:
                logger.warning("%s %s wy%s: only %d hours - not a full year",
                               source, ty, wy, met["n_hours"])
            rows.append({"source": source, "target_year": ty, "weather_year": wy,
                         "file": str(path), **met})
            cs.append(duration_curve(res))
            logger.info("%-7s %s wy%s  rd %.1f  su %.1f TWh  pk %.1f GW",
                        source, ty, wy, met["rd_twh"], met["su_twh"], met["pk_gw"])
        if cs:
            curves[ty] = ensemble(cs)
    return pd.DataFrame(rows), curves


# ============================================================================ #
# Summary and figure
# ============================================================================ #
def summarise(per_year, n_expected):
    """Ensemble means per (source, target year), next to the published values.

    Args:
        per_year: Output of :func:`collect` (one or both sources concatenated).
        n_expected: Weather years asked for.

    Returns:
        DataFrame, one row per (source, target year).
    """
    if per_year.empty:
        return pd.DataFrame()
    g = per_year.groupby(["source", "target_year"])
    s = g.agg(n_years=("weather_year", "count"), rd_twh=("rd_twh", "mean"),
              su_twh=("su_twh", "mean"), pk_gw=("pk_gw", "mean"),
              rd_p10=("rd_twh", lambda x: x.quantile(0.1)),
              rd_p90=("rd_twh", lambda x: x.quantile(0.9)),
              su_p10=("su_twh", lambda x: x.quantile(0.1)),
              su_p90=("su_twh", lambda x: x.quantile(0.9))).reset_index()
    s["n_expected"] = n_expected
    s["published_rd_twh"] = s.target_year.map(lambda t: PUBLISHED.get(t, (np.nan,))[0])
    s["published_su_twh"] = s.target_year.map(lambda t: PUBLISHED.get(t, (np.nan, np.nan))[1])
    s["rd_minus_published"] = s.rd_twh - s.published_rd_twh
    s["su_minus_published"] = s.su_twh - s.published_su_twh
    return s.round(2)


def draw(curves, summary, source, out_base, annot=True):
    """Draw the panels in the format of ``plot_rdc_combined.R::top_panel``.

    Args:
        curves: {target_year: ensemble DataFrame}.
        summary: Output of :func:`summarise` for this source.
        source: Source label, used in the caption.
        out_base: Output path without extension.
        annot: Draw the in-plot TWh labels.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    years = sorted(curves)
    # shared y-limits across panels, as the R figure
    yl = (min(min(curves[t]["lo"].min(), curves[t]["mean"].min()) for t in years),
          max(max(curves[t]["hi"].max(), curves[t]["mean"].max()) for t in years))
    pad = 0.04 * (yl[1] - yl[0])
    yl = (yl[0] - pad, yl[1] + pad)

    fig, axes = plt.subplots(1, len(years), figsize=(6.5 * len(years), 5.0), squeeze=False)
    for ax, ty in zip(axes[0], years):
        cv = curves[ty]
        row = summary[summary.target_year == ty].iloc[0]
        x, m = cv["pct"], cv["mean"]
        ax.fill_between(x, 0, np.maximum(m, 0), color=RED_FILL, alpha=0.42, lw=0)
        ax.fill_between(x, np.minimum(m, 0), 0, color=GREEN_FILL, alpha=0.42, lw=0)
        ax.fill_between(x, cv["lo"], cv["hi"], color=BAND, alpha=0.5, lw=0)
        ax.plot(x, m, color=NAVY, lw=1.6)
        ax.axhline(0, color="#8c8c8c", lw=0.6)
        if annot:
            n = int(row.n_years)
            ax.text(24, 0.50 * yl[1], f"Residual demand\n{row.rd_twh:.1f} TWh/yr ({n}-yr mean)",
                    color=DRED, fontweight="bold", fontsize=10.5, va="center", linespacing=0.95)
            ax.text(56, 0.45 * yl[0], f"Residual surplus\n{row.su_twh:.1f} TWh/yr ({n}-yr mean)",
                    color=DGRN, fontweight="bold", fontsize=10.5, va="center", linespacing=0.95)
        ax.set_xlim(0, 100)
        ax.set_ylim(*yl)
        ax.set_title(f"GB {ty}  -  residual demand across weather years",
                     fontweight="bold", fontsize=13)
        ax.set_xlabel("Percentage of hours (%)", fontsize=12)
        ax.set_ylabel("Residual demand (GW)", fontsize=12)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    nyr = int(summary.n_years.min())
    what = {"network": "Whole-network dispatch per weather year (same accounting as the "
                       "weather-2010 panel)",
            "screen": "Single-node LP per weather year (seasonal_storage_weatheryears.py, "
                      "the published method)"}[source]
    cap = ("Residual demand = demand - wind - solar - must-run firm (nuclear + biomass group). "
           f"{what}; navy line = mean, grey band = P10-P90 across {nyr} weather years.")
    width = 95 * len(years) + 40 * (len(years) - 1)
    cap = textwrap.fill(cap, width=width)
    nlines = cap.count("\n") + 1
    fig.text(0.01, 0.005, cap, fontsize=8, ha="left", va="bottom")
    fig.tight_layout(rect=(0, 0.035 * nlines, 1, 1))
    for ext in ("png", "pdf"):
        fig.savefig(f"{out_base}.{ext}", dpi=160)
    plt.close(fig)
    logger.info("wrote %s.png / .pdf", out_base)


# ============================================================================ #
def parse_years(text):
    """Parse ``1985-2025`` or ``2010,2012`` into a tuple of ints."""
    out = []
    for part in str(text).split(","):
        if "-" in part:
            a, b = part.split("-")
            out.extend(range(int(a), int(b) + 1))
        elif part.strip():
            out.append(int(part))
    return tuple(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--source", choices=("network", "screen", "both"), default="network")
    ap.add_argument("--scenario-template", default="HT{yy}_disp_w{wy}",
                    help="network scenario id; {yy}=30/40, {ty}=2030/2040, {wy}=weather year")
    ap.add_argument("--target-years", default="2030,2040", type=parse_years)
    ap.add_argument("--weather-years", default="1985-2025", type=parse_years)
    ap.add_argument("--market-dir", type=Path, default=ROOT / "resources" / "market")
    ap.add_argument("--network-dir", type=Path, default=ROOT / "resources" / "network")
    ap.add_argument("--screen-dir", type=Path,
                    default=ROOT / "resources" / "analysis" / "weatheryears")
    ap.add_argument("--out", type=Path,
                    default=ROOT / "resources" / "analysis" / "rdc_weatheryear_ensemble")
    ap.add_argument("--min-years", type=int, default=1,
                    help="draw a source only if every target year has at least this many years")
    ap.add_argument("--inventory-only", action="store_true",
                    help="only report which input files exist")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    args.out.mkdir(parents=True, exist_ok=True)
    sources = ("network", "screen") if args.source == "both" else (args.source,)
    inv = Inventory()

    if args.inventory_only:
        for ty in args.target_years:
            for wy in args.weather_years:
                if "network" in sources:
                    scn = scenario_name(args.scenario_template, ty, wy)
                    trio = args.market_dir / f"{scn}_wholesale_dispatch.csv"
                    nc = args.network_dir / f"{scn}_solved.nc"
                    inv.add("network", ty, wy, trio, trio.exists())
                    inv.add("network", ty, wy, nc, nc.exists())
                if "screen" in sources:
                    p = args.screen_dir / f"{ty}_wy{wy}_genmix.parquet"
                    inv.add("screen", ty, wy, p, p.exists())
        f = inv.frame()
        f.to_csv(args.out / "rdc_wy_inputs.csv", index=False)
        print(f.groupby(["source", "target_year"]).found.sum().to_string())
        return 0

    per_all, summaries = [], []
    for src in sources:
        per, curves = collect(src, args.target_years, args.weather_years, args, inv)
        if per.empty:
            logger.error("%s: no inputs found - see rdc_wy_inputs.csv", src)
            continue
        per.to_csv(args.out / f"rdc_wy_{src}_per_year.csv", index=False)
        pd.concat({ty: c for ty, c in curves.items()}, names=["target_year", "i"]) \
            .reset_index(level=0).to_csv(args.out / f"rdc_wy_{src}_curves.csv", index=False)
        summ = summarise(per, len(args.weather_years))
        if len(curves) == len(args.target_years) and summ.n_years.min() >= args.min_years:
            draw(curves, summ, src, args.out / f"rdc_wy_{src}")
        per_all.append(per)
        summaries.append(summ)

    f = inv.frame()
    f.to_csv(args.out / "rdc_wy_inputs.csv", index=False)
    missing = f[~f.found]
    if len(missing):
        logger.warning("%d input files missing (listed in %s)", len(missing),
                       args.out / "rdc_wy_inputs.csv")
    if not summaries:
        return 1
    s = pd.concat(summaries, ignore_index=True)
    s.to_csv(args.out / "rdc_wy_summary.csv", index=False)
    print(s.to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
