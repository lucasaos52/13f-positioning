# factors/ — the experiment modules

One directory per experiment. Every runnable module carries its
pre-registration in the script docstring and writes
`results/<MODULE>_REPORT.md` with the verdict. Shared infrastructure
lives in `general_plan/` and in the top-level engine files.

## Shared infrastructure

| file / dir | role |
|---|---|
| `general_plan/` | PIT panel access (`panel.py`), quarterly-store builder (`prep_quarters.py`), backtest helpers, market loading |
| `market_data.py` | Yahoo price/volume panels with on-disk caching (auto-fetch on miss) |
| `backtest.py`, `portfolio.py`, `filters.py`, `indicator.py`, `grouping.py` | the production engine primitives |
| `data/` | price caches (gitignored; rebuilt by `bootstrap.py`) |

## Core result modules (the paper's spine)

| module | question | headline |
|---|---|---|
| `general_predictive_signals/` | 17-signal catalogue, one protocol | NCB t=+3.54 |
| `champion/`, `new_positioning/` | NCB implementations | 8 replications, t 3.3–4.0 |
| `fire_calendar/` | flow instrument + forced selling | 34.5% vs 23.1% sold, t≈+10 |
| `champion_hyperopt/` | NCB hyperparameter surface | 36/36 configs OOS-positive |
| `distress_hyperopt/` | FSS threshold surface | mechanism monotone; price = regime |
| `score_model/` | FM combiner race | Sharpe 0.86; joint λ table |
| `ipca/` | latent-factor spanning (KPS) | premium not absorbed; candidate |
| `ml_positioning/` | ML on change variables | NCB is the sufficient statistic |
| `production_suite/` | net engine, LO tilt, PnL series | combo net Sharpe 1.02 |
| `fund_performance/` | descriptive base rates | median −3.3%/yr before fees |

## Mechanism / event-clock modules

`ragged_edge/` (the D+45 clock, measured), `stopout/`,
`window_dressing/`, `restatement_shock/`, `cascade/`, `flow_beta/`,
`flow_forecast/`, `stress_short/` (retracted — kept as the process
exhibit), `daily_monitor/`, `reversao_condicional/` (FSS panel).

## Universe / smart-money modules

`universe_variants/`, `patient_universe/`, `wbreadth/`,
`champion_noetf/`, `champion_nopassive/`, `follow_nopassive/`,
`breadth_universes/`, `ETF_strat/` (audited ETF universe).

## Crowding / structure modules

`manager_factor_positioning/` (E=WX), `grafo_crowding/`,
`absorcao/`, `overhang/`, `copycat/`, `copycat_pop/`, `ssi/`,
`ica_demand/`, `original_methods/` (NMF), `nowcasting/`,
`black_litterman/`, `drift_fluxo_rotacao/`.

## Design notes (inputs, not modules)

`new_positionog_gpt/`, `factor_positioning_classical/`,
`factor-crowding/`, `generative_modeling/`,
`stopping_after_drawdon/`, `window-dressin/`,
`etf-positioninig-strats-codex/` — the research documents that seeded
the corresponding experiments; kept for pre-registration
traceability (module docstrings cite them).
