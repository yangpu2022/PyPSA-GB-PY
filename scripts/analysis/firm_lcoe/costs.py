"""Cost table for the firm-LCOE LP. REAL 2024 GBP, 2030 commissioning.

Principle: every generation input is a published DESNZ 2025 LCOE and its load factor, so a MWh
taken straight from the plant costs exactly the DESNZ figure (AFC = (LCOE - VOM) x 8760 x LF / 1000,
GBP/kW-yr). Storage is annualised capex at CEPA 2025 hurdle rates. Sources: DESNZ Electricity
Generation Costs 2025 (Jan 2026) and Annex A; NAO (HPC/SZC) for nuclear; NREL 2025, BNEF Dec 2025,
LCP Delta/Regen 2024, Royal Society 2023 for storage (see spec 2026-11-18).
"""
import math

# cap_max (MW): GB build-out ceilings so the LP cannot answer with hundreds of GW of onshore wind.
# Onshore 40 GW and solar 100 GW sit at the top of the FES 2025 / CCC Seventh Carbon Budget 2050 ranges;
# offshore is left free. cap_max=None is the unconstrained sensitivity.
DEFAULT_OPT = dict(battery_e=120.0, nuclear_lcoe=140.0, gas_p=71.0, carbon=120.0,
                   solar_scale=11.0 / 12.0, nuclear_must_run=0.0,
                   cap_max=dict(onshore=40_000.0, solar=100_000.0))

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
    return {
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


def lcos(store, cycles, duration_h, charge_price, opt=DEFAULT_OPT):
    """GBP per MWh discharged: power annuity / (cycles x h) + energy annuity / cycles + charging / RTE + VOM.
    For h2 the power annuity is electrolyser + turbine per MW."""
    s = stores(opt)[store]
    rte = s['eta_in'] * s['eta_out']
    p_afc = s['afc_p_in'] + s['afc_p_out']
    return p_afc * 1000 / (cycles * duration_h) + s['afc_e'] * 1000 / cycles + charge_price / rte + s['vom']


if __name__ == '__main__':
    for k, v in generation().items():
        print(f'{k:10s} AFC {v["afc"]:7.1f} GBP/kW-yr  VOM {v["vom"]:6.1f}  avail {v["avail"]}')
    for k, v in stores().items():
        print(f'{k:10s} P_in {v["afc_p_in"]:6.1f} P_out {v["afc_p_out"]:6.1f} E {v["afc_e"]:6.2f} GBP/kW(h)-yr  eta {v["eta_in"]:.3f}/{v["eta_out"]:.3f}')
