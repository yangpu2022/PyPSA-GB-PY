"""Which buses carry GB electricity: the rule the market accounting and the bill share.

A network holds three kinds of bus: GB electrical buses (AC, DC or an empty carrier), the hydrogen
bus, and the foreign-market buses at the far end of each interconnector (``External`` in the name,
or a non-GB country). Demand totals, demand-weighted prices and the bill count loads only on the
first kind, plus the electricity electrolysers draw from them. These tests pin that rule
(``market_accounting._is_gb_electrical_bus``) and the two places that apply it:
``market_accounting._gb_electricity_demand_mwh`` on an in-memory network and
``project_future_bill._electrical_buses`` on a saved network file.
"""
import pandas as pd
import pypsa
import pytest
import xarray as xr

from scripts.market import market_accounting as ma

IDX = pd.date_range("2035-01-01", periods=3, freq="h")


def _buses(**columns) -> pd.DataFrame:
    index = columns.pop("index")
    return pd.DataFrame(columns, index=pd.Index(index, name="Bus"))


# --- the rule ---------------------------------------------------------------------------------

def test_ac_dc_and_blank_carriers_are_electrical_whatever_their_case_and_spacing():
    buses = _buses(index=["a", "b", "c", "d", "e"], carrier=["AC", "dc", " Ac ", "", None])
    assert ma._is_gb_electrical_bus(buses).tolist() == [True, True, True, True, True]


def test_hydrogen_and_other_carriers_are_not_electrical():
    buses = _buses(index=["h2", "heat", "gas", "ac"], carrier=["H2", "heat", "gas", "AC"])
    assert ma._is_gb_electrical_bus(buses).tolist() == [False, False, False, True]


def test_external_buses_are_foreign_whatever_their_carrier():
    buses = _buses(index=["FR External", "NO_External_1", "Externally"], carrier=["AC", "AC", "AC"])
    # the rule is a substring match on "External"; a GB bus must never carry it in its name
    assert ma._is_gb_electrical_bus(buses).tolist() == [False, False, False]


def test_country_column_keeps_gb_and_blank_and_drops_other_countries():
    buses = _buses(index=["gb", "blank", "missing", "fr", "be"], carrier="AC",
                   country=["GB", "", None, "FR", "BE"])
    assert ma._is_gb_electrical_bus(buses).tolist() == [True, True, True, False, False]


def test_blank_country_does_not_rescue_an_external_bus():
    buses = _buses(index=["IE External"], carrier=["AC"], country=[""])
    assert not ma._is_gb_electrical_bus(buses).iloc[0]


def test_without_carrier_or_country_columns_every_non_external_bus_is_electrical():
    buses = pd.DataFrame(index=pd.Index(["x", "y External"], name="Bus"))
    assert ma._is_gb_electrical_bus(buses).tolist() == [True, False]


def test_result_is_aligned_to_the_bus_index():
    buses = _buses(index=["z", "a"], carrier=["H2", "AC"])
    result = ma._is_gb_electrical_bus(buses)
    assert list(result.index) == ["z", "a"]
    assert result.dtype == bool


def test_rule_carriers_are_the_documented_set():
    assert ma.ELECTRICAL_BUS_CARRIERS == frozenset({"", "ac", "dc"})


# --- applied to a network ---------------------------------------------------------------------

def _network() -> pypsa.Network:
    """Two GB buses, the hydrogen bus and one foreign bus, each with a load; one electrolyser."""
    n = pypsa.Network()
    n.set_snapshots(IDX)
    n.add("Bus", "north", carrier="AC", country="GB")
    n.add("Bus", "south", carrier="AC", country="GB")
    n.add("Bus", "H2", carrier="H2", country="")
    n.add("Bus", "FR External", carrier="AC", country="FR")
    n.add("Load", "north load", bus="north", p_set=pd.Series([100.0, 110.0, 120.0], index=IDX))
    n.add("Load", "south load", bus="south", p_set=50.0)
    n.add("Load", "H2 offtake", bus="H2", p_set=pd.Series([30.0, 30.0, 30.0], index=IDX))
    n.add("Load", "FR demand", bus="FR External", p_set=pd.Series([1000.0, 1000.0, 1000.0], index=IDX))
    n.add("Link", "north electrolysis", bus0="north", bus1="H2", p_nom=40.0, efficiency=0.7)
    n.add("Link", "H2 turbine", bus0="H2", bus1="south", p_nom=20.0, efficiency=0.5)
    n.add("Link", "IFA", bus0="south", bus1="FR External", p_nom=2000.0)
    n.links_t.p0 = pd.DataFrame({"north electrolysis": [40.0, 0.0, 20.0],
                                 "H2 turbine": [0.0, 10.0, 0.0],
                                 "IFA": [500.0, -300.0, 0.0]}, index=IDX)
    return n


def test_network_buses_split_into_gb_hydrogen_and_foreign():
    n = _network()
    electrical = set(n.buses.index[ma._is_gb_electrical_bus(n.buses)])
    assert electrical == {"north", "south"}


def test_gb_demand_counts_gb_loads_and_electrolysis_but_not_hydrogen_or_foreign_loads():
    n = _network()
    hours = pd.Series(1.0, index=IDX)
    loads = (100 + 110 + 120) + 3 * 50.0
    electrolysis = 40.0 + 0.0 + 20.0
    # the hydrogen offtake (MWh of hydrogen), the French load, the turbine and the
    # interconnector's exports are not GB electricity demand
    assert ma._gb_electricity_demand_mwh(n, hours) == pytest.approx(loads + electrolysis)


def test_gb_demand_weights_each_snapshot_by_its_hours():
    n = _network()
    hours = pd.Series([1.0, 2.0, 3.0], index=IDX)
    loads = 100 * 1 + 110 * 2 + 120 * 3 + 50.0 * 6
    electrolysis = 40.0 * 1 + 20.0 * 3
    assert ma._gb_electricity_demand_mwh(n, hours) == pytest.approx(loads + electrolysis)


def test_reverse_flow_on_a_conversion_link_is_not_demand():
    n = _network()
    n.links_t.p0["north electrolysis"] = [-5.0, -5.0, -5.0]
    hours = pd.Series(1.0, index=IDX)
    assert ma._gb_electricity_demand_mwh(n, hours) == pytest.approx(330.0 + 150.0)


def test_unsolved_network_counts_loads_only():
    n = _network()
    n.links_t.p0 = pd.DataFrame(index=IDX)
    assert ma._gb_electricity_demand_mwh(n, pd.Series(1.0, index=IDX)) == pytest.approx(480.0)


# --- applied to a saved network file ---------------------------------------------------------

def test_bill_reads_the_same_electrical_buses_from_a_netcdf_file(tmp_path):
    from scripts.consumer_bill.project_future_bill import _electrical_buses

    n = _network()
    path = tmp_path / "network.nc"
    n.export_to_netcdf(path)
    with xr.open_dataset(path) as ds:
        assert _electrical_buses(ds) == {"north", "south"}


def test_bill_returns_none_when_the_file_has_no_bus_table():
    from scripts.consumer_bill.project_future_bill import _electrical_buses

    assert _electrical_buses(xr.Dataset()) is None
    assert _electrical_buses(xr.Dataset({"buses_i": ("buses_i", ["a"])})) is None


def test_bill_without_a_country_variable_falls_back_to_names_and_carriers():
    from scripts.consumer_bill.project_future_bill import _electrical_buses

    ds = xr.Dataset({"buses_carrier": ("buses_i", ["AC", "H2", "AC"])},
                    coords={"buses_i": ["gb", "H2", "NO External"]})
    assert _electrical_buses(ds) == {"gb"}
