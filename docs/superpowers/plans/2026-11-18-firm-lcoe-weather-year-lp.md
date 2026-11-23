# Firm LCOE weather-year LP — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A greenfield single-node GB capacity-expansion LP over 41 weather years that prices the service of meeting the GB demand profile with RE + storage, nuclear (+ storage) and gas CCUS at stated firmness levels, plus a 2024-25 market-evidence layer comparing what renewables and gas bid with the unit cost of shifting a MWh through storage.

**Architecture:** Five small modules under `scripts/analysis/firm_lcoe/`: `inputs.py` (national CF + demand, cached parquet), `costs.py` (DESNZ-anchored annualised costs), `model.py` (gurobipy matrix LP, build/extract/hourly re-check), `run_sweep.py` (CLI sweep writing `results.csv`), `market_bids.py` (2024-25 Modo/Elexon pulls -> `market_bids_2024_25.csv`), `report.py` (one xlsx + one tabbed HTML + README). Spec: `docs/superpowers/specs/2026-11-18-firm-lcoe-weather-year-lp-design.md`.

**Tech Stack:** system Python 3.12 (`C:\Users\ucbqnge\AppData\Local\Programs\Python\Python312\python.exe`), gurobipy 13, numpy, pandas 3, scipy.sparse, pyarrow, openpyxl, matplotlib 3.10. No pytest in this interpreter: tests use `unittest` (`python -m unittest discover -s scripts/analysis/firm_lcoe/tests -v`).

## Global Constraints

- Real 2024 £, 2030 commissioning costs. AFC = (LCOE − VOM) × 8760 × LF / 1000 in £/kW-yr.
- Solar CF derated by 11/12 (41-yr mean 11.0%); wind unscaled. `solar_scale=1.0` is the sensitivity.
- Feb 29 dropped; every weather year is 8,760 h. Default block = 3 h (`--step 3`).
- Storage cyclic within each weather year; no state carried across years.
- Firmness f: per year unserved ≤ (1 − f) × that year's demand; f = 1.0 sets unserved to zero.
- Backup case: unabated CCGT energy ≤ 5% of each year's demand.
- Nuclear flexible to zero (must-run switch default off).
- Outputs under `resources/analysis/firm_lcoe/`. One workbook, one HTML, one `results.csv`, one `market_bids_2024_25.csv`, `README.md`.
- No git commits unless the user asks (user rule). No new packages.
- Modo token read from `scripts/analysis/bidding_behaviour/.env` by the existing `fetch_modo.get_token()`; never printed.

---

## File structure

```
scripts/analysis/firm_lcoe/
  __init__.py          empty
  inputs.py            build_cf(), build_demand(), load(years, step, solar_scale) -> dict
  costs.py             crf, afc_from_lcoe, two_point, generation(opt), stores(opt), lcos(), DEFAULT_OPT
  model.py             CASES, build_lp(), extract(), recheck_hourly()
  run_sweep.py         CLI -> resources/analysis/firm_lcoe/results.csv
  market_bids.py       CLI -> resources/analysis/firm_lcoe/market_bids_2024_25.csv (+ inputs/market/*.csv caches)
  report.py            CLI -> firm_lcoe.xlsx, firm_lcoe_report.html, README.md
  tests/test_costs.py, tests/test_inputs.py, tests/test_model.py
resources/analysis/firm_lcoe/
  inputs/national_cf.parquet, inputs/demand.parquet, inputs/market/*.csv
  results.csv, market_bids_2024_25.csv, firm_lcoe.xlsx, firm_lcoe_report.html, README.md, figures/*.png
```

---

### Task 1: costs.py

**Files:** Create `scripts/analysis/firm_lcoe/__init__.py` (empty), `scripts/analysis/firm_lcoe/costs.py`, `scripts/analysis/firm_lcoe/tests/__init__.py` (empty), `scripts/analysis/firm_lcoe/tests/test_costs.py`.

**Interfaces produced:**
- `DEFAULT_OPT: dict(battery_e=120.0, nuclear_lcoe=140.0, gas_p=71.0, carbon=120.0, solar_scale=11/12, nuclear_must_run=0.0)`
- `generation(opt) -> {name: dict(afc, vom, avail)}` for `solar, onshore, offshore, nuclear, gas_ccus, ccgt` (afc £/kW-yr, vom £/MWh, avail fraction or None for VRE)
- `stores(opt) -> {name: dict(afc_p_in, afc_p_out, afc_e, eta_in, eta_out, vom, symmetric)}` for `battery, ldes, h2`
- `lcos(store, cycles, duration_h, charge_price, opt) -> £/MWh discharged`
- `crf(r, n)`, `afc_from_lcoe(lcoe, lf, vom=0)`, `two_point(l1, lf1, l2, lf2) -> (afc, vom)`, `ccgt_vom(gas_p, carbon)`

- [ ] **Step 1: Write the failing test** `tests/test_costs.py`

```python
import unittest, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import costs as C


class TestCosts(unittest.TestCase):
    def test_afc_reproduces_desnz(self):
        g = C.generation(C.DEFAULT_OPT)
        self.assertAlmostEqual(g['solar']['afc'], 63.07, 1)
        self.assertAlmostEqual(g['onshore']['afc'], 188.0, 0)
        self.assertAlmostEqual(g['offshore']['afc'], 442.0, 0)
        self.assertAlmostEqual(g['nuclear']['afc'], 1009.2, 0)
        # inverse: LCOE at the DESNZ load factor comes back
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
        self.assertAlmostEqual(s['ldes']['afc_p_in'], 114, delta=1)
        self.assertAlmostEqual(s['ldes']['afc_e'], 5.2, delta=0.1)
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
        # battery 2 h, 300 cycles, charge at 20 £/MWh: AFC_p/(cycles*h) + AFC_e/cycles + p/RTE
        s = C.stores(C.DEFAULT_OPT)['battery']
        exp = (s['afc_p_in'] * 1000 / (300 * 2) + s['afc_e'] * 1000 / 300 + 20 / 0.86)
        self.assertAlmostEqual(C.lcos('battery', 300, 2, 20, C.DEFAULT_OPT), exp, 6)


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest scripts.analysis.firm_lcoe.tests.test_costs -v` (from repo root)
Expected: FAIL with `ModuleNotFoundError: No module named 'costs'`

- [ ] **Step 3: Write `costs.py`**

```python
"""Cost table for the firm-LCOE LP. REAL 2024 GBP, 2030 commissioning.

Principle: every generation input is a published DESNZ 2025 LCOE and its load factor, so a MWh
taken straight from the plant costs exactly the DESNZ figure (AFC = (LCOE - VOM) x 8760 x LF / 1000,
GBP/kW-yr). Storage is annualised capex at CEPA 2025 hurdle rates. Sources: DESNZ Electricity
Generation Costs 2025 (Jan 2026) and Annex A; NAO (HPC/SZC) for nuclear; NREL 2025, BNEF Dec 2025,
LCP Delta/Regen 2024, Royal Society 2023 for storage (see spec 2026-11-18).
"""
import math

DEFAULT_OPT = dict(battery_e=120.0, nuclear_lcoe=140.0, gas_p=71.0, carbon=120.0,
                   solar_scale=11.0 / 12.0, nuclear_must_run=0.0)

# CEPA 2025 pre-tax real hurdle rates
R = dict(solar=0.076, onshore=0.076, offshore=0.089, gas=0.089, bess=0.089, phes=0.089, novel=0.101)

# DESNZ 2025 LCOE (GBP/MWh) and net load factors, 2030 commissioning
DESNZ = dict(solar=(60.0, 0.12), onshore=(58.0, 0.37), offshore=(103.0, 0.49),
             gas_ccus=((105.0, 0.88), (181.0, 0.30)),       # two load-factor points
             ccgt_fixed_per_mwh=15.0 + 3.0, ccgt_lf=0.93)   # construction 15 + FOM 3 at 93 %
NUCLEAR_VOM = 12.0          # fuel + VOM GBP/MWh
NUCLEAR_LF = 0.90
AVAIL = dict(nuclear=0.90, gas_ccus=0.83, ccgt=0.93)

# gas coefficients (DESNZ Annex A, HHV): 1 p/therm = 0.3412 GBP/MWh_th; CCGT 54 % -> 0.632 GBP/MWh_e per p/th
CCGT_FUEL_COEF, CCGT_EF, CCGT_VOM = 0.632, 0.339, 5.0

STORE_CAPEX = dict(
    battery=dict(p=120.0, e=120.0, life=15, r=R['bess'], fom=0.025, rte=0.86),
    ldes=dict(p=1100.0, e=50.0, life=40, r=R['phes'], fom=0.01, rte=0.76),
    h2=dict(ely=1000.0, ely_eff=0.70, ely_life=25, ely_r=R['novel'], ely_fom=0.03,
            cav=0.6, cav_life=30, cav_r=R['gas'], cav_fom=0.01,
            tb=887.0, tb_eff=0.55, tb_life=25, tb_r=R['novel'], tb_fom_abs=14.0, vom=2.0),
)


def crf(r, n):
    return r * (1 + r) ** n / ((1 + r) ** n - 1)


def afc_from_lcoe(lcoe, lf, vom=0.0):
    """GBP/kW-yr fixed charge that reproduces `lcoe` at load factor `lf`."""
    return (lcoe - vom) * 8760 * lf / 1000.0


def two_point(l1, lf1, l2, lf2):
    """Fixed (GBP/kW-yr) and variable (GBP/MWh) parts from two (LCOE, LF) points."""
    h1, h2 = 8760 * lf1, 8760 * lf2
    fixed = (l2 - l1) / (1 / h2 - 1 / h1)          # GBP/MW-yr
    return fixed / 1000.0, l1 - fixed / h1


def ccgt_vom(gas_p, carbon):
    return CCGT_VOM + CCGT_FUEL_COEF * gas_p + CCGT_EF * carbon


def generation(opt=DEFAULT_OPT):
    ccus_afc, ccus_vom = two_point(*DESNZ['gas_ccus'][0], *DESNZ['gas_ccus'][1])
    return {
        'solar': dict(afc=afc_from_lcoe(*DESNZ['solar']), vom=0.0, avail=None),
        'onshore': dict(afc=afc_from_lcoe(*DESNZ['onshore']), vom=0.0, avail=None),
        'offshore': dict(afc=afc_from_lcoe(*DESNZ['offshore']), vom=0.0, avail=None),
        'nuclear': dict(afc=afc_from_lcoe(opt['nuclear_lcoe'], NUCLEAR_LF, NUCLEAR_VOM), vom=NUCLEAR_VOM, avail=AVAIL['nuclear']),
        'gas_ccus': dict(afc=ccus_afc, vom=ccus_vom, avail=AVAIL['gas_ccus']),
        'ccgt': dict(afc=DESNZ['ccgt_fixed_per_mwh'] * 8760 * DESNZ['ccgt_lf'] / 1000.0,
                     vom=ccgt_vom(opt['gas_p'], opt['carbon']), avail=AVAIL['ccgt']),
    }


def stores(opt=DEFAULT_OPT):
    b, l, h = STORE_CAPEX['battery'], STORE_CAPEX['ldes'], STORE_CAPEX['h2']
    out = {
        'battery': dict(afc_p_in=b['p'] * (crf(b['r'], b['life']) + b['fom']), afc_p_out=0.0,
                        afc_e=opt['battery_e'] * (crf(b['r'], b['life']) + b['fom']),
                        eta_in=math.sqrt(b['rte']), eta_out=math.sqrt(b['rte']), vom=0.0, symmetric=True),
        'ldes': dict(afc_p_in=l['p'] * (crf(l['r'], l['life']) + l['fom']), afc_p_out=0.0,
                     afc_e=l['e'] * (crf(l['r'], l['life']) + l['fom']),
                     eta_in=math.sqrt(l['rte']), eta_out=math.sqrt(l['rte']), vom=0.0, symmetric=True),
        'h2': dict(afc_p_in=h['ely'] * (crf(h['ely_r'], h['ely_life']) + h['ely_fom']),
                   afc_p_out=h['tb'] * crf(h['tb_r'], h['tb_life']) + h['tb_fom_abs'],
                   afc_e=h['cav'] * (crf(h['cav_r'], h['cav_life']) + h['cav_fom']),
                   eta_in=h['ely_eff'], eta_out=h['tb_eff'], vom=h['vom'], symmetric=False),
    }
    return out


def lcos(store, cycles, duration_h, charge_price, opt=DEFAULT_OPT):
    """GBP per MWh discharged: power annuity / (cycles x h) + energy annuity / cycles + charging / RTE + VOM.
    For h2 the power annuity is electrolyser + turbine per MW_out (electrolyser sized 1/eta_out...)."""
    s = stores(opt)[store]
    rte = s['eta_in'] * s['eta_out']
    p_afc = s['afc_p_in'] + s['afc_p_out']
    return p_afc * 1000 / (cycles * duration_h) + s['afc_e'] * 1000 / cycles + charge_price / rte + s['vom']


if __name__ == '__main__':
    for k, v in generation().items():
        print(f'{k:10s} AFC {v["afc"]:7.1f} GBP/kW-yr  VOM {v["vom"]:6.1f}  avail {v["avail"]}')
    for k, v in stores().items():
        print(f'{k:10s} P_in {v["afc_p_in"]:6.1f} P_out {v["afc_p_out"]:6.1f} E {v["afc_e"]:6.2f} GBP/kW(h)-yr  eta {v["eta_in"]:.3f}/{v["eta_out"]:.3f}')
```

- [ ] **Step 4: Run tests**  `python -m unittest scripts.analysis.firm_lcoe.tests.test_costs -v` → all 6 PASS. Also `python scripts/analysis/firm_lcoe/costs.py` prints the table (solar 63.1, onshore 188.0, offshore 442.0, nuclear 1009.2, gas_ccus ~303/65.7, ccgt 146.6/91.5).

---

### Task 2: inputs.py

**Files:** Create `scripts/analysis/firm_lcoe/inputs.py`, `scripts/analysis/firm_lcoe/tests/test_inputs.py`.

**Interfaces produced:**
- `YEARS = list(range(1985, 2026))`, `TECHS = ['solar', 'onshore', 'offshore']`
- `build_cf(years=YEARS, force=False) -> DataFrame[year, hour, solar, onshore, offshore]` (raw, unscaled), cached at `resources/analysis/firm_lcoe/inputs/national_cf.parquet`
- `build_demand(force=False) -> np.ndarray (8760,)` MW, cached at `inputs/demand.parquet`
- `load(years=YEARS, step=3, solar_scale=11/12) -> dict(cf=(Y,T,3) ndarray, demand=(T,) ndarray, years=list, T=int, dt=float, techs=TECHS)`
- `slice_year(data, i) -> dict` same shape with Y = 1

- [ ] **Step 1: Write the failing test** `tests/test_inputs.py` (uses the cache; skipped until built)

```python
import unittest, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import inputs as I


@unittest.skipUnless(os.path.exists(I.CF_CACHE) and os.path.exists(I.DEMAND_CACHE), 'run python inputs.py --build first')
class TestInputs(unittest.TestCase):
    def test_cf_statistics(self):
        d = I.load(step=1, solar_scale=1.0)
        self.assertEqual(d['cf'].shape, (41, 8760, 3))
        m = d['cf'].mean(axis=(0, 1))
        self.assertAlmostEqual(m[0], 0.120, delta=0.005)   # solar raw
        self.assertAlmostEqual(m[1], 0.374, delta=0.01)    # onshore
        self.assertAlmostEqual(m[2], 0.517, delta=0.01)    # offshore
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
        self.assertAlmostEqual(h['cf'].sum() * 1, b['cf'].sum() * 3, 3)
        self.assertAlmostEqual(h['demand'].sum(), b['demand'].sum() * 3, 1)

    def test_slice_year(self):
        d = I.load(years=[1985, 1986], step=6)
        s = I.slice_year(d, 1)
        self.assertEqual(s['cf'].shape, (1, 1460, 3))
        self.assertEqual(s['years'], [1986])
```

- [ ] **Step 2: Run** → `OK (skipped=5)` before cache exists.

- [ ] **Step 3: Write `inputs.py`**

```python
"""National hourly capacity factors (41 weather years, 3 VRE techs) and GB demand for the firm-LCOE LP.

CF = row sum of site-level MW (resources/renewable/profiles/<tech>_<wy>.csv, atlite REPD fleet) divided by
fleet nameplate from resources/renewable/<tech>_sites.csv (names normalised; unmatched columns fall back
to their series maximum). Feb 29 dropped. Demand = GB sum of resources/demand/HT50_w2010_base_profile.csv
(FES 2025 Holistic Transition 2050; identical for every weather year).

    python scripts/analysis/firm_lcoe/inputs.py --build      # (re)build the parquet caches, ~minutes
"""
import argparse, os, re
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
PROF = os.path.join(ROOT, 'resources', 'renewable', 'profiles')
SITES_DIR = os.path.join(ROOT, 'resources', 'renewable')
DEMAND_FILE = os.path.join(ROOT, 'resources', 'demand', 'HT50_w2010_base_profile.csv')
OUT = os.path.join(ROOT, 'resources', 'analysis', 'firm_lcoe', 'inputs')
CF_CACHE = os.path.join(OUT, 'national_cf.parquet')
DEMAND_CACHE = os.path.join(OUT, 'demand.parquet')

YEARS = list(range(1985, 2026))
TECHS = ['solar', 'onshore', 'offshore']
FILE_TECH = dict(solar='solar_pv', onshore='wind_onshore', offshore='wind_offshore')
SOLAR_SCALE = 11.0 / 12.0


def norm(s):
    return re.sub(r'\s+', ' ', re.sub(r'\(REPD\)', '', str(s))).strip().lower()


def _nameplate(tech):
    sites = pd.read_csv(os.path.join(SITES_DIR, f'{FILE_TECH[tech]}_sites.csv'))
    return sites.groupby(sites['site_name'].map(norm))['capacity_mw'].sum()


def national_cf_year(tech, year, cap=None):
    cap = _nameplate(tech) if cap is None else cap
    df = pd.read_csv(os.path.join(PROF, f'{FILE_TECH[tech]}_{year}.csv'), index_col=0)
    df.index = pd.to_datetime(df.index)
    names = [norm(c) for c in df.columns]
    matched = np.array([n in cap.index for n in names])
    nameplate = float(sum(cap[n] for n, m in zip(names, matched) if m)) + float(df.loc[:, ~matched].max().sum())
    cf = df.sum(axis=1) / nameplate
    cf = cf[~((cf.index.month == 2) & (cf.index.day == 29))]
    if len(cf) != 8760:
        raise ValueError(f'{tech} {year}: {len(cf)} rows after dropping Feb 29')
    return cf.clip(0, 1).to_numpy(dtype=float)


def build_cf(years=YEARS, force=False):
    if os.path.exists(CF_CACHE) and not force:
        df = pd.read_parquet(CF_CACHE)
        if set(years) <= set(df['year'].unique()):
            return df
    os.makedirs(OUT, exist_ok=True)
    caps = {t: _nameplate(t) for t in TECHS}
    frames = []
    for y in years:
        cols = {t: national_cf_year(t, y, caps[t]) for t in TECHS}
        frames.append(pd.DataFrame(dict(year=y, hour=np.arange(8760), **cols)))
        print(f'  cf {y}: ' + ' '.join(f'{t} {cols[t].mean():.3f}' for t in TECHS), flush=True)
    df = pd.concat(frames, ignore_index=True)
    df.to_parquet(CF_CACHE, index=False)
    return df


def build_demand(force=False):
    if os.path.exists(DEMAND_CACHE) and not force:
        return pd.read_parquet(DEMAND_CACHE)['demand_mw'].to_numpy()
    os.makedirs(OUT, exist_ok=True)
    d = pd.read_csv(DEMAND_FILE, index_col=0)
    dem = d.sum(axis=1).to_numpy(dtype=float)
    if len(dem) != 8760:
        raise ValueError(f'demand has {len(dem)} rows')
    pd.DataFrame(dict(hour=np.arange(8760), demand_mw=dem)).to_parquet(DEMAND_CACHE, index=False)
    return dem


def _blocks(a, step):
    """Average consecutive `step` hours along the hour axis (axis 1 for (Y,8760,...) arrays, axis 0 for 1-D)."""
    if step == 1:
        return a
    if a.ndim == 1:
        return a.reshape(8760 // step, step).mean(axis=1)
    return a.reshape(a.shape[0], 8760 // step, step, *a.shape[2:]).mean(axis=2)


def load(years=YEARS, step=3, solar_scale=SOLAR_SCALE):
    if 8760 % step:
        raise ValueError('step must divide 8760')
    df = build_cf(years)
    df = df[df['year'].isin(years)].sort_values(['year', 'hour'])
    cf = df[TECHS].to_numpy(dtype=float).reshape(len(years), 8760, 3)
    cf[:, :, 0] *= solar_scale
    dem = build_demand()
    return dict(cf=_blocks(cf, step), demand=_blocks(dem, step), years=list(years), T=8760 // step,
                dt=float(step), techs=TECHS)


def slice_year(data, i):
    return dict(data, cf=data['cf'][i:i + 1], years=[data['years'][i]])


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--build', action='store_true')
    ap.add_argument('--force', action='store_true')
    a = ap.parse_args()
    if a.build:
        df = build_cf(force=a.force)
        dem = build_demand(force=a.force)
        print(df.groupby('year')[TECHS].mean().describe().round(3))
        print(f'41-yr mean CF: ' + ' '.join(f'{t} {df[t].mean():.3f}' for t in TECHS))
        print(f'demand {dem.sum()/1e6:.1f} TWh, peak {dem.max()/1e3:.1f} GW, min {dem.min()/1e3:.1f} GW')
```

- [ ] **Step 4: Build the cache and run tests**

Run: `python scripts/analysis/firm_lcoe/inputs.py --build` (several minutes: 123 wide CSVs). Expected last lines: `41-yr mean CF: solar 0.120 onshore 0.374 offshore 0.517` (± 0.005) and `demand 567.4 TWh, peak 99.8 GW, min 38.1 GW`.
Run: `python -m unittest scripts.analysis.firm_lcoe.tests.test_inputs -v` → 5 PASS.

---

### Task 3: model.py

**Files:** Create `scripts/analysis/firm_lcoe/model.py`, `scripts/analysis/firm_lcoe/tests/test_model.py`.

**Interfaces consumed:** `costs.generation/stores/DEFAULT_OPT`, `inputs.slice_year`, data dict from `inputs.load`.

**Interfaces produced:**
- `CASES: dict[name -> dict(vre=list, disp=list, stores=list, gas_share=float|None, firmness=list)]`
- `build_lp(data, case, firmness, opt, fixed_caps=None, voll=None, threads=8) -> (gurobipy.Model, handles dict)`
- `extract(m, h, data, case, firmness, opt) -> dict` (one results row, keys listed in code)
- `recheck_hourly(data_hourly, caps, case, opt) -> dict(lole_h_mean, lole_h_max, unserved_twh_mean, unserved_twh_max, worst_year)`
- `solve(m) -> status str`

- [ ] **Step 1: Write the failing test** `tests/test_model.py`

```python
import unittest, os, sys, math
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import costs as C
import model as M


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
        soc = 1200 / eta                   # MWh needed at dusk
        charge = soc / eta                 # MWh drawn in 12 h
        self.assertAlmostEqual(r['cap_solar_mw'], 100 + charge / 12, delta=1.0)
        self.assertAlmostEqual(r['battery_e_mwh'], soc, delta=5.0)
        self.assertAlmostEqual(r['battery_p_mw'], charge / 12, delta=1.0)
        self.assertAlmostEqual(r['curtail_share'], 0.0, delta=0.01)
        self.assertAlmostEqual(r['unserved_twh'], 0.0, 6)
        # cost identity: objective / delivered == firm_lcoe
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

    def test_recheck_hourly_fixed_caps(self):
        data = toy()
        case = dict(vre=['solar'], disp=[], stores=['battery'], gas_share=None)
        caps = dict(cap_solar_mw=216.3, battery_p_mw=116.3, battery_e_mwh=1294.0)
        rc = M.recheck_hourly(data, caps, case, C.DEFAULT_OPT)
        self.assertLess(rc['lole_h_max'], 1)
        caps['battery_e_mwh'] = 600.0
        rc = M.recheck_hourly(data, caps, case, C.DEFAULT_OPT)
        self.assertGreater(rc['lole_h_max'], 5)
```

- [ ] **Step 2: Run** → FAIL `No module named 'model'`.

- [ ] **Step 3: Write `model.py`**

```python
"""Single-node greenfield capacity-expansion LP over weather years (gurobipy matrix API).

Periods are laid out as one flat axis of length N = Y x T (year-major). Sparse matrices handle the
per-year cyclic storage dynamics (permutation P) and per-year sums (Yagg). All capacity in MW / MWh,
costs in GBP; the objective is the mean annual cost over the weather years.
"""
import time
import numpy as np
import scipy.sparse as sp
import gurobipy as gp
from gurobipy import GRB

import costs as C

VRE_ALL = ['solar', 'onshore', 'offshore']
STORES_ALL = ['battery', 'ldes', 'h2']
CASES = {
    're_storage': dict(vre=VRE_ALL, disp=[], stores=STORES_ALL, gas_share=None, firmness=[0.90, 0.95, 0.99, 0.999, 1.0]),
    're_storage_gas5': dict(vre=VRE_ALL, disp=['ccgt'], stores=STORES_ALL, gas_share=0.05, firmness=[1.0]),
    'nuclear_storage': dict(vre=[], disp=['nuclear'], stores=['battery', 'ldes'], gas_share=None, firmness=[0.99, 1.0]),
    'gas_ccus': dict(vre=[], disp=['gas_ccus'], stores=[], gas_share=None, firmness=[1.0]),
    'all_tech': dict(vre=VRE_ALL, disp=['nuclear', 'gas_ccus'], stores=STORES_ALL, gas_share=None, firmness=[1.0]),
}


def _mats(Y, T):
    N = Y * T
    idx = np.arange(N)
    prev = idx - 1
    prev[idx % T == 0] += T                     # year start links to the same year's last period
    P = sp.csr_matrix((np.ones(N), (idx, prev)), shape=(N, N))
    Yagg = sp.kron(sp.eye(Y, format='csr'), sp.csr_matrix(np.ones((1, T))), format='csr')
    ones = sp.csr_matrix(np.ones((N, 1)))
    return N, P, Yagg, ones


def build_lp(data, case, firmness, opt=C.DEFAULT_OPT, fixed_caps=None, voll=None, threads=8):
    cf, dem, dt = data['cf'], data['demand'], data['dt']
    Y, T = cf.shape[0], cf.shape[1]
    N, P, Yagg, ones = _mats(Y, T)
    dem_rep = np.tile(dem, Y)
    gen, sto = C.generation(opt), C.stores(opt)
    vre, disp, stores = list(case['vre']), list(case['disp']), list(case['stores'])

    m = gp.Model('firm_lcoe')
    m.Params.OutputFlag = 0
    m.Params.Threads = threads
    if N > 20000:
        m.Params.Method = 2
        m.Params.Crossover = 0
    h = dict(vre=vre, disp=disp, stores=stores, N=N, Y=Y, T=T, dt=dt, dem_rep=dem_rep)

    # ---- capacity variables
    cap_vre = m.addMVar(len(vre), lb=0.0, name='cap_vre') if vre else None
    cap_disp = {k: m.addMVar(1, lb=0.0, name=f'cap_{k}') for k in disp}
    scap = {}
    for s in stores:
        scap[s] = dict(p_in=m.addMVar(1, lb=0.0, name=f'{s}_p_in'), e=m.addMVar(1, lb=0.0, name=f'{s}_e'))
        scap[s]['p_out'] = scap[s]['p_in'] if sto[s]['symmetric'] else m.addMVar(1, lb=0.0, name=f'{s}_p_out')
    if fixed_caps is not None:
        for i, k in enumerate(vre):
            v = fixed_caps.get(f'cap_{k}_mw', 0.0); cap_vre[i].lb = cap_vre[i].ub = v
        for k in disp:
            v = fixed_caps.get(f'cap_{k}_mw', 0.0); cap_disp[k].lb = cap_disp[k].ub = v
        for s in stores:
            for key, nm in (('p_in', f'{s}_p_mw'), ('e', f'{s}_e_mwh'), ('p_out', f'{s}_p_out_mw')):
                if key == 'p_out' and sto[s]['symmetric']:
                    continue
                v = fixed_caps.get(nm, fixed_caps.get(f'{s}_p_mw', 0.0)); scap[s][key].lb = scap[s][key].ub = v

    # ---- period variables
    unserved = m.addMVar(N, lb=0.0, ub=(0.0 if (firmness >= 1.0 and voll is None) else GRB.INFINITY), name='unserved')
    vre_used = m.addMVar(N, lb=0.0, name='vre_used') if vre else None
    g = {k: m.addMVar(N, lb=0.0, name=f'g_{k}') for k in disp}
    ch = {s: m.addMVar(N, lb=0.0, name=f'ch_{s}') for s in stores}
    dis = {s: m.addMVar(N, lb=0.0, name=f'dis_{s}') for s in stores}
    soc = {s: m.addMVar(N, lb=0.0, name=f'soc_{s}') for s in stores}

    # ---- constraints
    balance = unserved
    if vre:
        CF = cf[:, :, [VRE_ALL.index(k) for k in vre]].reshape(N, len(vre))
        h['CF'] = CF
        m.addConstr(vre_used <= CF @ cap_vre, name='vre_avail')
        balance = balance + vre_used
    for k in disp:
        m.addConstr(g[k] <= gen[k]['avail'] * (ones @ cap_disp[k]), name=f'avail_{k}')
        if k == 'nuclear' and opt.get('nuclear_must_run', 0.0) > 0:
            m.addConstr(g[k] >= opt['nuclear_must_run'] * gen[k]['avail'] * (ones @ cap_disp[k]), name='must_run')
        balance = balance + g[k]
    for s in stores:
        st = sto[s]
        m.addConstr(soc[s] == P @ soc[s] + dt * st['eta_in'] * ch[s] - (dt / st['eta_out']) * dis[s], name=f'soc_{s}')
        m.addConstr(soc[s] <= ones @ scap[s]['e'], name=f'e_{s}')
        m.addConstr(ch[s] <= ones @ scap[s]['p_in'], name=f'pin_{s}')
        m.addConstr(dis[s] <= ones @ scap[s]['p_out'], name=f'pout_{s}')
        balance = balance + dis[s] - ch[s]
    m.addConstr(balance == dem_rep, name='balance')
    if firmness < 1.0 and voll is None:
        m.addConstr(Yagg @ unserved <= (1.0 - firmness) * (Yagg @ dem_rep), name='firmness')
    if case.get('gas_share') is not None and 'ccgt' in disp:
        m.addConstr(Yagg @ g['ccgt'] <= case['gas_share'] * (Yagg @ dem_rep), name='gas_share')

    # ---- objective: mean annual cost
    fixed = 0
    if vre:
        fixed = fixed + sum(1000.0 * gen[k]['afc'] * cap_vre[i] for i, k in enumerate(vre))
    for k in disp:
        fixed = fixed + 1000.0 * gen[k]['afc'] * cap_disp[k]
    for s in stores:
        st = sto[s]
        fixed = fixed + 1000.0 * st['afc_p_in'] * scap[s]['p_in'] + 1000.0 * st['afc_e'] * scap[s]['e']
        if not st['symmetric']:
            fixed = fixed + 1000.0 * st['afc_p_out'] * scap[s]['p_out']
    var = 0
    for k in disp:
        var = var + dt * gen[k]['vom'] * g[k].sum()
    for s in stores:
        if sto[s]['vom']:
            var = var + dt * sto[s]['vom'] * dis[s].sum()
    obj = fixed + var / Y                 # fixed is already an annual cost; var sums over Y years
    if voll is not None:
        obj = obj + voll * dt * unserved.sum() / Y
    m.setObjective(obj, GRB.MINIMIZE)
    h.update(cap_vre=cap_vre, cap_disp=cap_disp, scap=scap, unserved=unserved, vre_used=vre_used, g=g, ch=ch, dis=dis, soc=soc)
    return m, h


def solve(m):
    t0 = time.time()
    m.optimize()
    m._solve_time = time.time() - t0
    return {GRB.OPTIMAL: 'optimal', GRB.INFEASIBLE: 'infeasible', GRB.UNBOUNDED: 'unbounded',
            GRB.SUBOPTIMAL: 'suboptimal'}.get(m.Status, f'status_{m.Status}')


def _x(v):
    return float(np.asarray(v.X).sum()) if v is not None else 0.0


def extract(m, h, data, case, firmness, opt=C.DEFAULT_OPT):
    gen, sto = C.generation(opt), C.stores(opt)
    Y, dt = h['Y'], h['dt']
    scale = dt / 1e6 / Y                     # MW-periods -> TWh per year
    r = dict(firmness=firmness, n_years=Y, step_h=dt, status='optimal', solve_time_s=round(getattr(m, '_solve_time', 0.0), 1),
             demand_twh=float(h['dem_rep'].sum()) * scale)
    r['unserved_twh'] = _x(h['unserved']) * scale
    r['delivered_twh'] = r['demand_twh'] - r['unserved_twh']
    cost = {}
    avail_twh = used_twh = 0.0
    for i, k in enumerate(h['vre']):
        c = float(h['cap_vre'][i].X)
        r[f'cap_{k}_mw'] = c
        avail_k = float(h['CF'][:, i].sum()) * c * scale
        r[f'avail_{k}_twh'] = avail_k
        avail_twh += avail_k
        cost[f'cost_{k}'] = 1000.0 * gen[k]['afc'] * c
    if h['vre']:
        used_twh = _x(h['vre_used']) * scale
    r['vre_used_twh'] = used_twh
    r['vre_avail_twh'] = avail_twh
    r['curtail_share'] = (1.0 - used_twh / avail_twh) if avail_twh > 0 else 0.0
    for k in h['disp']:
        c = float(h['cap_disp'][k].X[0]); e = _x(h['g'][k]) * scale
        r[f'cap_{k}_mw'] = c; r[f'gen_{k}_twh'] = e
        r[f'lf_{k}'] = e * 1e6 / (c * 8760) if c > 0 else 0.0
        cost[f'cost_{k}_fixed'] = 1000.0 * gen[k]['afc'] * c
        cost[f'cost_{k}_var'] = gen[k]['vom'] * e * 1e6
    for s in h['stores']:
        st = sto[s]; sc = h['scap'][s]
        p_in, e = float(sc['p_in'].X[0]), float(sc['e'].X[0])
        p_out = p_in if st['symmetric'] else float(sc['p_out'].X[0])
        d_twh = _x(h['dis'][s]) * scale
        r[f'{s}_p_mw'] = p_in; r[f'{s}_e_mwh'] = e; r[f'{s}_discharge_twh'] = d_twh
        if not st['symmetric']:
            r[f'{s}_p_out_mw'] = p_out
        r[f'{s}_duration_h'] = e / p_out if p_out > 0 else 0.0
        r[f'{s}_cycles_yr'] = d_twh * 1e6 / e if e > 0 else 0.0
        cost[f'cost_{s}'] = 1000.0 * (st['afc_p_in'] * p_in + st['afc_e'] * e + (0.0 if st['symmetric'] else st['afc_p_out'] * p_out)) \
            + st['vom'] * d_twh * 1e6
    r.update(cost)
    r['cost_total_gbp_yr'] = float(m.ObjVal) if hasattr(m, 'ObjVal') else sum(cost.values())
    r['cost_vre_curtailed'] = sum(v for k, v in cost.items() if k in [f'cost_{t}' for t in h['vre']]) * r['curtail_share']
    r['firm_lcoe'] = r['cost_total_gbp_yr'] / (r['delivered_twh'] * 1e6) if r['delivered_twh'] > 0 else float('nan')
    return r


def recheck_hourly(data_hourly, caps, case, opt=C.DEFAULT_OPT, voll=1e4, threads=4):
    """Fixed-capacity hourly dispatch per weather year; returns LOLE (hours with unserved > 1 MW) stats."""
    import inputs as I
    lole, uns = [], []
    for i in range(len(data_hourly['years'])):
        d = I.slice_year(data_hourly, i)
        m, h = build_lp(d, case, 0.0, opt, fixed_caps=caps, voll=voll, threads=threads)
        solve(m)
        u = np.asarray(h['unserved'].X)
        lole.append(int((u > 1.0).sum())); uns.append(float(u.sum()) * d['dt'] / 1e6)
    lole, uns = np.array(lole), np.array(uns)
    return dict(lole_h_mean=float(lole.mean()), lole_h_max=int(lole.max()), unserved_twh_mean=float(uns.mean()),
                unserved_twh_max=float(uns.max()), worst_year=int(data_hourly['years'][int(lole.argmax())]))
```

- [ ] **Step 4: Run tests**  `python -m unittest scripts.analysis.firm_lcoe.tests.test_model -v` → 4 PASS (each toy solve < 1 s).

Known numbers for the toy: solar cap 216.3 MW, battery 116.3 MW / 1293.9 MWh, curtailment 0.

---

### Task 4: run_sweep.py and a small-scale smoke run

**Files:** Create `scripts/analysis/firm_lcoe/run_sweep.py`.

**Interfaces consumed:** `inputs.load`, `model.CASES/build_lp/solve/extract/recheck_hourly`, `costs.DEFAULT_OPT`.
**Produces:** `resources/analysis/firm_lcoe/results.csv` — one row per solve; columns = extract() keys + `case, sens, sens_value, lole_h_mean, lole_h_max, unserved_twh_max_hourly, worst_year`.

- [ ] **Step 1: Write `run_sweep.py`**

```python
"""Sweep the firm-LCOE LP over cases x firmness x sensitivities and write results.csv (checkpointed per solve).

    python scripts/analysis/firm_lcoe/run_sweep.py                          # all cases, 41 years, 3-h blocks
    python scripts/analysis/firm_lcoe/run_sweep.py --years 2010 2013 --step 6 --cases re_storage gas_ccus --no-recheck
    python scripts/analysis/firm_lcoe/run_sweep.py --sens all
"""
import argparse, os, sys, time, json
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import inputs as I, costs as C, model as M

OUT = os.path.join(I.ROOT, 'resources', 'analysis', 'firm_lcoe')
RESULTS = os.path.join(OUT, 'results.csv')
# (sensitivity name, value, cases it applies to, firmness)
SENS = [('battery_e', 80.0, ['re_storage'], 1.0), ('battery_e', 200.0, ['re_storage'], 1.0),
        ('nuclear_lcoe', 120.0, ['nuclear_storage', 'all_tech'], 1.0), ('nuclear_lcoe', 160.0, ['nuclear_storage', 'all_tech'], 1.0),
        ('gas_p', 40.0, ['re_storage_gas5'], 1.0), ('gas_p', 150.0, ['re_storage_gas5'], 1.0),
        ('solar_scale', 1.0, ['re_storage'], 1.0)]


def log(msg):
    print(time.strftime('%H:%M:%S'), msg, flush=True)
    with open(os.path.join(OUT, 'run_sweep.log'), 'a', encoding='utf-8') as f:
        f.write(time.strftime('%Y-%m-%d %H:%M:%S ') + msg + '\n')


def one(data, data_h, case_name, f, opt, sens, sens_value, recheck, threads):
    case = M.CASES[case_name]
    t0 = time.time()
    m, h = M.build_lp(data, case, f, opt, threads=threads)
    log(f'{case_name} f={f} {sens}={sens_value}: built {h["N"]} periods, {m.NumVars} vars, {m.NumConstrs} constrs in {time.time()-t0:.0f}s')
    status = M.solve(m)
    if status != 'optimal':
        log(f'  !! {status}')
        return dict(case=case_name, firmness=f, sens=sens, sens_value=sens_value, status=status)
    r = M.extract(m, h, data, case, f, opt)
    r.update(case=case_name, sens=sens, sens_value=sens_value)
    log(f'  firm LCOE {r["firm_lcoe"]:.1f} GBP/MWh, curtail {100*r["curtail_share"]:.1f}%, solve {r["solve_time_s"]}s')
    if recheck:
        rc = M.recheck_hourly(data_h, r, case, opt)
        r.update(lole_h_mean=rc['lole_h_mean'], lole_h_max=rc['lole_h_max'], unserved_twh_max_hourly=rc['unserved_twh_max'], worst_year=rc['worst_year'])
        log(f'  hourly re-check: LOLE mean {rc["lole_h_mean"]:.1f} h, max {rc["lole_h_max"]} h ({rc["worst_year"]})')
    m.dispose()
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cases', nargs='*', default=list(M.CASES))
    ap.add_argument('--firmness', nargs='*', type=float, default=None)
    ap.add_argument('--step', type=int, default=3)
    ap.add_argument('--years', nargs='*', type=int, default=None)
    ap.add_argument('--sens', nargs='*', default=[], help="'all' or names from SENS")
    ap.add_argument('--no-recheck', action='store_true')
    ap.add_argument('--threads', type=int, default=8)
    ap.add_argument('--out', default=RESULTS)
    ap.add_argument('--append', action='store_true')
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    years = a.years or I.YEARS
    data = I.load(years, a.step, C.DEFAULT_OPT['solar_scale'])
    data_h = I.load(years, 1, C.DEFAULT_OPT['solar_scale']) if not a.no_recheck else None
    rows = pd.read_csv(a.out).to_dict('records') if (a.append and os.path.exists(a.out)) else []

    def save():
        pd.DataFrame(rows).to_csv(a.out, index=False)

    for cn in a.cases:
        for f in (a.firmness or M.CASES[cn]['firmness']):
            rows.append(one(data, data_h, cn, f, C.DEFAULT_OPT, 'base', None, not a.no_recheck, a.threads)); save()
    sens = SENS if 'all' in a.sens else [s for s in SENS if s[0] in a.sens]
    for name, val, cases, f in sens:
        opt = dict(C.DEFAULT_OPT, **{name: val})
        d = I.load(years, a.step, opt['solar_scale']) if name == 'solar_scale' else data
        dh = (I.load(years, 1, opt['solar_scale']) if name == 'solar_scale' else data_h) if not a.no_recheck else None
        for cn in cases:
            if cn in a.cases:
                rows.append(one(d, dh, cn, f, opt, name, val, not a.no_recheck, a.threads)); save()
    log(f'done: {len(rows)} rows -> {a.out}')


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: Smoke run** (2 years, 6-h blocks, all cases, with re-check):

`python scripts/analysis/firm_lcoe/run_sweep.py --years 2010 2013 --step 6 --out resources/analysis/firm_lcoe/results_smoke.csv`
Expected: 10 rows, every status `optimal`; sanity: gas_ccus firm LCOE ≈ 303×1000×(peak/0.83)/(demand) + 65.7 ≈ £120-130/MWh; re_storage f=1.0 well above f=0.90; nuclear_storage f=1.0 ≈ £190-260.

- [ ] **Step 3: Scale test** one solve at 41 years / 3-h: `python scripts/analysis/firm_lcoe/run_sweep.py --cases gas_ccus re_storage --firmness 1.0 --no-recheck --out resources/analysis/firm_lcoe/results_scale.csv` and record build/solve time and peak memory (Task Manager / `Get-Process python`). If memory > 3.5 GB or solve > 40 min, fall back to `--step 6` for the full sweep and record that in the README.

- [ ] **Step 4: Full sweep in the background**: `python scripts/analysis/firm_lcoe/run_sweep.py --sens all` (hours). Check `resources/analysis/firm_lcoe/run_sweep.log` on completion; 17 rows expected.

---

### Task 5: market_bids.py (2024-25 market evidence)

**Files:** Create `scripts/analysis/firm_lcoe/market_bids.py`.

**Interfaces consumed:** `scripts/analysis/bidding_behaviour/fetch_modo.py` (`fetch`, `TZ`, `iso`, `months`, `get_token`), `plants.PLANTS`, existing CSVs in `scripts/analysis/bidding_behaviour/data/`, `costs.lcos/stores`.
**Produces:** `resources/analysis/firm_lcoe/market_bids_2024_25.csv` (tidy: `block, metric, group, year, value, unit, source`) and caches `inputs/market/da_hourly_2024_25.csv`, `bod_monthly_2024_25.csv`, `ccgt_hourly_2024_25.csv`.

- [ ] **Step 1: Write `market_bids.py`**

```python
"""2024-25 GB market evidence for the firm-LCOE report: what renewables and gas bid, vs the cost of shifting a MWh.

Blocks written to market_bids_2024_25.csv (tidy):
  A  da_price        N2EX day-ahead hourly: annual mean, negative hours, floor, mean daily spread, cheapest-6h / dearest-6h means
  B  re_bid          BM turn-down bids (pair -1) submitted by representative wind/solar plants, median by plant-year
                     + subsidy arithmetic (ROC value, CfD strike) from constants below
  C  gas             CCGT SRMC from NBP + UKA + CPS; Pembroke/Grain/Saltend/Staythorpe median BM bid/offer; DA price in gas-marginal hours
  D  shift_cost      LCOS curves (GBP/MWh discharged) vs cycles/yr for the LP stores and a 2025 2-h battery, charging at the cheapest-6h price
  E  bess_revenue    realised GB BESS revenue GBP/MW-yr (Modo index)

    python scripts/analysis/firm_lcoe/market_bids.py            # pulls (cached), writes CSV
    python scripts/analysis/firm_lcoe/market_bids.py --no-pull  # rebuild CSV from caches only
"""
import argparse, os, sys
import numpy as np
import pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'bidding_behaviour'))
import costs as C
import fetch_modo as F          # noqa: E402
import plants as PL             # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
OUT = os.path.join(ROOT, 'resources', 'analysis', 'firm_lcoe')
MK = os.path.join(OUT, 'inputs', 'market')
BB = os.path.join(ROOT, 'scripts', 'analysis', 'bidding_behaviour', 'data')
D0, D1 = '2024-01-01', '2026-01-01'
YEARS = [2024, 2025]

EXTRA_PLANTS = {   # bmu: (name, tech, contract)
    'T_GRAI-6': ('Grain', 'Gas CCGT', 'Merchant'), 'T_SCCL-1': ('Saltend', 'Gas CCGT', 'Merchant'),
    'T_STAY-1': ('Staythorpe', 'Gas CCGT', 'Merchant'),
    'T_BEATO-1': ('Beatrice', 'Wind offshore', 'CfD AR1'), 'T_MOWEO-1': ('Moray East', 'Wind offshore', 'CfD AR2'),
    'T_WLNYO-3': ('Walney Ext', 'Wind offshore', 'CfD AR1'), 'T_HOWBO-1': ('Hornsea Two', 'Wind offshore', 'CfD AR3'),
}
PLANTS = {k: (v[0], v[1], v[2]) for k, v in PL.PLANTS.items()} | EXTRA_PLANTS

# nominal GBP. NBP day-ahead: DESNZ Fossil Fuel Price Assumptions 2025 (ICIS): 84 p/th 2024, 94 p/th H1 2025;
# H2 2025 ~78 (Ofgem monthly: Jul 79.3, Sep 79.2) -> 2025 ~86. UKA: NAO 2025 (~37 in 2024); gov.uk civil-penalty
# determination 2026 = 49.41 (12-month mean of Dec-26 futures to 11 Nov 2025). CPS 18 GBP/t. Existing CCGT 50 % HHV.
GAS_CARBON = {2024: dict(nbp_p_th=84.0, uka=37.0), 2025: dict(nbp_p_th=86.0, uka=49.4)}
CPS, EFF_EXISTING, EF_HHV, VOM_CCGT = 18.0, 0.50, 0.184, 4.0
ROC_BUYOUT = {2024: 64.73, 2025: 67.06}            # GBP/ROC (2024/25, 2025/26 obligation years)
ROC_BAND = {'Wind offshore': 1.8, 'Wind onshore': 0.9, 'Solar': 1.4, 'Biomass': 1.0}
MODO_BESS = {2024: 52200.0, 2025: 71600.0}         # GBP/MW-yr, Modo GB BESS index (storage_value/costs.py)


def srmc(year):
    g = GAS_CARBON[year]
    fuel = g['nbp_p_th'] * 0.3412 / EFF_EXISTING
    carbon = (g['uka'] + CPS) * EF_HHV / EFF_EXISTING
    return fuel, carbon, fuel + carbon + VOM_CCGT


def da_hourly(pull=True):
    f = os.path.join(MK, 'da_hourly_2024_25.csv')
    if os.path.exists(f) or not pull:
        d = pd.read_csv(f); d['t'] = pd.to_datetime(d['t'], utc=True).dt.tz_convert('Europe/London'); return d
    p = F.fetch('/gb/n2ex/day-ahead-hourly/prices', {'date_from': f'{D0}T00:00:00', 'date_to': f'{D1}T00:00:00', 'timezone': F.TZ})
    p['t'] = F.to_london(p['start_time']); p['price'] = pd.to_numeric(p['price'], errors='coerce')
    p = p[p.t < pd.Timestamp(D1, tz='Europe/London')][['t', 'price']].dropna().sort_values('t')
    os.makedirs(MK, exist_ok=True); p.to_csv(f, index=False)
    return p


def bod_monthly(pull=True):
    f = os.path.join(MK, 'bod_monthly_2024_25.csv')
    if os.path.exists(f) or not pull:
        return pd.read_csv(f)
    rows = []
    for bmu, (name, tech, contract) in PLANTS.items():
        for m0, m1 in F.months(pd.Timestamp(D0).date(), pd.Timestamp(D1).date()):
            d1 = min(m1, m0 + pd.Timedelta(days=7).to_pytimedelta())
            try:
                b = F.fetch('/gb/elexon/physical/bod', {'date_from': F.iso(m0), 'date_to': F.iso(d1), 'bm_unit': bmu, 'timezone': F.TZ})
            except RuntimeError as e:
                print(f'[warn] {bmu} {m0:%Y-%m}: {e}'); continue
            if b.empty:
                continue
            for c in ('bid', 'offer', 'pair_id'):
                b[c] = pd.to_numeric(b[c], errors='coerce')
            td = b[(b.pair_id == -1) & (b.bid.abs() < 2000)].bid
            tu = b[(b.pair_id == 1) & (b.offer.abs() < 2000)].offer
            rows.append(dict(bmu=bmu, name=name, tech=tech, contract=contract, yr=m0.year, mo=m0.month,
                             turn_down_bid=td.median(), turn_up_offer=tu.median(), n=len(b)))
            print(f'  bod {name:<12} {m0:%Y-%m} bid {td.median():8.1f} offer {tu.median() if len(tu) else float("nan"):8.1f} n={len(b)}', flush=True)
    df = pd.DataFrame(rows); os.makedirs(MK, exist_ok=True); df.to_csv(f, index=False)
    return df


def ccgt_hourly(pull=True):
    f = os.path.join(MK, 'ccgt_hourly_2024_25.csv')
    if os.path.exists(f) or not pull:
        d = pd.read_csv(f); d['t'] = pd.to_datetime(d['t'], utc=True); return d
    recs = []
    for m0, m1 in F.months(pd.Timestamp(D0).date(), pd.Timestamp(D1).date()):
        g = F.fetch('/gb/elexon/system/fuelhh', {'publish_date_from': F.iso(m0), 'publish_date_to': F.iso(m1), 'timezone': F.TZ})
        if g.empty:
            continue
        g = g[g['fuel_type'].str.upper() == 'CCGT'].copy()
        g['t'] = pd.to_datetime(g['start_time'], utc=True).dt.floor('h')
        g['generation'] = pd.to_numeric(g['generation'], errors='coerce')
        recs.append(g.groupby('t').generation.mean().rename('ccgt_mw'))
        print(f'  fuelhh {m0:%Y-%m}: {len(g)} CCGT rows', flush=True)
    d = pd.concat(recs).groupby(level=0).mean().reset_index()
    os.makedirs(MK, exist_ok=True); d.to_csv(f, index=False)
    return d


def build(pull=True):
    rows = []
    add = lambda block, metric, group, year, value, unit, source: rows.append(dict(block=block, metric=metric, group=group, year=year, value=round(float(value), 2), unit=unit, source=source))
    # A  day-ahead
    da = da_hourly(pull); da['yr'] = da.t.dt.year; da['day'] = da.t.dt.date
    for y in YEARS:
        d = da[da.yr == y]
        add('A', 'da_mean', 'N2EX DA', y, d.price.mean(), 'GBP/MWh', 'Modo /gb/n2ex/day-ahead-hourly/prices')
        add('A', 'neg_hours', 'N2EX DA', y, (d.price < 0).sum(), 'h', 'as above')
        add('A', 'da_min', 'N2EX DA', y, d.price.min(), 'GBP/MWh', 'as above')
        add('A', 'mean_neg_price', 'N2EX DA', y, d.loc[d.price < 0, 'price'].mean(), 'GBP/MWh', 'as above')
        g = d.groupby('day').price
        add('A', 'daily_spread', 'N2EX DA', y, (g.max() - g.min()).mean(), 'GBP/MWh', 'mean of daily max - min')
        lo = g.apply(lambda s: s.nsmallest(6).mean()).mean(); hi = g.apply(lambda s: s.nlargest(6).mean()).mean()
        add('A', 'cheapest6h', 'N2EX DA', y, lo, 'GBP/MWh', 'mean of the 6 cheapest hours per day')
        add('A', 'dearest6h', 'N2EX DA', y, hi, 'GBP/MWh', 'mean of the 6 dearest hours per day')
        add('A', 'spread6h', 'N2EX DA', y, hi - lo, 'GBP/MWh', 'dearest6h - cheapest6h')
    # B  renewable bids
    bod = bod_monthly(pull)
    for (name, tech, contract, y), d in bod.groupby(['name', 'tech', 'contract', 'yr']):
        add('B', 'bm_turn_down_bid', f'{name} ({tech}, {contract})', y, d.turn_down_bid.median(), 'GBP/MWh', 'Elexon BOD pair -1, median of monthly medians, first 7 days/month')
        if d.turn_up_offer.notna().any():
            add('C' if 'Gas' in tech or 'Battery' in tech else 'B', 'bm_turn_up_offer', f'{name} ({tech}, {contract})', y, d.turn_up_offer.median(), 'GBP/MWh', 'Elexon BOD pair +1')
    for y in YEARS:
        for tech, band in ROC_BAND.items():
            add('B', 'roc_value_forgone', f'ROC {tech}', y, -band * ROC_BUYOUT[y] * 1.1, 'GBP/MWh', 'ROC banding x buy-out x ~1.1 recycle; what a ROC plant bids to be curtailed')
    tv = pd.read_csv(os.path.join(BB, 'tech_vs_price.csv'))
    for _, r in tv[tv.yr.isin(YEARS) & tv.tech.isin(['WIND', 'SOLAR', 'CCGT'])].iterrows():
        add('B' if r.tech != 'CCGT' else 'C', 'output_ratio_neg_over_pos', r.tech, r.yr, r.ratio_neg_over_pos, 'ratio', 'bidding_behaviour/data/tech_vs_price.csv (FUELHH + Sheffield Solar)')
    # C  gas
    for y in YEARS:
        fuel, carbon, total = srmc(y)
        add('C', 'srmc_fuel', 'existing CCGT 50% HHV', y, fuel, 'GBP/MWh', f'NBP DA {GAS_CARBON[y]["nbp_p_th"]} p/th (DESNZ FFPA 2025 / Ofgem)')
        add('C', 'srmc_carbon', 'existing CCGT 50% HHV', y, carbon, 'GBP/MWh', f'UKA {GAS_CARBON[y]["uka"]} + CPS 18 GBP/t, 0.184 t/MWh_th')
        add('C', 'srmc_total', 'existing CCGT 50% HHV', y, total, 'GBP/MWh', 'fuel + carbon + VOM 4')
    cc = ccgt_hourly(pull)
    j = da.assign(tu=da.t.dt.tz_convert('UTC').dt.floor('h')).merge(cc.rename(columns={'t': 'tu'}), on='tu')
    for y in YEARS:
        d = j[j.yr == y]; med = d.ccgt_mw.median(); q9 = d.ccgt_mw.quantile(0.9)
        add('C', 'da_price_ccgt_above_median', 'N2EX DA | CCGT > median', y, d.loc[d.ccgt_mw > med, 'price'].mean(), 'GBP/MWh', 'FUELHH CCGT hourly join')
        add('C', 'da_price_ccgt_below_median', 'N2EX DA | CCGT <= median', y, d.loc[d.ccgt_mw <= med, 'price'].mean(), 'GBP/MWh', 'as above')
        add('C', 'da_price_ccgt_top_decile', 'N2EX DA | CCGT top decile', y, d.loc[d.ccgt_mw > q9, 'price'].mean(), 'GBP/MWh', 'as above')
    # D  shift cost curves
    cycles = np.array([25, 50, 100, 150, 200, 250, 300, 365, 500, 700])
    specs = [('battery', 2.0, 'LP battery 2 h (2030 costs)'), ('battery', 4.0, 'LP battery 4 h (2030 costs)'),
             ('ldes', 8.0, 'LP LDES 8 h'), ('ldes', 24.0, 'LP LDES 24 h'), ('h2', 200.0, 'LP hydrogen 200 h')]
    for y in YEARS:
        p_ch = [r['value'] for r in rows if r['metric'] == 'cheapest6h' and r['year'] == y][0]
        for store, h, label in specs:
            for c in cycles:
                if c * h <= 8760:
                    add('D', 'lcos', label, y, C.lcos(store, c, h, p_ch), 'GBP/MWh discharged', f'costs.lcos, charging at cheapest-6h DA {p_ch:.1f}')
        # 2025-vintage 2 h battery: 560 GBP/kW, FOM 14, 15 yr, 8.9 % (storage_value/costs.py central)
        afc25 = 560 * C.crf(0.089, 15) + 14
        for c in cycles:
            add('D', 'lcos', 'today battery 2 h (560 GBP/kW)', y, afc25 * 1000 / (c * 2) + p_ch / 0.86, 'GBP/MWh discharged', 'storage_value costs central')
    # E  BESS revenue
    for y in YEARS:
        add('E', 'bess_revenue', 'GB BESS index', y, MODO_BESS[y], 'GBP/MW-yr', 'Modo Energy GB BESS index (all revenue streams)')
    out = pd.DataFrame(rows)
    os.makedirs(OUT, exist_ok=True)
    out.to_csv(os.path.join(OUT, 'market_bids_2024_25.csv'), index=False)
    print(out[out.block != 'D'].to_string(index=False))
    return out


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--no-pull', action='store_true')
    build(pull=not ap.parse_args().no_pull)
```

- [ ] **Step 2: Run** `python scripts/analysis/firm_lcoe/market_bids.py`. Expected: DA means 72-73 (2024) and 80-81 (2025) matching `price_monthly.csv`; neg hours 176/177; BOD medians for wind strongly negative (−70 to −190), Pembroke bid ~50 / offer ~150; plants with no BOD print `[warn]` and are skipped. Note skipped BMUs in the README.

- [ ] **Step 3: Sanity assertions** (inline, in the Python REPL): `srmc(2024)[2]` ≈ 82, `srmc(2025)[2]` ≈ 88; DA mean 2024 within 1 of 72.5.

---

### Task 6: report.py (xlsx + HTML + README)

**Files:** Create `scripts/analysis/firm_lcoe/report.py`.

**Interfaces consumed:** `results.csv`, `market_bids_2024_25.csv`, `costs.generation/stores`, `inputs.build_cf` (CF summary), `run_sweep.log`.
**Produces:** `firm_lcoe.xlsx` (sheets: README, results, market_bids, costs, cf_by_year), `firm_lcoe_report.html` (tabs: Overview, Firmness, Cost decomposition, Capacity & storage, Market 2024-25, Inputs & method), `figures/F1..F6.png`, `README.md`.

- [ ] **Step 1: Write `report.py`**

```python
"""One workbook + one tabbed self-contained HTML + README for the firm-LCOE analysis.

    python scripts/analysis/firm_lcoe/report.py
"""
import base64, html, io, os, subprocess, sys, datetime as dt
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import costs as C, inputs as I

OUT = os.path.join(I.ROOT, 'resources', 'analysis', 'firm_lcoe')
FIG = os.path.join(OUT, 'figures')
LABEL = {'re_storage': 'RE + storage', 're_storage_gas5': 'RE + storage + 5% gas', 'nuclear_storage': 'Nuclear + storage',
         'gas_ccus': 'Gas CCUS', 'all_tech': 'All technologies'}
COL = {'solar': '#f0b429', 'onshore': '#7fb3d5', 'offshore': '#2e6da4', 'nuclear': '#8e44ad', 'gas_ccus': '#7f8c8d', 'ccgt': '#4d4d4d',
       'battery': '#e67e22', 'ldes': '#16a085', 'h2': '#c0392b', 'curtailed': '#d5d8dc'}
plt.rcParams.update({'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False, 'figure.dpi': 130})


def savefig(fig, name):
    os.makedirs(FIG, exist_ok=True)
    p = os.path.join(FIG, f'{name}.png'); fig.savefig(p, bbox_inches='tight'); plt.close(fig)
    return p


def img(p):
    return '<img src="data:image/png;base64,' + base64.b64encode(open(p, 'rb').read()).decode() + '">'


def table(df, fmt='{:,.1f}'):
    th = ''.join(f'<th>{html.escape(str(c))}</th>' for c in df.columns)
    tr = ''.join('<tr>' + ''.join(f'<td>{fmt.format(v) if isinstance(v, (float, np.floating)) and not np.isnan(v) else html.escape(str(v))}</td>' for v in r) + '</tr>' for r in df.itertuples(index=False))
    return f'<table><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table>'


def components(r):
    """GBP/MWh delivered by component for one results row."""
    den = r['delivered_twh'] * 1e6
    vre = sum(r.get(f'cost_{k}', 0) for k in ('solar', 'onshore', 'offshore'))
    cur = r.get('cost_vre_curtailed', 0)
    out = {'VRE used': (vre - cur) / den, 'VRE curtailed': cur / den}
    for k in ('nuclear', 'gas_ccus', 'ccgt'):
        v = r.get(f'cost_{k}_fixed', 0) + r.get(f'cost_{k}_var', 0)
        if v: out[LABEL.get(k, k) if k != 'ccgt' else 'Backup gas'] = v / den
    for s, lab in (('battery', 'Battery'), ('ldes', 'LDES'), ('h2', 'Hydrogen')):
        v = r.get(f'cost_{s}', 0)
        if v: out[lab] = v / den
    return out


def f1_firmness(res):
    base = res[res.sens == 'base']
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    for cn, d in base.groupby('case'):
        d = d.sort_values('firmness')
        x = -np.log10(np.clip(1 - d.firmness, 1e-4, 1))
        ax.plot(x, d.firm_lcoe, 'o-', label=LABEL[cn], color={'re_storage': COL['offshore'], 're_storage_gas5': COL['ccgt'], 'nuclear_storage': COL['nuclear'], 'gas_ccus': COL['gas_ccus'], 'all_tech': '#27ae60'}[cn])
        for xi, yi in zip(x, d.firm_lcoe):
            ax.annotate(f'{yi:.0f}', (xi, yi), textcoords='offset points', xytext=(4, 4), fontsize=8)
    ax.set_xticks([1, 1.3, 2, 3, 4]); ax.set_xticklabels(['90%', '95%', '99%', '99.9%', '100%'])
    ax.set_xlabel('Firmness (share of demand met, every weather year)'); ax.set_ylabel('Firm LCOE, GBP/MWh delivered (real 2024)')
    ax.set_title('Cost of meeting the GB demand profile, 41 weather years'); ax.legend(frameon=False)
    return savefig(fig, 'F1_firm_lcoe_vs_firmness')


def f2_decomposition(res):
    pts = res[(res.sens == 'base') & (res.firmness.isin([0.99, 1.0]))].copy()
    pts['lab'] = pts.case.map(LABEL) + ' ' + pts.firmness.map(lambda f: f'{100*f:g}%')
    comps = [components(r) for _, r in pts.iterrows()]
    keys = [k for k in dict.fromkeys(k for c in comps for k in c)]
    cols = {'VRE used': COL['offshore'], 'VRE curtailed': COL['curtailed'], 'Nuclear + storage': COL['nuclear'], 'Gas CCUS': COL['gas_ccus'],
            'Backup gas': COL['ccgt'], 'Battery': COL['battery'], 'LDES': COL['ldes'], 'Hydrogen': COL['h2']}
    fig, ax = plt.subplots(figsize=(8, 4.5)); bottom = np.zeros(len(pts))
    for k in keys:
        v = np.array([c.get(k, 0) for c in comps]); ax.bar(pts.lab, v, bottom=bottom, label=k, color=cols.get(k, '#999')); bottom += v
    for i, t in enumerate(bottom): ax.text(i, t + 2, f'{t:.0f}', ha='center', fontsize=9)
    ax.set_ylabel('GBP/MWh delivered'); ax.set_title('Where the firm LCOE goes'); ax.legend(frameon=False, ncol=2, fontsize=8)
    plt.setp(ax.get_xticklabels(), rotation=20, ha='right')
    return savefig(fig, 'F2_cost_decomposition')


def f3_capacity(res):
    pts = res[(res.sens == 'base') & (res.firmness == 1.0)].copy(); pts['lab'] = pts.case.map(LABEL)
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2))
    ax = axes[0]; bottom = np.zeros(len(pts))
    for k in ('solar', 'onshore', 'offshore', 'nuclear', 'gas_ccus', 'ccgt'):
        v = pts.get(f'cap_{k}_mw', pd.Series(0, index=pts.index)).fillna(0).to_numpy() / 1e3
        ax.bar(pts.lab, v, bottom=bottom, color=COL[k], label=k); bottom += v
    ax.set_ylabel('GW'); ax.set_title('Generation capacity'); ax.legend(frameon=False, fontsize=8); plt.setp(ax.get_xticklabels(), rotation=20, ha='right')
    ax = axes[1]; bottom = np.zeros(len(pts))
    for s in ('battery', 'ldes', 'h2'):
        v = pts.get(f'{s}_e_mwh', pd.Series(0, index=pts.index)).fillna(0).to_numpy() / 1e3
        ax.bar(pts.lab, v, bottom=bottom, color=COL[s], label=s); bottom += v
    ax.set_ylabel('GWh'); ax.set_title('Storage energy capacity'); ax.set_yscale('symlog', linthresh=100); ax.legend(frameon=False, fontsize=8); plt.setp(ax.get_xticklabels(), rotation=20, ha='right')
    return savefig(fig, 'F3_capacity_mix')


def f4_cycles(res):
    pts = res[(res.sens == 'base')].copy(); pts['lab'] = pts.case.map(LABEL) + ' ' + pts.firmness.map(lambda f: f'{100*f:g}%')
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2))
    for s in ('battery', 'ldes', 'h2'):
        if f'{s}_cycles_yr' in pts:
            axes[0].plot(pts.lab, pts[f'{s}_cycles_yr'], 'o', color=COL[s], label=s)
            axes[1].plot(pts.lab, pts[f'{s}_duration_h'], 'o', color=COL[s], label=s)
    axes[0].set_ylabel('cycles per year'); axes[0].set_title('Storage cycles'); axes[1].set_ylabel('hours'); axes[1].set_yscale('log'); axes[1].set_title('Storage duration (E/P)')
    for ax in axes: ax.legend(frameon=False, fontsize=8); plt.setp(ax.get_xticklabels(), rotation=30, ha='right', fontsize=8)
    return savefig(fig, 'F4_storage_cycles_duration')


def f5_shift_cost(mk, res):
    fig, ax = plt.subplots(figsize=(8, 4.8))
    d = mk[(mk.block == 'D') & (mk.year == 2025)]
    for g, dd in d.groupby('group'):
        x = dd.source.str.extract(r'^(?:costs\.lcos|storage_value)')  # noqa (label only)
        cyc = [int(c) for c in [25, 50, 100, 150, 200, 250, 300, 365, 500, 700] if len(dd) and True][:len(dd)]
        ax.plot(cyc, dd.value.to_numpy(), '-', label=g)
    for y, ls in ((2024, ':'), (2025, '--')):
        sp = mk[(mk.metric == 'spread6h') & (mk.year == y)].value.iloc[0]
        ax.axhline(sp, color='k', ls=ls, lw=1); ax.text(705, sp, f'DA 6h spread {y}: {sp:.0f}', fontsize=8, va='bottom', ha='right')
    rb = mk[(mk.metric == 'bm_turn_down_bid') & (mk.group.str.contains('Wind offshore')) & (mk.year == 2025)].value.median()
    gs = mk[(mk.metric == 'srmc_total') & (mk.year == 2025)].value.iloc[0]
    ax.axhline(gs - rb, color=COL['h2'], ls='-.', lw=1); ax.text(705, gs - rb, f'gas SRMC minus offshore-wind curtail bid 2025: {gs-rb:.0f}', fontsize=8, va='bottom', ha='right')
    base = res[(res.sens == 'base') & (res.case == 're_storage') & (res.firmness == 1.0)]
    if len(base):
        r = base.iloc[0]
        for s, lab in (('battery', 'LP battery'), ('ldes', 'LP LDES'), ('h2', 'LP hydrogen')):
            if r.get(f'{s}_e_mwh', 0) > 0:
                p_ch = mk[(mk.metric == 'cheapest6h') & (mk.year == 2025)].value.iloc[0]
                ax.plot(r[f'{s}_cycles_yr'], C.lcos(s, max(r[f'{s}_cycles_yr'], 1), r[f'{s}_duration_h'], p_ch), 's', color=COL[s], ms=9, label=f'{lab} as built by the LP ({r[f"{s}_duration_h"]:.0f} h)')
    ax.set_xscale('log'); ax.set_yscale('log'); ax.set_xlabel('cycles per year'); ax.set_ylabel('GBP per MWh shifted')
    ax.set_title('Unit cost of shifting one MWh vs what the 2024-25 market paid'); ax.legend(frameon=False, fontsize=7.5, ncol=2)
    return savefig(fig, 'F5_shift_cost_vs_market')


def f6_bids(mk):
    b = mk[mk.metric == 'bm_turn_down_bid'].pivot_table(index='group', columns='year', values='value')
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), gridspec_kw=dict(width_ratios=[1.4, 1]))
    b.sort_values(2025 if 2025 in b else b.columns[0]).plot.barh(ax=axes[0], color=['#999', '#333'])
    for y in (2024, 2025):
        s = mk[(mk.metric == 'srmc_total') & (mk.year == y)].value.iloc[0]
        axes[0].axvline(s, color=COL['ccgt'], ls='--', lw=1); axes[0].text(s, -0.8, f'gas SRMC {y} {s:.0f}', fontsize=7, rotation=90, va='bottom')
    axes[0].axvline(0, color='k', lw=0.8); axes[0].set_xlabel('GBP/MWh (median BM bid to turn down; negative = must be paid to curtail)'); axes[0].set_title('What plants bid 2024-25')
    c = mk[mk.block == 'C'].pivot_table(index='metric', columns='year', values='value')
    c.loc[['srmc_fuel', 'srmc_carbon', 'srmc_total', 'da_price_ccgt_above_median', 'da_price_ccgt_below_median', 'da_price_ccgt_top_decile']].plot.bar(ax=axes[1], color=['#999', '#333'])
    axes[1].set_ylabel('GBP/MWh'); axes[1].set_title('Gas: cost to run vs price when it runs'); plt.setp(axes[1].get_xticklabels(), rotation=30, ha='right', fontsize=8)
    return savefig(fig, 'F6_bids_and_gas')


def main():
    res = pd.read_csv(os.path.join(OUT, 'results.csv')); res['sens'] = res['sens'].fillna('base')
    mk = pd.read_csv(os.path.join(OUT, 'market_bids_2024_25.csv'))
    commit = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True, cwd=I.ROOT).stdout.strip()
    figs = dict(F1=f1_firmness(res), F2=f2_decomposition(res), F3=f3_capacity(res), F4=f4_cycles(res), F5=f5_shift_cost(mk, res), F6=f6_bids(mk))
    # tables
    key = ['case', 'firmness', 'sens', 'sens_value', 'firm_lcoe', 'curtail_share', 'cap_solar_mw', 'cap_onshore_mw', 'cap_offshore_mw', 'cap_nuclear_mw', 'cap_gas_ccus_mw', 'cap_ccgt_mw',
           'battery_p_mw', 'battery_e_mwh', 'battery_cycles_yr', 'ldes_p_mw', 'ldes_e_mwh', 'ldes_cycles_yr', 'h2_p_mw', 'h2_p_out_mw', 'h2_e_mwh', 'h2_cycles_yr', 'lole_h_mean', 'lole_h_max', 'solve_time_s']
    key = [k for k in key if k in res]
    gen = pd.DataFrame([dict(technology=k, **v) for k, v in C.generation().items()])
    sto = pd.DataFrame([dict(store=k, **v) for k, v in C.stores().items()])
    cf = I.build_cf().groupby('year')[I.TECHS].mean().reset_index(); cf['solar_derated'] = cf['solar'] * C.DEFAULT_OPT['solar_scale']
    readme_rows = [
        ('Question', 'Cost per MWh delivered of meeting the GB demand profile at a stated firmness with RE+storage, nuclear(+storage) and gas CCUS; plus 2024-25 market evidence on bids vs the unit cost of shifting a MWh.'),
        ('Model', 'Single-node greenfield LP, joint over weather years, storage cyclic per year, 3-h blocks, hourly fixed-capacity re-check for LOLE. scripts/analysis/firm_lcoe/'),
        ('Weather years', f'{int(res.n_years.max())} (1985-2025 atlite REPD fleet CF); solar derated x{C.DEFAULT_OPT["solar_scale"]:.4f} to an 11.0% 41-yr mean'),
        ('Demand', 'FES 2025 Holistic Transition 2050 GB profile (567 TWh, peak 99.8 GW), fixed shape for every weather year (no temperature coupling)'),
        ('Costs', 'Real 2024 GBP, 2030 commissioning; DESNZ Electricity Generation Costs 2025 LCOEs reproduced exactly at DESNZ load factors; storage per spec'),
        ('Market data', 'N2EX DA hourly, Elexon BOD (first 7 days/month), FUELHH CCGT via Modo REST (2024-01..2025-12); NBP/UKA annual means in market_bids.py'),
        ('Spec', 'docs/superpowers/specs/2026-11-18-firm-lcoe-weather-year-lp-design.md'), ('Git commit', commit), ('Built', dt.date.today().isoformat()),
        ('Sheets', 'results (one row per solve), market_bids (tidy), costs_generation, costs_storage, cf_by_year'),
    ]
    with pd.ExcelWriter(os.path.join(OUT, 'firm_lcoe.xlsx'), engine='openpyxl') as xw:
        pd.DataFrame(readme_rows, columns=['item', 'value']).to_excel(xw, 'README', index=False)
        res[key + [c for c in res.columns if c not in key]].to_excel(xw, 'results', index=False)
        mk.to_excel(xw, 'market_bids', index=False); gen.to_excel(xw, 'costs_generation', index=False); sto.to_excel(xw, 'costs_storage', index=False); cf.to_excel(xw, 'cf_by_year', index=False)
    # HTML
    base = res[res.sens == 'base']
    hl = base[base.firmness == 1.0].set_index('case').firm_lcoe
    tabs = [
        ('Overview', f'<p>Firm LCOE at 100% firmness over all weather years (GBP/MWh delivered): ' + ', '.join(f'<b>{LABEL[c]}</b> {v:.0f}' for c, v in hl.items()) + '.</p>' + img(figs['F1']) + table(base[key])),
        ('Cost decomposition', img(figs['F2']) + '<p>VRE curtailed = share of VRE fixed cost attributable to curtailed energy.</p>'),
        ('Capacity & storage', img(figs['F3']) + img(figs['F4'])),
        ('Market 2024-25', img(figs['F6']) + img(figs['F5']) + table(mk[mk.block != 'D'][['block', 'metric', 'group', 'year', 'value', 'unit', 'source']], '{:,.1f}')),
        ('Sensitivities', table(res[res.sens != 'base'][key])),
        ('Inputs & method', table(gen, '{:,.2f}') + table(sto, '{:,.3f}') + table(cf.round(3), '{:.3f}') + '<pre>' + html.escape(open(os.path.join(OUT, 'run_sweep.log'), encoding='utf-8').read()[-6000:] if os.path.exists(os.path.join(OUT, 'run_sweep.log')) else '') + '</pre>'),
    ]
    nav = ''.join(f'<button onclick="show({i})" id="b{i}">{html.escape(t)}</button>' for i, (t, _) in enumerate(tabs))
    secs = ''.join(f'<section id="s{i}" style="display:{"block" if i == 0 else "none"}"><h2>{html.escape(t)}</h2>{b}</section>' for i, (t, b) in enumerate(tabs))
    doc = f'''<!doctype html><html><head><meta charset="utf-8"><title>Firm LCOE: RE + storage vs nuclear vs gas CCUS</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;margin:24px;color:#222;max-width:1200px}}nav button{{margin:0 4px 12px 0;padding:6px 12px;border:1px solid #bbb;background:#f6f6f6;cursor:pointer}}
nav button.on{{background:#2e6da4;color:#fff;border-color:#2e6da4}}table{{border-collapse:collapse;font-size:12px;margin:12px 0}}th,td{{border:1px solid #ddd;padding:3px 6px;text-align:right}}th{{background:#f0f0f0}}td:first-child,th:first-child{{text-align:left}}img{{max-width:100%;display:block;margin:12px 0}}pre{{font-size:11px;background:#f6f6f6;padding:8px;overflow:auto}}</style></head>
<body><h1>Firm LCOE of renewables + storage vs nuclear and gas CCUS, GB demand profile, 41 weather years</h1>
<p class="sub">Real 2024 GBP, 2030 costs. Built {dt.date.today().isoformat()}, commit {commit}. Spec: docs/superpowers/specs/2026-11-18-firm-lcoe-weather-year-lp-design.md</p>
<nav>{nav}</nav>{secs}
<script>function show(i){{document.querySelectorAll('section').forEach((s,j)=>s.style.display=i==j?'block':'none');document.querySelectorAll('nav button').forEach((b,j)=>b.className=i==j?'on':'')}}show(0)</script></body></html>'''
    open(os.path.join(OUT, 'firm_lcoe_report.html'), 'w', encoding='utf-8').write(doc)
    open(os.path.join(OUT, 'README.md'), 'w', encoding='utf-8').write('# firm_lcoe\n\n' + '\n'.join(f'- **{k}**: {v}' for k, v in readme_rows) +
        '\n\nFiles: results.csv, market_bids_2024_25.csv, firm_lcoe.xlsx, firm_lcoe_report.html, figures/, inputs/ (national_cf.parquet, demand.parquet, market/*.csv).\n')
    print('wrote', OUT)


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: Run on the smoke results** first (`copy results_smoke.csv results.csv` temporarily if the full sweep is still running) → HTML opens, 6 figures, xlsx with 6 sheets. Fix any KeyError from missing columns (cases without a store/tech produce NaN columns, handled by `.get`/`fillna`).

- [ ] **Step 3: Run on the full results**; open `firm_lcoe_report.html` in the built-in browser and check every tab renders.

---

### Task 7: Record provenance and hand over

- [ ] Append to `scripts/analysis/firm_lcoe/README.md`? No: the README.md sidecar lives in `resources/analysis/firm_lcoe/` (written by report.py). Add a `_registry.yaml` entry? The hub's DATA_PROVENANCE rule 4 applies to external pulls: add a `scripts/analysis/firm_lcoe/_registry.yaml` with id `firm_lcoe_weather_year_lp_2026_11_18`, the Modo endpoints used, window 2024-01..2026-01, outputs list, caveats (fixed 2050 demand shape; 3-h blocks; crossover off; sampled BOD; annual NBP/UKA means).
- [ ] Append a dated section to the PyPSA-GB Obsidian project note (per user memory `obsidian-project-notes`) with the headline numbers and the path to the HTML.
- [ ] Do not commit unless the user asks.

---

## Self-review

- Spec coverage: model (T3), cases + sweep + sensitivities incl. solar 12% (T4), inputs with 11/12 derate (T2), costs table (T1), hourly LOLE re-check (T3/T4), market evidence blocks 1-3 (T5, F5/F6 in T6), one xlsx + one HTML + README (T6), provenance (T7). Out-of-scope items untouched.
- Types: `extract()` keys (`cap_{k}_mw`, `{s}_p_mw`, `{s}_e_mwh`, `{s}_p_out_mw`, `{s}_cycles_yr`, `{s}_duration_h`, `cost_*`, `firm_lcoe`, `delivered_twh`) are the ones `recheck_hourly(fixed_caps=...)`, `run_sweep.one()` and `report.components()` read. `data` dict keys (`cf, demand, years, T, dt, techs`) consistent between `inputs.load`, `slice_year`, `build_lp`, and the test `toy()`.
- Known simplification: F5 reads LCOS curve x-values from the fixed cycles list (same order as written) rather than parsing them from the CSV; acceptable because `market_bids.py` writes them in that order and skips `c*h > 8760` only for hydrogen/LDES 24 h (those curves are shorter, handled by `[:len(dd)]`).
