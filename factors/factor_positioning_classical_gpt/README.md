# Classical 13F manager factor positioning

Implementation of the local memo `13F_manager_factor_crowding_implementation.md`.
It builds the permanent manager-by-factor product `E_t = W_t X_t`, separates
state from flow, tests H1–H5, and sends the directional stock composites to the
shared multifactor `Portfolio`/`Backtest` engine.

## Selected hypotheses

- H1: aggregate factor position is persistent (measurement/state).
- H2: active factor rotation persists one quarter.
- H3: active rotation pressure predicts short-horizon factor continuation.
- H4: static crowding has weak/no directional alpha (required placebo).
- H5: adverse funding flow is more damaging against crowded positioning.

The directional candidates are H3 and H5. H1 is infrastructure and H4 prevents
the invalid shortcut “crowded = short”. H6 mismatch is deferred because a local
experiment already validates its trading mechanism but finds no return edge.

## Factors and signs

All inputs are available by the formation date and are winsorized and
cross-sectionally standardized each date:

- `size`: positive means smaller market cap;
- `momentum`: positive means prior 12–1 month winner;
- `beta`: positive means high market beta;
- `lowvol`: positive means low residual volatility;
- `liquidity`: positive means high 63-day median dollar volume.

Value, profitability, investment and sector-neutral variants are not fabricated
from present-day Yahoo metadata. They require point-in-time SEC XBRL and PIT
SIC/GICS history.

## Point-in-time and data-quality rules

- Holdings are read at quarter-end + 45 calendar days using actual filing dates.
- Filing versions are resolved per CIK: restatement replaces, later NEW HOLDINGS
  amendments add. Only afterwards are rows aggregated to reporting filer.
- Quarter-end exposure and tradable decision-date exposure are separate fields.
- ETFs/funds are excluded because issuer size/beta of a wrapper is not its
  underlying factor exposure.
- Impossible Yahoo market caps are rejected. The benchmark caps remaining
  market caps at the cross-sectional 99th percentile because historical shares
  contain severe split artifacts. This approximation is reported, not hidden.
- Trading begins on the first market date strictly after the knowledge cut. The
  core engine uses lagged weights, price drift, borrow and a 0/5/10/20 bps cost
  ladder.
- The measurement universe uses price >= $1 and median ADV >= $0.1m so an
  otherwise observable small-cap holding is not mislabeled as missing. The
  tradable backtest remains stricter at price >= $5 and ADV >= $5m.

## Run

Use the environment already present in this repository:

```powershell
& '..\..\crowdflow\.venv\Scripts\python.exe' .\run_research.py --smoke
& '..\..\crowdflow\.venv\Scripts\python.exe' .\run_research.py
```

Outputs:

- `data/manager_factor_exposure.parquet`: permanent manager-level matrix;
- `data/manager_factor_rotation.parquet`: exact four-component decomposition;
- `data/factor_positioning_dashboard.csv`: position/breadth/dispersion/tails/HHI;
- `data/factor_flow_panel.csv`: H1–H5 panel;
- `data/coverage_sensitivity.csv`: honest 50/70/80/90% coverage audit;
- `results/hypothesis_tests.csv`: quarter-clustered panel tests;
- `results/backtest_summary.csv`: shared-engine, costed strategy statistics;
- `results/REPORT.md`: research verdict and limitations.

## Tests

```powershell
& '..\..\crowdflow\.venv\Scripts\python.exe' -m pytest .\tests -q -p no:cacheprovider
```
