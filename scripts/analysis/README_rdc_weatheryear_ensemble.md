# 41-weather-year residual-demand panels (2030 / 2040)

Script: `scripts/analysis/rdc_weatheryear_ensemble.py`
Tests: `tests/unit/test_rdc_weatheryear_ensemble.py`

## Why this exists

The residual-demand figure in the LDES policy brief has two kinds of panel:

| Panel | Drawn by | Model behind it |
|---|---|---|
| Weather year 2010 | `plot_rdc_combined.R::proc_bot` | whole-network PyPSA-GB dispatch, `HT30_disp_w2010` / `HT40_disp_w2010` (`resources/market/*_wholesale_{dispatch,storage,links}.csv`) |
| "41-yr mean" | `plot_rdc_combined.R::proc_top` | `resources/analysis/weatheryears/<ty>_wy<wy>_genmix.parquet`, written by `seasonal_storage_weatheryears.py` |

The published 41-year numbers are 60.1 / 20.2 TWh/yr (2030) and 69.9 / 62.6 TWh/yr (2040), read here as
(residual demand, residual surplus). They come from the second route, which is not the same model as the 2010 panel:

1. **Single node** rather than the Reduced network, so there is no transmission constraint and no network losses.
2. **Different demand**: a national temperature-response model (`demand_weather_model.project_demand`, central case,
   fitted on 2019 ESPENI) rescaled to the FES ED1 total, instead of the network run's demand.
3. **Different VRE**: a national fleet capacity factor (REPD fleet) times FES capacity for onshore wind, offshore wind
   and solar, instead of site-level profiles on the network.
4. **Fixed firm availability** at the reference run's mean.
5. **Fleet taken from `HT{30,40}_market_w2010`**, the two-stage market run, not from `*_disp_w2010`.
   `surplus_absorption_2030_2040.py` already notes these two give materially different hydrogen flows.

So the 2010 member of the published 41-year ensemble is not the 2010 panel, and the gap between "41-yr mean" and
"weather 2010" mixes weather variation with these model differences.

## Method

`--source network` (default) applies the 2010 panel's accounting to one network dispatch per weather year:

```
demand   = sum(all generator output) + storage-unit net output + (H2 turbine p0 x 0.50 - electrolysis p0)
residual = demand - wind - solar - nuclear - must-run firm (biomass, biogas, landfill/sewage gas, EfW,
           advanced biofuel, large hydro, geothermal)
residual demand  = sum of positive hours,  residual surplus = minus the sum of negative hours  (TWh/yr)
```

Generator classes are matched on component name with the same regular expressions as `plot_rdc_combined.R`, so a run
with `--weather-years 2010` gives the 2010 panel's numbers. Interconnector links are not part of the accounting, as in
the R script. Ensemble statistics follow `proc_top`: each year's residual is sorted into a duration curve on 400 points,
the panel shows the mean curve and the P10 to P90 band, and the TWh labels are the mean of the per-year values. The
figure uses the published panel's colours, label positions and shared y-axis.

`--source screen` re-runs the published method (`proc_top`) on the genmix parquets, so the published numbers can be
reproduced and compared. `--source both` writes both and puts them side by side in `rdc_wy_summary.csv`, next to the
published values.

For each weather year the script reads `resources/market/<scn>_wholesale_*.csv` first and falls back to
`resources/network/<scn>_solved.nc`. `<scn>` comes from `--scenario-template`:

| Template | Runs |
|---|---|
| `HT{yy}_disp_w{wy}` (default) | same family as the 2010 panel; only w2010 exists so far |
| `HT{yy}_gap_w{wy}` | gap-demand campaign, full-year Reduced dispatch, market off (`myriad/README_GAP_RUN.md`) |
| `HT{yy}_esp_w{wy}` | two-stage market campaign, ESPENI demand (`myriad/README_FES2METHODS.md`) |

```bash
python scripts/analysis/rdc_weatheryear_ensemble.py --inventory-only --source both   # what is on disk
python scripts/analysis/rdc_weatheryear_ensemble.py --scenario-template "HT{yy}_gap_w{wy}"
python scripts/analysis/rdc_weatheryear_ensemble.py --source both
```

Outputs go to `resources/analysis/rdc_weatheryear_ensemble/`: per-year metrics, ensemble curves, the summary against
the published values, an inventory of every input looked for (`rdc_wy_inputs.csv`, with a `found` column), and
`rdc_wy_<source>.png/.pdf`.

## Inputs and what is missing

None of the 2030/2040 inputs are tracked in git (`resources/` is not tracked). On the analysis PC
(`C:\Users\ucbqnge\PyPSA-GB`, checked 2026-11-23) none of them are present either. The R scripts read them from
`C:/models/pypsa-gb/resources/`, which is not on that machine. To reproduce:

* **Published numbers (`--source screen`)**: `resources/analysis/weatheryears/2030_wy{1985..2025}_genmix.parquet` and
  `2040_wy{1985..2025}_genmix.parquet` (82 files).
* **2010 panel (check)**: `resources/market/HT30_disp_w2010_wholesale_{dispatch,storage,links}.csv` and the `HT40` equivalents.
* **Consistent 41-year panels (`--source network`)**: 82 network runs, one of
  * `resources/market/HT{30,40}_<tag>_w{1985..2025}_wholesale_{dispatch,storage,links}.csv`, or
  * `resources/network/HT{30,40}_gap_w{1985..2025}_solved.nc` (from Myriad with `myriad/pull_gap_results.ps1`).

For like-for-like panels, the 2010 panel and the 41-year panels should come from the same run family. If the gap
campaign is used for the 41 years, redraw the 2010 panel from `HT{30,40}_gap_w2010` too, or confirm that
`*_disp_w2010` was built with the same settings.

## Check on runs that exist: HT 2050, 31 weather years

The analysis PC has whole-network wholesale runs `HT50_w{1985..2011, 2013..2016}`. Running
`--scenario-template "HT{yy}_w{wy}" --target-years 2050` on them takes about 2 minutes and gives:

| | Residual demand (TWh/yr) | Residual surplus (TWh/yr) | Peak (GW) |
|---|---|---|---|
| Weather 2010 | 82.9 | 25.5 | 65.8 |
| 31-year mean | 68.0 (P10 57.6, P90 79.0) | 28.3 (P10 24.1, P90 45.1) | 63.2 |

So weather year 2010 is in the top decile for residual demand: a single-year 2010 panel overstates the typical
deficit by about 15 TWh/yr in 2050.

Caveat found in this check: surplus steps from about 25 TWh/yr (1985–2011) to about 47 TWh/yr (2013–2016). The
2013–2016 runs were written a day or more later (19–20 Oct 2026 vs 18 Oct), their links CSVs are four times larger, and
storage charging rises from about 30 to about 48 TWh. They look like a different model version, so do not pool runs
from different vintages in one ensemble without checking that they share settings.
