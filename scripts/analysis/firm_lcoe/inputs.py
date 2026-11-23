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
    """Average consecutive `step` hours (axis 1 for (Y,8760,...) arrays, axis 0 for 1-D)."""
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
    cf = df[TECHS].to_numpy(dtype=float).reshape(len(years), 8760, 3).copy()
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
        print('41-yr mean CF: ' + ' '.join(f'{t} {df[t].mean():.3f}' for t in TECHS))
        print(f'demand {dem.sum()/1e6:.1f} TWh, peak {dem.max()/1e3:.1f} GW, min {dem.min()/1e3:.1f} GW')
