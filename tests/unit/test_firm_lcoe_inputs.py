"""Capacity-factor and demand caches of the firm-LCOE LP (skip unless inputs.py --build has run)."""
import os
import unittest

from scripts.analysis.firm_lcoe import inputs as I


@unittest.skipUnless(os.path.exists(I.CF_CACHE) and os.path.exists(I.DEMAND_CACHE), 'run python inputs.py --build first')
class TestInputs(unittest.TestCase):
    def test_cf_statistics(self):
        d = I.load(step=1, solar_scale=1.0)
        self.assertEqual(d['cf'].shape, (41, 8760, 3))
        m = d['cf'].mean(axis=(0, 1))
        self.assertAlmostEqual(m[0], 0.120, delta=0.005)
        self.assertAlmostEqual(m[1], 0.374, delta=0.01)
        self.assertAlmostEqual(m[2], 0.517, delta=0.01)
        self.assertTrue((d['cf'] >= 0).all() and (d['cf'] <= 1).all())

    def test_solar_scale_default(self):
        d = I.load(step=1)
        self.assertAlmostEqual(d['cf'][:, :, 0].mean(), 0.110, delta=0.005)

    def test_demand(self):
        dem = I.build_demand()
        self.assertEqual(dem.shape, (8760,))
        self.assertAlmostEqual(dem.sum() / 1e6, 567.4, delta=0.5)
        self.assertAlmostEqual(dem.max() / 1e3, 99.8, delta=0.2)

    def test_blocks_conserve_energy(self):
        h, b = I.load(years=[2010], step=1), I.load(years=[2010], step=3)
        self.assertEqual(b['cf'].shape, (1, 2920, 3))
        self.assertAlmostEqual(h['cf'].sum(), b['cf'].sum() * 3, 3)
        self.assertAlmostEqual(h['demand'].sum(), b['demand'].sum() * 3, 1)

    def test_slice_year(self):
        d = I.load(years=[1985, 1986], step=6)
        s = I.slice_year(d, 1)
        self.assertEqual(s['cf'].shape, (1, 1460, 3))
        self.assertEqual(s['years'], [1986])


if __name__ == '__main__':
    unittest.main()
