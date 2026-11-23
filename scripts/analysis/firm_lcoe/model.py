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

from scripts.analysis.firm_lcoe import costs as C

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


CAP_KEYS = dict(vre=lambda k: f'cap_{k}_mw', disp=lambda k: f'cap_{k}_mw')


def cap_afc(case, opt):
    """Map every capacity key of a case to its annualised fixed cost (GBP/MW-yr or GBP/MWh-yr)."""
    gen, sto = C.generation(opt), C.stores(opt)
    out = {f'cap_{k}_mw': 1000.0 * gen[k]['afc'] for k in list(case['vre']) + list(case['disp'])}
    for s in case['stores']:
        out[f'{s}_p_mw'] = 1000.0 * sto[s]['afc_p_in']; out[f'{s}_e_mwh'] = 1000.0 * sto[s]['afc_e']
        if not sto[s]['symmetric']:
            out[f'{s}_p_out_mw'] = 1000.0 * sto[s]['afc_p_out']
    return out


def _val(d, k, default=0.0):
    v = d.get(k, default)
    return default if v is None or (isinstance(v, float) and np.isnan(v)) else float(v)


def build_lp(data, case, firmness, opt=C.DEFAULT_OPT, fixed_caps=None, voll=None, threads=8, min_caps=None):
    """fixed_caps: pin every capacity (dispatch-only re-check). min_caps: use them as lower bounds (hourly top-up)."""
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
        m.Params.BarConvTol = 1e-6
        m.Params.NumericFocus = 1
    h = dict(vre=vre, disp=disp, stores=stores, N=N, Y=Y, T=T, dt=dt, dem_rep=dem_rep)

    # ---- capacity variables
    cap_vre = m.addMVar(len(vre), lb=0.0, name='cap_vre') if vre else None
    cap_disp = {k: m.addMVar(1, lb=0.0, name=f'cap_{k}') for k in disp}
    scap = {}
    for s in stores:
        scap[s] = dict(p_in=m.addMVar(1, lb=0.0, name=f'{s}_p_in'), e=m.addMVar(1, lb=0.0, name=f'{s}_e'))
        scap[s]['p_out'] = scap[s]['p_in'] if sto[s]['symmetric'] else m.addMVar(1, lb=0.0, name=f'{s}_p_out')
    cap_max = opt.get('cap_max') or {}
    for i, k in enumerate(vre):
        if k in cap_max and cap_max[k] is not None and fixed_caps is None:
            cap_vre[i].ub = float(cap_max[k])
    bounds = fixed_caps if fixed_caps is not None else min_caps
    if bounds is not None:
        pin = fixed_caps is not None

        def setb(var, v):
            var.lb = v
            if pin:
                var.ub = v
        for i, k in enumerate(vre):
            setb(cap_vre[i], _val(bounds, f'cap_{k}_mw'))
        for k in disp:
            setb(cap_disp[k], _val(bounds, f'cap_{k}_mw'))
        for s in stores:
            setb(scap[s]['p_in'], _val(bounds, f'{s}_p_mw')); setb(scap[s]['e'], _val(bounds, f'{s}_e_mwh'))
            if not sto[s]['symmetric']:
                setb(scap[s]['p_out'], _val(bounds, f'{s}_p_out_mw'))

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
    if voll is None and firmness < 1.0:
        # tiny cost on unserved energy removes the degeneracy of 'free' unserved (barrier stalls otherwise)
        var = var + dt * opt.get('unserved_cost', 1.0) * unserved.sum()
    penalty = opt.get('unserved_cost', 1.0) if (voll is None and firmness < 1.0) else 0.0
    obj = fixed + var / Y                 # fixed is already an annual cost; var sums over Y years
    if voll is not None:
        obj = obj + voll * dt * unserved.sum() / Y
    m.setObjective(obj, GRB.MINIMIZE)
    h.update(unserved_penalty=penalty, cap_vre=cap_vre, cap_disp=cap_disp, scap=scap, unserved=unserved, vre_used=vre_used, g=g, ch=ch, dis=dis, soc=soc)
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
    # system cost excludes the tie-breaking penalty on unserved energy (firmness < 1), which is not a real cost
    r['cost_total_gbp_yr'] = float(m.ObjVal) - h.get('unserved_penalty', 0.0) * r['unserved_twh'] * 1e6
    r['cost_vre_curtailed'] = sum(v for k, v in cost.items() if k in [f'cost_{t}' for t in h['vre']]) * r['curtail_share']
    r['firm_lcoe'] = r['cost_total_gbp_yr'] / (r['delivered_twh'] * 1e6) if r['delivered_twh'] > 0 else float('nan')
    return r


def topup_hourly(data_hourly, caps, case, opt=C.DEFAULT_OPT, threads=4):
    """Hourly capacity LP per weather year with the block solution as lower bounds (100 % firmness);
    returns the element-wise max over years (a conservative hourly-feasible capacity set) and its extra cost."""
    from scripts.analysis.firm_lcoe import inputs as I
    afc = cap_afc(case, opt)
    best = {k: _val(caps, k) for k in afc}
    for i in range(len(data_hourly['years'])):
        d = I.slice_year(data_hourly, i)
        m, h = build_lp(d, case, 1.0, opt, min_caps=caps, threads=threads)
        st = solve(m)
        if st != 'optimal':
            m.dispose(); continue
        r = extract(m, h, d, case, 1.0, opt)
        for k in afc:
            best[k] = max(best[k], _val(r, k))
        m.dispose()
    extra = sum((best[k] - _val(caps, k)) * afc[k] for k in afc)
    return best, extra


def recheck_hourly(data_hourly, caps, case, opt=C.DEFAULT_OPT, voll=1e4, threads=4):
    """Fixed-capacity hourly dispatch per weather year; returns LOLE (hours with unserved > 1 MW) stats."""
    from scripts.analysis.firm_lcoe import inputs as I
    lole, uns = [], []
    for i in range(len(data_hourly['years'])):
        d = I.slice_year(data_hourly, i)
        m, h = build_lp(d, case, 0.0, opt, fixed_caps=caps, voll=voll, threads=threads)
        solve(m)
        u = np.asarray(h['unserved'].X)
        lole.append(int((u > 1.0).sum())); uns.append(float(u.sum()) * d['dt'] / 1e6)
        m.dispose()
    lole, uns = np.array(lole), np.array(uns)
    return dict(lole_h_mean=float(lole.mean()), lole_h_max=int(lole.max()), unserved_twh_mean=float(uns.mean()),
                unserved_twh_max=float(uns.max()), worst_year=int(data_hourly['years'][int(lole.argmax())]))
