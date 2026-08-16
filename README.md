# 13F Institutional Positioning — Research System

A point-in-time research system for SEC 13F institutional holdings:
bitemporal data engineering, a pre-registered signal research funnel,
and a production backtest engine. Two factors survive the funnel —
**NCB (New-Conviction Breadth)** and **FSS (Forced-Sale Supply)** —
and the full research trail, including every negative result and one
explicit retraction, is documented in the paper.

**Deliverables**: [`memo/memo.pdf`](memo/memo.pdf) — the 5-page memo;
[`memo/main.pdf`](memo/main.pdf) — the complete technical report
(data engineering, signal taxonomy, hyperparameter surfaces,
net-of-cost engine results, long-only implementation). LaTeX sources
in `docs/paper/`.

## Quickstart

```bash
git clone <this repo> && cd 13f_v2
export CROWDFLOW_USER_AGENT="Your Name you@example.com"   # SEC contact
python bootstrap.py          # deps -> EDGAR lake -> PIT store ->
                             # crosswalk -> price panels (idempotent)
python run_experiments.py    # the full experiment pipeline
python run_experiments.py --quick    # core results only
```

`bootstrap.py --status` shows which data stages already exist; every
stage is skipped when its output is present, so partial clones and
re-runs are cheap. The EDGAR download needs only a contact e-mail in
the User-Agent (SEC policy) — no credentials. Prices come from Yahoo
and are cached on first use.

**What gets built locally** (none of it ships in the repo): the EDGAR
lake (~5 GB, ~1–2 h download from SEC bulk datasets), the quarterly
point-in-time store (~10 min build), the CUSIP→ticker crosswalk
(name matching against the live exchange directory + ~230
hand-verified corrections applied by `notebooks/apply_handmap.py`),
and the Yahoo price panels (~4 k tickers; first fetch takes a while
and Yahoo throttles a small tail — the market layer retries and
fails closed on names it cannot price). The repository itself is
~40 MB: code, module reports, the paper, and one 9 MB audited ETF
reference file kept in-repo so the ETF pipeline need not be re-run.

## Repository map

```
crowdflow/        EDGAR ingestion package: bulk DERA datasets + raw
                  filing parsers, bitemporal PIT store, rejection
                  ledger.  make setup && make test (63 tests, offline)
factors/          the research modules — one directory per experiment,
                  each script carries its pre-registration in the
                  docstring and writes results/<MODULE>_REPORT.md
  general_plan/     shared infra: PIT panel access, backtest helpers,
                    quarterly store builder (prep_quarters.py)
  general_predictive_signals/  the 17-signal catalogue
  fire_calendar/    flow instrument + forced-sale mechanism (t=+20.9)
  champion_hyperopt/, distress_hyperopt/  bootstrap hyperparameter
                    surfaces (arXiv:2510.12725 protocol)
  score_model/      Fama-MacBeth combiner race
  ipca/             Kelly-Pruitt-Su IPCA challenger
  ml_positioning/   ML cross-check on the change-variable family
  production_suite/ the net engine: costs, borrow, PnL series,
                    long-only cap-weighted tilt
notebooks/        crosswalk construction + descriptive analyses
docs/
  paper/          LaTeX source of the report (main.tex, figs, tables)
data-quality-check/  the coverage audit + expanded-universe campaign
```

## Reading order

1. `docs/paper/main.pdf` — everything, in order.
2. `data-quality-check/EXPANDED_UNIVERSE_RESULTS.md` — the coverage
   fix and the 24-run re-verification campaign (one retraction).
3. Any `factors/*/results/*_REPORT.md` — per-module verdicts with
   their pre-registrations.

## Conventions

- Decisions at quarter-end + 45 days; holdings only through the PIT
  store (`as_of`); quintile EW spreads; Newey-West t; Spearman IC.
- Signals are residualized on size/liquidity only when a formal
  placebo (dart-throwing value-weighted managers) shows the raw
  construction is mechanically correlated with them.
- Verdicts are paired quarter-by-quarter deltas on common samples;
  families of tests carry Bonferroni bars; post-hoc results are
  candidates, never promotions.
- Failures are loud: zero-row parses raise, missing quarters raise,
  and every data-quality decision is counted in a rejection ledger.
