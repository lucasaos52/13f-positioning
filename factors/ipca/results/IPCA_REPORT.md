# IPCA (Kelly-Pruitt-Su) on the 10-characteristic panel - 50 quarters, instruments: const + size, mom, beta, lowvol, strev, liq, new_conv, dbreadth, distress, pressure

ALS verified line-by-line against the reference package (bkelly-lab/ipca): N_t-weighted Gamma step, intercept as pre-specified factor, Walpha wild bootstrap (t5 multiplier, 500 draws).

## In-sample fit and the alpha question

| K | total R2 | predictive R2 | Walpha (Gamma_a'Gamma_a) | bootstrap p | new_conv managed-pf alpha t (secondary) |
|---|---|---|---|---|---|
| 1 | 0.097 | 0.0133 | 5.95e-02 | **0.516** | t=+6.80 |
| 2 | 0.109 | 0.0147 | 2.81e-02 | **0.578** | t=+6.56 |
| 3 | 0.114 | 0.0162 | 3.98e-02 | **0.412** | t=+5.78 |
| 4 | 0.118 | 0.0162 | 2.96e-02 | **0.594** | t=+5.22 |

Reading: total R2 = common factor structure in the managed returns; predictive R2 = what a constant risk premium explains. Walpha is the KPS test of Gamma_alpha = 0: a small p-value means the characteristics carry premium NOT explained by exposure to the K latent factors (alpha). The secondary column is the interpretable version: time-series alpha of the new_conv-managed portfolio on the factors.

## OOS ranking race (K=3, expanding, same protocol as the A/B/C combiner race)

- **restricted E[r]=z'Gamma*lambda (risk only)**: spread +0.0509/qtr (t=+2.39), Sharpe +0.73, IC +0.0231
- **unrestricted + z'Gamma_alpha (risk + alpha)**: spread +0.0595/qtr (t=+3.07), Sharpe +0.97, IC +0.0354
- delta unrestricted vs restricted: +0.0086/qtr (t=+1.52)
- reference on the same protocol: A (FM/Lewellen) Sharpe 0.86, C (naive rank-average) 0.74 - expanded universe

If Walpha rejects, the alpha leg should be where the OOS ranking power lives - the two results check each other.

## Paired deltas on the common 38 OOS quarters (vs the score_model race)

- unrestricted IPCA vs A (FM/Lewellen): **+0.0055/qtr, t=+2.08**
- unrestricted IPCA vs C (naive): +0.0337/qtr, t=+2.37
- restricted IPCA vs A: -0.0030/qtr, t=-0.75 (flat)

## Verdict (revised after a second review; supersedes the first cut)

1. **The formal KPS Walpha test does not reject** Gamma_alpha = 0
   (p 0.41-0.59 at every K). With T=50 the test refits an 11-dim alpha
   vector under a wide bootstrap null - low power is expected (KPS run
   it on 600+ months); absence of rejection is not evidence of absence,
   but it is the formal result and is reported as such.
2. **Correction of the first-cut mechanism story.** The unconditional
   forecast of the unrestricted model, z'(Gamma_b*lambda + Gamma_a),
   is NOT rank-restricted: Gamma_a is a free L-vector, so the sum
   spans all of R^L. The rank-K restriction binds only the *time
   variation* of expected returns, which a constant-lambda forecast
   does not use. "Compression denoises while alpha keeps the premium"
   was therefore wrong; the unrestricted IPCA is best understood as a
   *different unrestricted estimator of the same 11 premia* (pooled,
   N_t-weighted, structure-regularised) versus FM's equal-weighted
   average of quarterly cross-sectional slopes. Internal confirmation:
   the leg that IS genuinely compressed (restricted, z'Gamma*lambda)
   does not beat FM (paired t=-0.75).
3. **Evidence strength, stated by the project's own funnel rules.**
   IPCA+alpha entered after the A/B/C race was scored - it is a
   post-hoc, non-preregistered fourth entrant. Its paired edge over FM
   (+0.55%/qtr, t=+2.08, Sharpe 0.97 vs 0.86) does not clear the
   pre-registered promotion bar (t>=2.57) and the alpha-specific OOS
   delta (unrestricted vs restricted, the comparison that isolates
   Gamma_a) is t=+1.52 - suggestive, not decisive. Status: CANDIDATE
   combiner, best point estimate on the protocol; FM remains the
   production combiner pending fresh-sample confirmation.
4. What survives cleanly: the factor-structure measurement (R2 table)
   and the time-series spanning alpha of the new_conv managed
   portfolio on the latent factors (t +5.2 to +6.8; secondary
   statistic, in-sample factors, OLS t) - the interpretable version of
   "the 13F premium is not spanned", labelled as such.