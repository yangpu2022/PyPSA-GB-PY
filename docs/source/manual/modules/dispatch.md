# Single solve and constraints: `scripts/solve/`

Up: {doc}`../subsystems/dispatch`. The two-stage market: {doc}`market`.

| Module | Rule | Does |
|---|---|---|
| `finalize_network.py` | `finalize_network` | the clean `{scenario}.nc` and its summary (`normalize_bus_coordinates`) |
| `solve_network.py` | `solve_network` | the single network-constrained solve: `configure_solver`, `apply_load_shedding_limits`, `apply_transmission_relaxation`, `apply_line_rating_overrides` |
| `secured_boundaries.py` | (imported) | NESO's sum-of-flow boundary limits for future years (`build_secured_boundary_specs`) |
| `hydro_constraints.py` | (imported) | large-hydro inflow and pumped-hydro constraints |
| `link_outages.py` | (imported) | declared DC link outages in historical years |
| `deep_network_validation.py` | (checks) | demand, renewables, thermal, storage and interconnector checks on a network |

## Conventions

- `solve_network.py` and the market solves share these helpers: a constraint added here for the single solve should
  be checked against both market stages.
- Load shedding is a generator at the value of lost load; any of it in a result is unserved energy, reported apart.

Debugging: infeasible or shedding load, compare `n.generators.p_nom.sum()` with peak demand and look for isolated
buses and very small ratings; high curtailment, check `n.lines_t.p0.abs() / n.lines.s_nom` and the boundary limits.
