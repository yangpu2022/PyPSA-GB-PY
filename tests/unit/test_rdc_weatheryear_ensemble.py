"""Tests for scripts/analysis/rdc_weatheryear_ensemble.py (synthetic data only)."""

import numpy as np
import pandas as pd
import pytest

from scripts.analysis import rdc_weatheryear_ensemble as rw


def _toy_network(hours=8760, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2030-01-01", periods=hours, freq="h")
    wind = rng.uniform(0, 30_000, hours)
    disp = pd.DataFrame({
        "FES_wind_onshore_A_2030": wind * 0.4,
        "FES_wind_offshore_B_2030": wind * 0.6,
        "FES_solar_pv_C_2030": rng.uniform(0, 10_000, hours),
        "FES_nuclear_D_2030": np.full(hours, 4_000.0),
        "FES_biomass_E_2030": np.full(hours, 1_000.0),
        "FES_CCGT_F_2030": rng.uniform(0, 20_000, hours),
    }, index=idx)
    sto = pd.DataFrame({"FES_Battery_X_2030_0": rng.uniform(-2_000, 2_000, hours),
                        "Pumped_Storage_Y": rng.uniform(-500, 500, hours)}, index=idx)
    lnk = pd.DataFrame({"electrolysis_Z": rng.uniform(0, 1_000, hours),
                        "H2_turbine_Z": rng.uniform(0, 800, hours),
                        "IC_Norway": rng.uniform(-1_000, 1_000, hours)}, index=idx)
    return disp, sto, lnk


def test_network_residual_matches_proc_bot_definition():
    disp, sto, lnk = _toy_network()
    out = rw.network_residual(disp, sto, lnk, h2_turbine_eff=0.5)
    h2 = 0.5 * lnk["H2_turbine_Z"] - lnk["electrolysis_Z"]
    demand = disp.sum(axis=1) + sto.sum(axis=1) + h2
    vre = disp.filter(regex="wind|solar").sum(axis=1)
    firm = disp["FES_nuclear_D_2030"] + disp["FES_biomass_E_2030"]
    np.testing.assert_allclose(out["demand"], demand)
    np.testing.assert_allclose(out["residual"], demand - vre - firm)
    # interconnector links are not part of the accounting
    assert "IC_Norway" not in out.columns
    np.testing.assert_allclose(out["net_Hydrogen"], h2)
    assert {"net_Battery", "net_Pumped hydro"} <= set(out.columns)


def test_year_metrics_split_and_units():
    r = pd.Series([2_000_000.0, -1_000_000.0, 0.0])          # MW
    m = rw.year_metrics(r)
    assert m["rd_twh"] == pytest.approx(2.0)
    assert m["su_twh"] == pytest.approx(1.0)
    assert m["pk_gw"] == pytest.approx(2_000.0)


def test_duration_curve_is_sorted_and_clamped():
    r = np.arange(8760, dtype=float) * 1000          # MW
    c = rw.duration_curve(r)
    assert c.size == rw.N_GRID
    assert np.all(np.diff(c) <= 0)
    assert c[0] == pytest.approx(r.max() / 1e3)        # clamped at the top (rule = 2)
    assert c[-1] == pytest.approx(0.0)


def test_screen_residual_uses_exact_carriers():
    g = pd.DataFrame({"demand": [10.0, 20.0], "wind_onshore": [3.0, 1.0],
                      "solar_pv": [1.0, 0.0], "nuclear": [2.0, 2.0], "CCGT": [4.0, 17.0]})
    np.testing.assert_allclose(rw.screen_residual(g), [4.0, 17.0])


def test_end_to_end_csv(tmp_path):
    market = tmp_path / "market"
    market.mkdir()
    for ty in (2030, 2040):
        for wy in (2010, 2011):
            disp, sto, lnk = _toy_network(seed=wy + ty)
            scn = f"HT{str(ty)[2:]}_disp_w{wy}"
            disp.to_csv(market / f"{scn}_wholesale_dispatch.csv")
            sto.to_csv(market / f"{scn}_wholesale_storage.csv")
            lnk.to_csv(market / f"{scn}_wholesale_links.csv")
    out = tmp_path / "out"
    rc = rw.main(["--market-dir", str(market), "--network-dir", str(tmp_path),
                  "--weather-years", "2010-2012", "--out", str(out)])
    assert rc == 0
    s = pd.read_csv(out / "rdc_wy_summary.csv")
    assert set(s.target_year) == {2030, 2040}
    assert (s.n_years == 2).all() and (s.n_expected == 3).all()
    inv = pd.read_csv(out / "rdc_wy_inputs.csv")
    assert (~inv.found).sum() == 4                     # wy2012: csv + nc, two target years
    assert (out / "rdc_wy_network.png").exists()
    per = pd.read_csv(out / "rdc_wy_network_per_year.csv")
    assert np.isclose(s.loc[s.target_year == 2030, "rd_twh"].iloc[0],
                      per[per.target_year == 2030].rd_twh.mean(), atol=0.01)
