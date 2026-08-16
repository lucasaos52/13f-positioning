# Manager Factor Positioning — experiment plan

Source doc: `factors/factor_positioning_classical/13F_manager_factor_crowding_implementation.md`.
Organized against what this project has already learned (state has no arrow; flow
does; skill-weighting hurts; removing mechanics ex-ante destroys signals).

## What gets executed now (run_mfp.py, one script, one quarter loop)

| # | experiment | doc priority | why now |
|---|---|---|---|
| E1 | `E_t = W_t X_t` manager x factor panel, Tier-0 market-data factors only (SIZE, MOM, BETA, LOWVOL, STREV, LIQ), active vs VW-universe benchmark, coverage >= 80% | P1 | foundational infra; everything else reads this table. Stored permanently as parquet (the doc's "critical rule"). |
| E2 | Rotation decomposition (price drift / characteristic drift / active trading, exact 3-way) + FactorFlow pressure in factor-ADV units | P3 | the doc's own "first genuinely predictive experiment"; matches this project's DFR lesson — measure all components, residualize nothing ex-ante |
| E3 | Funding-induced factor flow `sum_m f_m * E_prev` using the VALIDATED implied-flow instrument, + H5 interaction (crowding x adverse funding shock) | P4 | highest synergy: bridges our best instrument to the new layer |
| E4 | Factor Rebalancing Mismatch (Peng-Wang), momentum only, mechanism-first: Mismatch -> next-q dIO before any return test | P6 | the stock-level extension with the strongest literature bridge; feeds the champion universe protocol if the mechanism confirms |
| E5 | Positioning dashboard (position, breadth, dispersion, tail HHI) | P2 | free byproduct of E1; explicitly NOT traded (H4 says state has no arrow) |

Validation before alpha (doc §17): synthetic known books (top-decile momentum,
small-cap) must land at the right z; placebo shuffling characteristics within
size quintiles must destroy the time-structure of aggregate positioning.

Pre-registered hypotheses: H1 position persistence (state), H2 rotation
persistence, H3 pressure -> short-horizon factor CONTINUATION (our distress
evidence gives continuation the stronger prior), H4 crowding alone ~ nothing,
H5 crowding amplifies adverse funding shocks (interaction negative), H6
mismatch -> owner-consistent future trading (dIO), then negative returns.

## Deliberately deferred, with reasons

- **Sector dummies / sector-neutral exposures**: no sector map in the repo and
  Yahoo `info` fetches for ~3.9k tickers are slow and non-PIT. Extension once a
  cached sector map exists; the raw/global version answers the first-order
  question.
- **Value/Quality/Investment via Yahoo fundamentals**: yfinance statements only
  reach ~4 years back, so a backtest would start ~2022 (~16 quarters) — enough
  for descriptive positioning, far too short for the panel tests. The doc itself
  flags non-PIT Yahoo fundamentals as the thing NOT to do. If wanted later:
  annual statements, reporting lag of 3 months applied, flagged as descriptive
  only. The honest PIT route is SEC XBRL (doc P5) — real work, separate sprint.
- **Factor Stress Matrix (Gamma = L' Sigma_u L, doc P7)**: only after E1-E3
  validate; our eigen/network family precedent demands the measurement layer
  first. The building blocks (flow covariance without forming MxM) already
  exist in new_positioning S4.
- **Return-beta exposures (doc §2.2/2.3)**: robustness layer, not headline —
  same choice as the doc recommends.
