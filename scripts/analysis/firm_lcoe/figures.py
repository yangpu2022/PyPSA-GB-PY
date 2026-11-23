"""Figures F1-F4 of the firm-LCOE analysis, drawn from the sweep's results.csv alone.

    python scripts/analysis/firm_lcoe/figures.py                       # resources/analysis/firm_lcoe/results.csv
    python scripts/analysis/firm_lcoe/figures.py --results other.csv --out some/dir

F1 firm LCOE vs firmness, F2 cost decomposition, F3 capacity mix, F4 storage cycles and duration. The headline
firm LCOE is the hourly-firm value (block solution plus hourly top-up) wherever the sweep produced one, and the
block value otherwise. report.py calls these functions and adds the market figures, workbook and HTML report.
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..'))
OUT = os.path.join(ROOT, 'resources', 'analysis', 'firm_lcoe')
RESULTS = os.path.join(OUT, 'results.csv')
FIG = os.path.join(OUT, 'figures')
FIGURES = ('F1_firm_lcoe_vs_firmness', 'F2_cost_decomposition', 'F3_capacity_mix', 'F4_storage_cycles_duration')

LABEL = {'re_storage': 'RE + storage', 're_storage_gas5': 'RE + storage + 5% gas', 'nuclear_storage': 'Nuclear + storage',
         'gas_ccus': 'Gas CCUS', 'all_tech': 'All technologies'}
CASE_COL = {'re_storage': '#2e6da4', 're_storage_gas5': '#4d4d4d', 'nuclear_storage': '#8e44ad', 'gas_ccus': '#7f8c8d', 'all_tech': '#27ae60'}
COL = {'solar': '#f0b429', 'onshore': '#7fb3d5', 'offshore': '#2e6da4', 'nuclear': '#8e44ad', 'gas_ccus': '#7f8c8d', 'ccgt': '#4d4d4d',
       'battery': '#e67e22', 'ldes': '#16a085', 'h2': '#c0392b', 'curtailed': '#d5d8dc'}
COMP_COL = {'VRE used': COL['offshore'], 'VRE curtailed': COL['curtailed'], 'Nuclear': COL['nuclear'], 'Gas CCUS': COL['gas_ccus'],
            'Backup gas': COL['ccgt'], 'Battery': COL['battery'], 'LDES': COL['ldes'], 'Hydrogen': COL['h2'], 'Hourly top-up': '#222222'}
plt.rcParams.update({'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False, 'figure.dpi': 130})


def load_results(path: str = RESULTS) -> pd.DataFrame:
    """Read results.csv, keep solved rows and set the headline firm LCOE.

    Args:
        path: results.csv written by run_sweep.py.

    Returns:
        One row per solve; ``firm_lcoe`` is the hourly-firm value where it exists, ``firm_lcoe_block`` the block value.
    """
    res = pd.read_csv(path)
    res['sens'] = res['sens'].fillna('base')
    res = res[res.status.isin(['optimal', 'suboptimal'])].copy()
    if res.empty:
        raise ValueError(f'{path}: no optimal or suboptimal rows')
    if 'firm_lcoe_hourly' not in res:
        res['firm_lcoe_hourly'] = np.nan
    res['firm_lcoe_block'] = res['firm_lcoe']
    res['firm_lcoe'] = res['firm_lcoe_hourly'].fillna(res['firm_lcoe'])
    return res


def savefig(fig, name: str, fig_dir: str = FIG) -> str:
    """Save ``fig`` as ``<fig_dir>/<name>.png``, close it and return the path."""
    os.makedirs(fig_dir, exist_ok=True)
    p = os.path.join(fig_dir, f'{name}.png')
    fig.savefig(p, bbox_inches='tight')
    plt.close(fig)
    return p


def g(r, k, default=0.0):
    """Value of ``k`` in a results row, or ``default`` when missing or NaN."""
    v = r.get(k, default)
    return default if v is None or (isinstance(v, float) and np.isnan(v)) else v


def components(r) -> dict:
    """GBP/MWh delivered by cost component for one results row (sums to the headline firm LCOE)."""
    den = r['delivered_twh'] * 1e6
    vre = sum(g(r, f'cost_{k}') for k in ('solar', 'onshore', 'offshore'))
    cur = g(r, 'cost_vre_curtailed')
    out = {'VRE used': (vre - cur) / den, 'VRE curtailed': cur / den}
    for k, lab in (('nuclear', 'Nuclear'), ('gas_ccus', 'Gas CCUS'), ('ccgt', 'Backup gas')):
        v = g(r, f'cost_{k}_fixed') + g(r, f'cost_{k}_var')
        if v:
            out[lab] = v / den
    for s, lab in (('battery', 'Battery'), ('ldes', 'LDES'), ('h2', 'Hydrogen')):
        v = g(r, f'cost_{s}')
        if v:
            out[lab] = v / den
    if g(r, 'topup_cost_gbp_yr'):
        out['Hourly top-up'] = g(r, 'topup_cost_gbp_yr') / den
    return out


def f1_firmness(res: pd.DataFrame, fig_dir: str = FIG) -> str:
    """F1: firm LCOE against firmness, one line per case (base settings)."""
    base = res[res.sens == 'base']
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    for cn, d in base.groupby('case'):
        d = d.sort_values('firmness')
        x = -np.log10(np.clip(1 - d.firmness, 1e-4, 1))
        ax.plot(x, d.firm_lcoe, 'o-', label=LABEL[cn], color=CASE_COL[cn])
        for xi, yi in zip(x, d.firm_lcoe):
            ax.annotate(f'{yi:.0f}', (xi, yi), textcoords='offset points', xytext=(4, 4), fontsize=8)
    ax.set_xticks([1, 1.3, 2, 3, 4]); ax.set_xticklabels(['90%', '95%', '99%', '99.9%', '100%'])
    ax.set_xlabel('Firmness (share of demand met, every weather year)'); ax.set_ylabel('Firm LCOE, GBP/MWh delivered (real 2024)')
    ax.set_title(f'Cost of meeting the GB demand profile, {int(res.n_years.max())} weather years'); ax.legend(frameon=False)
    return savefig(fig, 'F1_firm_lcoe_vs_firmness', fig_dir)


def f2_decomposition(res: pd.DataFrame, fig_dir: str = FIG) -> str:
    """F2: stacked cost components at 99 % and 100 % firmness (base settings)."""
    pts = res[(res.sens == 'base') & (res.firmness.isin([0.99, 1.0]))].copy()
    pts['lab'] = pts.case.map(LABEL) + ' ' + pts.firmness.map(lambda f: f'{100*f:g}%')
    comps = [components(r) for _, r in pts.iterrows()]
    keys = list(dict.fromkeys(k for c in comps for k in c))
    fig, ax = plt.subplots(figsize=(8.5, 4.8)); bottom = np.zeros(len(pts))
    for k in keys:
        v = np.array([c.get(k, 0) for c in comps]); ax.bar(pts.lab, v, bottom=bottom, label=k, color=COMP_COL.get(k, '#999')); bottom += v
    for i, t in enumerate(bottom):
        ax.text(i, t + 2, f'{t:.0f}', ha='center', fontsize=9)
    ax.set_ylim(0, 1.08 * bottom.max())
    ax.set_ylabel('GBP/MWh delivered'); ax.set_title('Where the firm LCOE goes')
    ax.legend(frameon=False, fontsize=8, loc='upper left', bbox_to_anchor=(1.01, 1))
    plt.setp(ax.get_xticklabels(), rotation=20, ha='right')
    return savefig(fig, 'F2_cost_decomposition', fig_dir)


def f3_capacity(res: pd.DataFrame, fig_dir: str = FIG) -> str:
    """F3: generation capacity, battery + LDES energy and hydrogen cavern size at 100 % firmness."""
    pts = res[(res.sens == 'base') & (res.firmness == 1.0)].copy(); pts['lab'] = pts.case.map(LABEL)
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.2), gridspec_kw=dict(width_ratios=[1.3, 1, 0.8]))
    ax = axes[0]; bottom = np.zeros(len(pts))
    for k in ('solar', 'onshore', 'offshore', 'nuclear', 'gas_ccus', 'ccgt'):
        v = pts[f'cap_{k}_mw'].fillna(0).to_numpy() / 1e3 if f'cap_{k}_mw' in pts else np.zeros(len(pts))
        ax.bar(pts.lab, v, bottom=bottom, color=COL[k], label=k); bottom += v
    ax.set_ylim(0, 1.3 * bottom.max())
    ax.set_ylabel('GW'); ax.set_title('Generation capacity'); ax.legend(frameon=False, fontsize=8, ncol=3, loc='upper left'); plt.setp(ax.get_xticklabels(), rotation=20, ha='right')
    ax = axes[1]; bottom = np.zeros(len(pts))
    for s in ('battery', 'ldes'):
        v = pts[f'{s}_e_mwh'].fillna(0).to_numpy() / 1e3 if f'{s}_e_mwh' in pts else np.zeros(len(pts))
        ax.bar(pts.lab, v, bottom=bottom, color=COL[s], label=s); bottom += v
    ax.set_ylabel('GWh'); ax.set_title('Battery + LDES energy'); ax.legend(frameon=False, fontsize=8); plt.setp(ax.get_xticklabels(), rotation=20, ha='right')
    ax = axes[2]
    v = pts['h2_e_mwh'].fillna(0).to_numpy() / 1e6 if 'h2_e_mwh' in pts else np.zeros(len(pts))
    ax.bar(pts.lab, v, color=COL['h2']); ax.set_ylabel('TWh H2'); ax.set_title('Hydrogen cavern'); plt.setp(ax.get_xticklabels(), rotation=20, ha='right')
    return savefig(fig, 'F3_capacity_mix', fig_dir)


def f4_cycles(res: pd.DataFrame, fig_dir: str = FIG) -> str:
    """F4: cycles per year and duration (E/P) of every store built with more than 1 MWh (base settings)."""
    pts = res[(res.sens == 'base')].copy(); pts['lab'] = pts.case.map(LABEL) + ' ' + pts.firmness.map(lambda f: f'{100*f:g}%')
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2))
    for s in ('battery', 'ldes', 'h2'):
        if f'{s}_cycles_yr' in pts:
            ok = pts[f'{s}_e_mwh'].fillna(0) > 1
            axes[0].plot(pts.lab[ok], pts.loc[ok, f'{s}_cycles_yr'], 'o', color=COL[s], label=s)
            axes[1].plot(pts.lab[ok], pts.loc[ok, f'{s}_duration_h'], 'o', color=COL[s], label=s)
    axes[0].set_ylabel('cycles per year'); axes[0].set_title('Storage cycles'); axes[1].set_ylabel('hours'); axes[1].set_yscale('log'); axes[1].set_title('Storage duration (E/P)')
    for ax in axes:
        ax.legend(frameon=False, fontsize=8); plt.setp(ax.get_xticklabels(), rotation=30, ha='right', fontsize=8)
    return savefig(fig, 'F4_storage_cycles_duration', fig_dir)


def make_figures(res: pd.DataFrame, fig_dir: str = FIG) -> dict:
    """Draw F1-F4.

    Args:
        res: output of ``load_results``.
        fig_dir: folder the PNGs are written to.

    Returns:
        ``{'F1': path, ..., 'F4': path}``.
    """
    return dict(F1=f1_firmness(res, fig_dir), F2=f2_decomposition(res, fig_dir),
                F3=f3_capacity(res, fig_dir), F4=f4_cycles(res, fig_dir))


def main(argv=None) -> dict:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--results', default=RESULTS, help='results.csv from run_sweep.py')
    ap.add_argument('--out', default=FIG, help='folder for the PNGs')
    a = ap.parse_args(argv)
    if not os.path.exists(a.results):
        sys.exit(f'{a.results} not found: run scripts/analysis/firm_lcoe/run_sweep.py first')
    paths = make_figures(load_results(a.results), a.out)
    for p in paths.values():
        print('wrote', os.path.relpath(p, ROOT) if p.startswith(ROOT) else p)
    return paths


if __name__ == '__main__':
    main()
