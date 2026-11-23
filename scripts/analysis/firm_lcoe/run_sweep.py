"""Sweep the firm-LCOE LP over cases x firmness x sensitivities and write results.csv (checkpointed per solve).

    python scripts/analysis/firm_lcoe/run_sweep.py                          # all cases, 41 years, 3-h blocks
    python scripts/analysis/firm_lcoe/run_sweep.py --years 2010 2013 --step 6 --cases re_storage gas_ccus --no-recheck
    python scripts/analysis/firm_lcoe/run_sweep.py --sens all

For firmness 1.0 the block solution is followed by an hourly top-up (per-year hourly capacity LP with the
block capacities as lower bounds, max over years) so the reported firm_lcoe_hourly is hourly-feasible in
every weather year; for firmness < 1 the hourly re-check only measures unserved energy / LOLE.
"""
import argparse, os, sys, time
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from scripts.analysis.firm_lcoe import inputs as I, costs as C, model as M  # noqa: E402

OUT = os.path.join(I.ROOT, 'resources', 'analysis', 'firm_lcoe')
RESULTS = os.path.join(OUT, 'results.csv')
# (sensitivity name, value, cases it applies to, firmness)
SENS = [('battery_e', 80.0, ['re_storage'], 1.0), ('battery_e', 200.0, ['re_storage'], 1.0),
        ('nuclear_lcoe', 120.0, ['nuclear_storage', 'all_tech'], 1.0), ('nuclear_lcoe', 160.0, ['nuclear_storage', 'all_tech'], 1.0),
        ('gas_p', 40.0, ['re_storage_gas5'], 1.0), ('gas_p', 150.0, ['re_storage_gas5'], 1.0),
        ('solar_scale', 1.0, ['re_storage'], 1.0),
        ('cap_max', None, ['re_storage', 'all_tech'], 1.0)]


def log(msg):
    print(time.strftime('%H:%M:%S'), msg, flush=True)
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, 'run_sweep.log'), 'a', encoding='utf-8') as f:
        f.write(time.strftime('%Y-%m-%d %H:%M:%S ') + msg + '\n')


def one(data, data_h, case_name, f, opt, sens, sens_value, recheck, threads):
    case = M.CASES[case_name]
    t0 = time.time()
    m, h = M.build_lp(data, case, f, opt, threads=threads)
    m.update()
    log(f'{case_name} f={f} {sens}={sens_value}: built {h["N"]} periods, {m.NumVars} vars, {m.NumConstrs} constrs in {time.time()-t0:.0f}s')
    status = M.solve(m)
    if status not in ('optimal', 'suboptimal') or m.SolCount == 0:
        log(f'  !! {status}')
        m.dispose()
        return dict(case=case_name, firmness=f, sens=sens, sens_value=sens_value, status=status)
    r = M.extract(m, h, data, case, f, opt)
    r.update(case=case_name, sens=sens, sens_value=str(sens_value), status=status)
    log(f'  status {status}')
    log(f'  firm LCOE {r["firm_lcoe"]:.1f} GBP/MWh, curtail {100*r["curtail_share"]:.1f}%, solve {r["solve_time_s"]}s')
    m.dispose()
    if recheck:
        caps = r
        if f >= 1.0:
            t1 = time.time()
            best, extra = M.topup_hourly(data_h, r, case, opt)
            for k, v in best.items():
                r[f'{k}_hourly'] = v
            r['topup_cost_gbp_yr'] = extra
            r['firm_lcoe_hourly'] = (r['cost_total_gbp_yr'] + extra) / (r['delivered_twh'] * 1e6)
            caps = {k: v for k, v in best.items()}
            log(f'  hourly top-up: +{extra/1e6:.0f} MGBP/yr -> firm LCOE {r["firm_lcoe_hourly"]:.1f} GBP/MWh ({time.time()-t1:.0f}s)')
        rc = M.recheck_hourly(data_h, caps, case, opt)
        r.update(lole_h_mean=rc['lole_h_mean'], lole_h_max=rc['lole_h_max'], unserved_twh_max_hourly=rc['unserved_twh_max'], worst_year=rc['worst_year'])
        log(f'  hourly re-check: LOLE mean {rc["lole_h_mean"]:.1f} h, max {rc["lole_h_max"]} h ({rc["worst_year"]})')
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
