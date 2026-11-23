"""One workbook + one tabbed self-contained HTML + README for the firm-LCOE analysis.

    python scripts/analysis/firm_lcoe/report.py [--results results.csv]
"""
import argparse, base64, html, os, subprocess, sys, datetime as dt
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from scripts.analysis.firm_lcoe import costs as C, inputs as I  # noqa: E402
from scripts.analysis.firm_lcoe.figures import (  # noqa: E402
    OUT, LABEL, COL, components, g, savefig, load_results, make_figures)

MARKET = os.path.join(OUT, 'market_bids_2024_25.csv')


def img(p):
    return '<img src="data:image/png;base64,' + base64.b64encode(open(p, 'rb').read()).decode() + '">'


def fmt_cell(v, fmt):
    if isinstance(v, (float, np.floating)):
        return '' if np.isnan(v) else fmt.format(v)
    return html.escape(str(v))


def table(df, fmt='{:,.1f}'):
    th = ''.join(f'<th>{html.escape(str(c))}</th>' for c in df.columns)
    tr = ''.join('<tr>' + ''.join(f'<td>{fmt_cell(v, fmt)}</td>' for v in r) + '</tr>' for r in df.itertuples(index=False))
    return f'<table><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table>'


def f5_shift_cost(mk, res):
    fig, ax = plt.subplots(figsize=(8.5, 5))
    d = mk[(mk.block == 'D') & (mk.year == 2025)]
    for grp, dd in d.groupby('group', sort=False):
        dd = dd.sort_values('cycles'); ax.plot(dd.cycles, dd.value, '-o', ms=3, label=grp)
    xr = 760
    for y, ls in ((2024, ':'), (2025, '--')):
        sp = mk[(mk.metric == 'spread6h') & (mk.year == y)].value.iloc[0]
        ax.axhline(sp, color='k', ls=ls, lw=1); ax.text(xr, sp, f'DA 6h-6h spread {y}: {sp:.0f}', fontsize=8, va='bottom', ha='right')
    off = mk[(mk.metric == 'bm_turn_down_bid') & mk.group.str.contains('Wind offshore') & (mk.year == 2025)].value
    if len(off):
        gs = mk[(mk.metric == 'srmc_total') & (mk.year == 2025)].value.iloc[0]
        ax.axhline(gs - off.median(), color=COL['h2'], ls='-.', lw=1)
        ax.text(xr, gs - off.median(), f'gas SRMC minus offshore-wind curtailment bid 2025: {gs-off.median():.0f}', fontsize=8, va='bottom', ha='right')
    for y, mkr in ((2024, '^'), (2025, 'v')):
        rev = mk[(mk.metric == 'bess_revenue') & (mk.year == y)].value.iloc[0]
        ax.plot([365], [rev / 730], mkr, color='k', ms=7, label=f'GB BESS revenue {y} per MWh if 1 cycle/day x 2 h')
    base = res[(res.sens == 'base') & (res.case == 're_storage') & (res.firmness == 1.0)]
    if len(base):
        r = base.iloc[0]; p_ch = mk[(mk.metric == 'cheapest6h') & (mk.year == 2025)].value.iloc[0]
        for s, lab in (('battery', 'LP battery'), ('ldes', 'LP LDES'), ('h2', 'LP hydrogen')):
            if g(r, f'{s}_e_mwh') > 1 and g(r, f'{s}_cycles_yr') > 0:
                ax.plot(r[f'{s}_cycles_yr'], C.lcos(s, r[f'{s}_cycles_yr'], r[f'{s}_duration_h'], p_ch), 's', color=COL[s], ms=9,
                        label=f'{lab} as built by the LP ({r[f"{s}_duration_h"]:.0f} h, {r[f"{s}_cycles_yr"]:.0f} cycles)')
    ax.set_xscale('log'); ax.set_yscale('log'); ax.set_xlabel('cycles per year'); ax.set_ylabel('GBP per MWh shifted (incl. charging at the cheapest 6 h)')
    ax.set_title('Unit cost of shifting one MWh vs what the 2024-25 market paid'); ax.legend(frameon=False, fontsize=7, ncol=2, loc='upper right')
    return savefig(fig, 'F5_shift_cost_vs_market')


def f6_bids(mk):
    b = mk[mk.metric == 'bm_turn_down_bid'].pivot_table(index='group', columns='year', values='value')
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), gridspec_kw=dict(width_ratios=[1.4, 1]))
    b.sort_values(b.columns[-1]).plot.barh(ax=axes[0], color=['#999', '#333'])
    for y, c in ((2024, '#999'), (2025, '#333')):
        s = mk[(mk.metric == 'srmc_total') & (mk.year == y)].value.iloc[0]
        axes[0].axvline(s, color=c, ls='--', lw=1); axes[0].text(s, len(b) - 0.5, f'gas SRMC {y}: {s:.0f}', fontsize=7, rotation=90, va='top', ha='right')
    axes[0].axvline(0, color='k', lw=0.8); axes[0].set_xlabel('GBP/MWh: median BM bid to turn down (negative = must be paid to curtail)'); axes[0].set_title('What plants bid, 2024-25')
    axes[0].set_ylabel('')
    c = mk[(mk.block == 'C') & mk.metric.str.startswith(('srmc', 'da_price'))].pivot_table(index='metric', columns='year', values='value')
    order = [m for m in ['srmc_fuel', 'srmc_carbon', 'srmc_total', 'da_price_ccgt_below_median', 'da_price_ccgt_above_median', 'da_price_ccgt_top_decile'] if m in c.index]
    c.loc[order].plot.bar(ax=axes[1], color=['#999', '#333'])
    axes[1].set_ylabel('GBP/MWh'); axes[1].set_title('Gas: cost to run vs DA price when it runs'); axes[1].set_xlabel('')
    plt.setp(axes[1].get_xticklabels(), rotation=30, ha='right', fontsize=8)
    return savefig(fig, 'F6_bids_and_gas')


def main(results_path):
    res = load_results(results_path)      # headline firm_lcoe: hourly-firm where it exists
    mk = pd.read_csv(MARKET) if os.path.exists(MARKET) else None
    commit = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True, cwd=ROOT).stdout.strip()
    figs = make_figures(res)
    if mk is not None:
        figs.update(F5=f5_shift_cost(mk, res), F6=f6_bids(mk))
    else:
        print(f'{MARKET} not found: skipping F5/F6 and the market tab (built by market_bids.py)')
    key = ['case', 'firmness', 'sens', 'sens_value', 'firm_lcoe', 'firm_lcoe_block', 'curtail_share', 'cap_solar_mw', 'cap_onshore_mw', 'cap_offshore_mw', 'cap_nuclear_mw', 'cap_gas_ccus_mw', 'cap_ccgt_mw',
           'battery_p_mw', 'battery_e_mwh', 'battery_cycles_yr', 'ldes_p_mw', 'ldes_e_mwh', 'ldes_cycles_yr', 'h2_p_mw', 'h2_p_out_mw', 'h2_e_mwh', 'h2_cycles_yr', 'lole_h_mean', 'lole_h_max', 'solve_time_s']
    key = [k for k in key if k in res]
    gen = pd.DataFrame([dict(technology=k, **v) for k, v in C.generation().items()])
    sto = pd.DataFrame([dict(store=k, **v) for k, v in C.stores().items()])
    cf = I.build_cf().groupby('year')[I.TECHS].mean().reset_index(); cf['solar_derated'] = cf['solar'] * C.DEFAULT_OPT['solar_scale']
    comp = pd.DataFrame([dict(case=LABEL[r.case], firmness=r.firmness, sens=r.sens, **{k: round(v, 1) for k, v in components(r).items()}) for _, r in res.iterrows()])
    readme_rows = [
        ('Question', 'Cost per MWh delivered of meeting the GB demand profile at a stated firmness with RE+storage, nuclear(+storage) and gas CCUS; plus 2024-25 market evidence on bids vs the unit cost of shifting a MWh.'),
        ('Model', 'Single-node greenfield LP, joint over weather years, storage cyclic per year, block-averaged periods, hourly fixed-capacity re-check for LOLE. scripts/analysis/firm_lcoe/'),
        ('Weather years', f'{int(res.n_years.max())} (1985-2025 atlite REPD fleet CF), {res.step_h.iloc[0]:g}-h blocks; solar derated x{C.DEFAULT_OPT["solar_scale"]:.4f} to an 11.0% 41-yr mean'),
        ('Demand', 'FES 2025 Holistic Transition 2050 GB profile (567 TWh, peak 99.8 GW), fixed shape for every weather year (no temperature coupling)'),
        ('Costs', 'Real 2024 GBP, 2030 commissioning; DESNZ Electricity Generation Costs 2025 LCOEs reproduced exactly at DESNZ load factors; storage per spec'),
        ('Solver', 'Gurobi 13 barrier without crossover for the big LPs (capacities read from the interior point; ~1e-6 relative)'),
        ('Market data', 'N2EX DA hourly, Elexon BOD (first 7 days/month), FUELHH CCGT via Modo REST (2024-01..2025-12); NBP/UKA annual means in market_bids.py'),
        ('Spec', 'docs/superpowers/specs/2026-11-18-firm-lcoe-weather-year-lp-design.md'), ('Plan', 'docs/superpowers/plans/2026-11-18-firm-lcoe-weather-year-lp.md'),
        ('Git commit', commit), ('Built', dt.date.today().isoformat()),
        ('Sheets', 'results (one row per solve), cost_components (GBP/MWh), market_bids (tidy), costs_generation, costs_storage, cf_by_year'),
    ]
    with pd.ExcelWriter(os.path.join(OUT, 'firm_lcoe.xlsx'), engine='openpyxl') as xw:
        pd.DataFrame(readme_rows, columns=['item', 'value']).to_excel(xw, sheet_name='README', index=False)
        res[key + [c for c in res.columns if c not in key]].to_excel(xw, sheet_name='results', index=False)
        comp.to_excel(xw, sheet_name='cost_components', index=False)
        if mk is not None:
            mk.to_excel(xw, sheet_name='market_bids', index=False)
        gen.to_excel(xw, sheet_name='costs_generation', index=False)
        sto.to_excel(xw, sheet_name='costs_storage', index=False); cf.to_excel(xw, sheet_name='cf_by_year', index=False)
    base = res[res.sens == 'base']
    hl = base[base.firmness == 1.0].set_index('case').firm_lcoe
    logp = os.path.join(OUT, 'run_sweep.log')
    tabs = [
        ('Overview', '<p>Firm LCOE at 100% firmness in every weather year (GBP/MWh delivered, real 2024): ' + ', '.join(f'<b>{LABEL[c]}</b> {v:.0f}' for c, v in hl.items()) + '.</p>' + img(figs['F1']) + table(base[key], '{:,.2f}')),
        ('Cost decomposition', img(figs['F2']) + '<p>VRE curtailed = share of VRE fixed cost attributable to curtailed energy.</p>' + table(comp)),
        ('Capacity & storage', img(figs['F3']) + img(figs['F4'])),
    ] + ([('Market 2024-25', img(figs['F6']) + img(figs['F5']) + table(mk[mk.block != 'D'][['block', 'metric', 'group', 'year', 'value', 'unit', 'source']], '{:,.1f}'))] if mk is not None else []) + [
        ('Sensitivities', table(res[res.sens != 'base'][key], '{:,.2f}')),
        ('Inputs & method', table(gen, '{:,.2f}') + table(sto, '{:,.3f}') + table(cf.round(3), '{:.3f}') + '<pre>' + html.escape(open(logp, encoding='utf-8').read()[-8000:] if os.path.exists(logp) else '') + '</pre>'),
    ]
    nav = ''.join(f'<button onclick="show({i})" id="b{i}">{html.escape(t)}</button>' for i, (t, _) in enumerate(tabs))
    secs = ''.join(f'<section id="s{i}" style="display:{"block" if i == 0 else "none"}"><h2>{html.escape(t)}</h2>{b}</section>' for i, (t, b) in enumerate(tabs))
    doc = f'''<!doctype html><html><head><meta charset="utf-8"><title>Firm LCOE: RE + storage vs nuclear vs gas CCUS</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;margin:24px;color:#222;max-width:1200px}}nav button{{margin:0 4px 12px 0;padding:6px 12px;border:1px solid #bbb;background:#f6f6f6;cursor:pointer}}
nav button.on{{background:#2e6da4;color:#fff;border-color:#2e6da4}}table{{border-collapse:collapse;font-size:12px;margin:12px 0}}th,td{{border:1px solid #ddd;padding:3px 6px;text-align:right}}th{{background:#f0f0f0}}td:first-child,th:first-child{{text-align:left}}img{{max-width:100%;display:block;margin:12px 0}}pre{{font-size:11px;background:#f6f6f6;padding:8px;overflow:auto}}.sub{{color:#666}}</style></head>
<body><h1>Firm LCOE of renewables + storage vs nuclear and gas CCUS, GB demand profile, {int(res.n_years.max())} weather years</h1>
<p class="sub">Real 2024 GBP, 2030 costs. Built {dt.date.today().isoformat()}, commit {commit}. Spec: docs/superpowers/specs/2026-11-18-firm-lcoe-weather-year-lp-design.md</p>
<nav>{nav}</nav>{secs}
<script>function show(i){{document.querySelectorAll('section').forEach((s,j)=>s.style.display=i==j?'block':'none');document.querySelectorAll('nav button').forEach((b,j)=>b.className=i==j?'on':'')}}show(0)</script></body></html>'''
    open(os.path.join(OUT, 'firm_lcoe_report.html'), 'w', encoding='utf-8').write(doc)
    open(os.path.join(OUT, 'README.md'), 'w', encoding='utf-8').write('# firm_lcoe\n\n' + '\n'.join(f'- **{k}**: {v}' for k, v in readme_rows) +
        '\n\nFiles: results.csv, market_bids_2024_25.csv, firm_lcoe.xlsx, firm_lcoe_report.html, figures/, inputs/ (national_cf.parquet, demand.parquet, market/*.csv), run_sweep.log.\n')
    print('wrote', OUT)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--results', default=os.path.join(OUT, 'results.csv'))
    main(ap.parse_args().results)
