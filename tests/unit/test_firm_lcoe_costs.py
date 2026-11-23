"""Cost table of the firm-LCOE LP reproduces the DESNZ 2025 figures it is built from."""
import unittest

from scripts.analysis.firm_lcoe import costs as C


class TestCosts(unittest.TestCase):
    def test_afc_reproduces_desnz(self):
        g = C.generation(C.DEFAULT_OPT)
        self.assertAlmostEqual(g['solar']['afc'], 63.07, 1)
        self.assertAlmostEqual(g['onshore']['afc'], 188.0, 0)
        self.assertAlmostEqual(g['offshore']['afc'], 442.0, 0)
        self.assertAlmostEqual(g['nuclear']['afc'], 1009.2, 0)
        self.assertAlmostEqual(g['solar']['afc'] * 1000 / (8760 * 0.12), 60.0, 2)

    def test_two_point_gas_ccus(self):
        afc, vom = C.two_point(105, 0.88, 181, 0.30)
        self.assertAlmostEqual(afc, 303, delta=2)
        self.assertAlmostEqual(vom, 65.7, delta=0.5)
        self.assertAlmostEqual(afc * 1000 / (8760 * 0.88) + vom, 105, 1)
        self.assertAlmostEqual(afc * 1000 / (8760 * 0.30) + vom, 181, 1)

    def test_ccgt_vom(self):
        self.assertAlmostEqual(C.ccgt_vom(71, 120), 5 + 0.632 * 71 + 0.339 * 120, 6)

    def test_store_annuities(self):
        s = C.stores(C.DEFAULT_OPT)
        self.assertAlmostEqual(s['battery']['afc_p_in'], 17.8, delta=0.2)
        self.assertAlmostEqual(s['battery']['afc_e'], 17.8, delta=0.2)
        self.assertAlmostEqual(s['ldes']['afc_p_in'], 112.2, delta=1)
        self.assertAlmostEqual(s['ldes']['afc_e'], 5.1, delta=0.1)
        self.assertAlmostEqual(s['h2']['afc_p_in'], 141, delta=1)
        self.assertAlmostEqual(s['h2']['afc_p_out'], 112, delta=1)
        self.assertAlmostEqual(s['h2']['afc_e'], 0.07, delta=0.02)
        self.assertTrue(s['battery']['symmetric'] and not s['h2']['symmetric'])

    def test_sensitivity_options(self):
        s = C.stores(dict(C.DEFAULT_OPT, battery_e=200.0))
        self.assertAlmostEqual(s['battery']['afc_e'], 200 * (C.crf(0.089, 15) + 0.025), 3)
        g = C.generation(dict(C.DEFAULT_OPT, nuclear_lcoe=120.0))
        self.assertAlmostEqual(g['nuclear']['afc'], (120 - 12) * 8760 * 0.9 / 1000, 3)

    def test_lcos(self):
        s = C.stores(C.DEFAULT_OPT)['battery']
        exp = (s['afc_p_in'] * 1000 / (300 * 2) + s['afc_e'] * 1000 / 300 + 20 / 0.86)
        self.assertAlmostEqual(C.lcos('battery', 300, 2, 20, C.DEFAULT_OPT), exp, 6)


if __name__ == '__main__':
    unittest.main()
