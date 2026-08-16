# flow_forecast — predicting inflow/stop-out points one quarter ahead (Coval-Stafford clock)

Can NEXT quarter's manager flow be forecast from this quarter's flow +
performance (Coval-Stafford 2007 expected-flows construction, with the
Sirri-Tufano convexity term), so that distressed managers are identified
BEFORE their filing reveals it? Mechanism-first gates, expanding
strictly-past coefficients, 45 OOS quarters, ~1,270 managers/quarter.

## G1 — is the implied flow forecastable?

- OOS rank-corr (predicted vs realized flow): **−0.015 (t=−1.21)**, 45 quarters

**FAIL.** 13F-implied flow carries no one-quarter-ahead predictability
from its own lag + book performance.

## G2 — do PREDICTED-distressed managers actually sell?

- fraction sold next quarter: predicted-distressed 0.265 vs predicted-inflow 0.252 (delta **t=+0.69**)
- contemporaneous benchmark (REALIZED distress, same machinery): 32.5% vs 16.2%, **t=+20.9**

**FAIL** — as it must, given G1: sorting on a noise forecast produces two
indistinguishable groups.

## G3 — short the PREDICTED supply basket (one quarter before the filing reveals it)

- predicted-basket excess: +0.0065/qtr (t=+1.53) — wrong sign, no edge. Not evaluated further (gated).

## Verdict

**The forecast route dies at the mechanism gate, cleanly.** The
flow→forced-selling mechanism is real and strongly validated
*contemporaneously* (t=+20.9), but our flow measure — implied from 13F
book changes — is not forecastable one quarter ahead. This is coherent
with the literature rather than against it: Coval-Stafford / Lou build
expected flows from **reported mutual-fund TNA flows**, which are
persistent investor decisions; 13F-implied flow additionally mixes
leverage changes, non-13F assets, and measurement error from the frozen-
book approximation, which plausibly destroys the AR structure. The
retraction of the daily anticipation overlay (stress_short) and this
quarterly result now bracket the same conclusion from both clocks:
**distress is information when observed, not when predicted** — with our
instruments, the value is in reacting fast to the filing (fire_calendar,
distress_mom), not in front-running it.

Shrinkage corollary: NMF-cluster (James-Stein) pooling of per-manager
flow sensitivities remains the right *estimator* design, but there is no
signal to shrink — pooled OLS (maximal shrinkage) already shows zero.
Would become relevant only with reported-TNA flow data (mutual funds /
ADV filings), which is the honest data upgrade this idea needs.
