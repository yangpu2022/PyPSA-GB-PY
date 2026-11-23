"""Firm-LCOE LP on toy data with known optima (skips without gurobipy)."""
import math
import unittest

import numpy as np
import pytest

pytest.importorskip('gurobipy')
from scripts.analysis.firm_lcoe import costs as C  # noqa: E402
from scripts.analysis.firm_lcoe import model as M  # noqa: E402


def toy(days=2, step=1):
    """One VRE ('solar' slot) at CF 1 for hours 0-11, 0 for 12-23; flat 100 MW demand; two identical years."""
    T = 24 * days
    cf = np.zeros((2, T, 3))
    for d in range(days):
        cf[:, d * 24: d * 24 + 12, 0] = 1.0
    return dict(cf=cf, demand=np.full(T, 100.0), years=[1, 2], T=T, dt=float(step), techs=['solar', 'onshore', 'offshore'])


class TestModel(unittest.TestCase):
    def test_toy_battery_only_known_optimum(self):
        data = toy()
        case = dict(vre=['solar'], disp=[], stores=['battery'], gas_share=None)
        m, h = M.build_lp(data, case, 1.0, C.DEFAULT_OPT, threads=2)
        self.assertEqual(M.solve(m), 'optimal')
        r = M.extract(m, h, data, case, 1.0, C.DEFAULT_OPT)
        eta = math.sqrt(0.86)
        soc = 1200 / eta
        charge = soc / eta
        self.assertAlmostEqual(r['cap_solar_mw'], 100 + charge / 12, delta=1.0)
        self.assertAlmostEqual(r['battery_e_mwh'], soc, delta=5.0)
        self.assertAlmostEqual(r['battery_p_mw'], charge / 12, delta=1.0)
        self.assertAlmostEqual(r['curtail_share'], 0.0, delta=0.01)
        self.assertAlmostEqual(r['unserved_twh'], 0.0, 6)
        self.assertAlmostEqual(r['firm_lcoe'], r['cost_total_gbp_yr'] / (r['delivered_twh'] * 1e6), 6)

    def test_gas_ccus_alone_is_peak_over_availability(self):
        data = toy()
        case = dict(vre=[], disp=['gas_ccus'], stores=[], gas_share=None)
        m, h = M.build_lp(data, case, 1.0, C.DEFAULT_OPT, threads=2)
        self.assertEqual(M.solve(m), 'optimal')
        r = M.extract(m, h, data, case, 1.0, C.DEFAULT_OPT)
        g = C.generation(C.DEFAULT_OPT)['gas_ccus']
        self.assertAlmostEqual(r['cap_gas_ccus_mw'], 100 / 0.83, 3)
        exp = g['afc'] * 1000 * (100 / 0.83) / (100 * 48) + g['vom']
        self.assertAlmostEqual(r['firm_lcoe'], exp, 3)

    def test_firmness_relaxes(self):
        data = toy()
        case = dict(vre=['solar'], disp=[], stores=['battery'], gas_share=None)
        m, h = M.build_lp(data, case, 0.9, C.DEFAULT_OPT, threads=2)
        M.solve(m)
        r = M.extract(m, h, data, case, 0.9, C.DEFAULT_OPT)
        self.assertAlmostEqual(r['unserved_twh'] / r['demand_twh'], 0.10, 3)
        # the tie-break cost on unserved energy is not part of the reported system cost
        parts = r['cost_solar'] + r['cost_battery']
        self.assertAlmostEqual(r['cost_total_gbp_yr'], parts, delta=1e-6 * parts)

    def test_cap_max_binds(self):
        data = toy()
        case = dict(vre=['solar'], disp=[], stores=['battery'], gas_share=None)
        opt = dict(C.DEFAULT_OPT, cap_max=dict(solar=150.0))
        m, h = M.build_lp(data, case, 0.5, opt, threads=2)
        m.update()
        self.assertAlmostEqual(h['cap_vre'][0].UB, 150.0, 6)
        self.assertEqual(M.solve(m), 'optimal')
        r = M.extract(m, h, data, case, 0.5, opt)
        self.assertLessEqual(r['cap_solar_mw'], 150.0 + 1e-6)
        m2, h2 = M.build_lp(data, case, 0.5, dict(C.DEFAULT_OPT, cap_max=None), threads=2)
        m2.update()
        self.assertGreater(h2['cap_vre'][0].UB, 1e20)

    def test_topup_hourly_restores_firmness(self):
        data = toy()
        case = dict(vre=['solar'], disp=[], stores=['battery'], gas_share=None)
        caps = dict(cap_solar_mw=216.3, battery_p_mw=116.3, battery_e_mwh=600.0)   # energy too small
        best, extra = M.topup_hourly(data, caps, case, C.DEFAULT_OPT)
        self.assertGreater(best['battery_e_mwh'], 1200.0)
        self.assertGreater(extra, 0.0)
        self.assertAlmostEqual(best['cap_solar_mw'], 216.3, delta=1.0)
        rc = M.recheck_hourly(data, best, case, C.DEFAULT_OPT)
        self.assertEqual(rc['lole_h_max'], 0)

    def test_recheck_hourly_fixed_caps(self):
        data = toy()
        case = dict(vre=['solar'], disp=[], stores=['battery'], gas_share=None)
        caps = dict(cap_solar_mw=216.3, battery_p_mw=116.3, battery_e_mwh=1294.0)
        rc = M.recheck_hourly(data, caps, case, C.DEFAULT_OPT)
        self.assertLess(rc['lole_h_max'], 1)
        caps['battery_e_mwh'] = 600.0
        rc = M.recheck_hourly(data, caps, case, C.DEFAULT_OPT)
        self.assertGreater(rc['lole_h_max'], 5)


if __name__ == '__main__':
    unittest.main()
