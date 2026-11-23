"""Smoke test: figures.py redraws F1-F4 of the firm-LCOE analysis from a results table.

A synthetic results.csv with every case the sweep runs stands in for the model outputs, so the test needs neither
Gurobi nor the weather-year inputs. When the real resources/analysis/firm_lcoe/results.csv exists, its cost
components are also checked against the headline firm LCOE.
"""
import os

import numpy as np
import pandas as pd
import pytest

pytest.importorskip('matplotlib')
from scripts.analysis.firm_lcoe import figures as F  # noqa: E402

DELIVERED_TWH = 500.0


def _row(case, firmness, costs, caps, stores, topup=0.0, sens='base', sens_value=None, status='optimal'):
    """One results row whose firm LCOE equals the sum of its cost components."""
    r = dict(case=case, firmness=firmness, sens=sens, sens_value=sens_value, status=status, n_years=41, step_h=3.0,
             delivered_twh=DELIVERED_TWH * firmness, demand_twh=DELIVERED_TWH, **costs, **caps)
    for s, (e_mwh, cycles, duration) in stores.items():
        r.update({f'{s}_e_mwh': e_mwh, f'{s}_cycles_yr': cycles, f'{s}_duration_h': duration, f'{s}_p_mw': e_mwh / duration})
    total = sum(v for k, v in costs.items() if k != 'cost_vre_curtailed')
    r['cost_total_gbp_yr'] = total
    r['firm_lcoe'] = total / (r['delivered_twh'] * 1e6)
    if firmness >= 1.0:
        r['topup_cost_gbp_yr'] = topup
        r['firm_lcoe_hourly'] = (total + topup) / (r['delivered_twh'] * 1e6)
    return r


def synthetic_results() -> pd.DataFrame:
    vre = dict(cost_solar=8e9, cost_onshore=1.5e10, cost_offshore=3e10, cost_vre_curtailed=1e10)
    vre_caps = dict(cap_solar_mw=1e5, cap_onshore_mw=4e4, cap_offshore_mw=1.2e5)
    re_stores = dict(battery=(2e5, 800, 3.2), ldes=(1.5e6, 80, 33), h2=(2e7, 1, 900))
    rows = []
    for f, scale in ((0.90, 0.85), (0.99, 0.95), (1.0, 1.0)):
        rows.append(_row('re_storage', f, {k: v * scale for k, v in vre.items()} | dict(cost_battery=4e9, cost_ldes=6e9, cost_h2=5e9),
                         vre_caps, re_stores, topup=3e8))
    rows.append(_row('re_storage_gas5', 1.0, vre | dict(cost_battery=4e9, cost_ldes=5e9, cost_h2=3e9, cost_ccgt_fixed=2e9, cost_ccgt_var=1e9),
                     vre_caps | dict(cap_ccgt_mw=3e4), re_stores, topup=4e8))
    for f in (0.99, 1.0):
        rows.append(_row('nuclear_storage', f, dict(cost_nuclear_fixed=7e10, cost_nuclear_var=6e9, cost_battery=1e9, cost_ldes=5e9),
                         dict(cap_nuclear_mw=8e4), dict(battery=(1e5, 120, 6), ldes=(1e6, 15, 40)), topup=1e8))
    rows.append(_row('gas_ccus', 1.0, dict(cost_gas_ccus_fixed=3.5e10, cost_gas_ccus_var=3e10), dict(cap_gas_ccus_mw=1.2e5), {}, topup=8e8))
    rows.append(_row('all_tech', 1.0, vre | dict(cost_nuclear_fixed=1e10, cost_gas_ccus_fixed=5e9, cost_gas_ccus_var=2e9, cost_battery=2e9),
                     vre_caps | dict(cap_nuclear_mw=1e4, cap_gas_ccus_mw=2e4), dict(battery=(1e5, 400, 4)), topup=2e8))
    rows.append(_row('re_storage', 1.0, vre, vre_caps, re_stores, sens='battery_e', sens_value=80.0))
    rows.append(dict(case='gas_ccus', firmness=1.0, sens='base', status='infeasible'))
    return pd.DataFrame(rows)


@pytest.fixture
def results_csv(tmp_path):
    p = tmp_path / 'results.csv'
    synthetic_results().to_csv(p, index=False)
    return p


def test_load_results_headline_is_hourly_where_present(results_csv):
    res = F.load_results(str(results_csv))
    assert (res.status == 'optimal').all()                              # infeasible row dropped
    firm = res[res.firmness == 1.0]
    np.testing.assert_allclose(firm.firm_lcoe, firm.firm_lcoe_hourly)
    part = res[res.firmness < 1.0]
    np.testing.assert_allclose(part.firm_lcoe, part.firm_lcoe_block)


def test_components_sum_to_headline(results_csv):
    res = F.load_results(str(results_csv))
    for _, r in res.iterrows():
        assert sum(F.components(r).values()) == pytest.approx(r.firm_lcoe, rel=1e-9)


def test_cli_writes_all_four_figures(results_csv, tmp_path):
    out = tmp_path / 'figures'
    paths = F.main(['--results', str(results_csv), '--out', str(out)])
    assert sorted(paths) == ['F1', 'F2', 'F3', 'F4']
    for name in F.FIGURES:
        png = out / f'{name}.png'
        assert png.exists() and png.stat().st_size > 10_000, name
        assert png.read_bytes()[:8] == b'\x89PNG\r\n\x1a\n'


@pytest.mark.skipif(not os.path.exists(F.RESULTS), reason='needs resources/analysis/firm_lcoe/results.csv from run_sweep.py')
def test_real_results_components_sum_to_headline():
    # Sweeps run before the unserved-energy tie-break was taken out of cost_total_gbp_yr carry it in firm_lcoe:
    # 1 GBP per MWh unserved, i.e. at most unserved / delivered GBP/MWh above the component sum.
    res = F.load_results(F.RESULTS)
    for _, r in res.iterrows():
        gap = r.firm_lcoe - sum(F.components(r).values())
        assert -1e-6 <= gap <= r.unserved_twh / r.delivered_twh + 1e-6, (r.case, r.firmness, r.sens, gap)
