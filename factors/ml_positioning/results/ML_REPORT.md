# ml_positioning - predicted size-residualized excess return from the 12 change variables

- walk-forward expanding, 12q warm-up; features winsor-z per quarter; target rank-z of size-residualized forward excess (notebook practices); no vol weighting

| model | spread raw/q (t) | Sharpe | spread resid/q (t) | IC |
|---|---|---|---|---|
| ridge | -0.0064 (-0.78) | -0.24 | +0.0245 (+3.18) | +0.0091 |
| knn | -0.0102 (-1.15) | -0.34 | +0.0179 (+2.87) | +0.0072 |
| hgb | -0.0046 (-0.42) | -0.13 | +0.0271 (+3.07) | +0.0205 |
| rf | -0.0163 (-1.27) | -0.42 | +0.0218 (+2.56) | +0.0175 |
| ens | -0.0115 (-1.08) | -0.34 | +0.0263 (+3.36) | +0.0157 |

## Gates

- G2 hgb vs ridge (nonlinear info?): +0.0018/q (t=+0.27)
- G2 rf vs ridge (nonlinear info?): -0.0099/q (t=-1.30)
- G2 knn vs ridge (nonlinear info?): -0.0038/q (t=-0.71)
- G2 ens vs ridge (nonlinear info?): -0.0051/q (t=-0.99)
- G1 reference: champion alone t~+3.5, Sharpe ~1.05 on this protocol; FM combiner Sharpe 0.86 (10 predictors incl. classical)

## HGB permutation importance (last OOS quarter)

- new_conviction: +0.0039
- exit_rate: +0.0015
- dbreadth: +0.0010
- ti: +0.0006
- entry_rate: +0.0006
- dio_2q: +0.0006
- dbreadth_common: +0.0005
- d_days_adv: +0.0001
- net_entry: +0.0001
- dio: -0.0002
- vi: -0.0006
- late_minus_early_dio: -0.0025

## Incremental test: does the ML add anything over the champion alone?

Same 37 OOS quarters, same size-residualized metric:

- ridge prediction: +0.0245/q (t=+3.18)
- **new_conviction alone: +0.0312/q (t=+3.50)** - the single signal
  BEATS the 12-variable ML
- paired delta (ML - champion): -0.0067/q (t=-1.09)
- mean rank-corr(prediction, new_conviction): +0.52
- ML orthogonalized within new_conv quintiles: +0.0029/q (t=+0.40) -
  nothing left

## Verdict

1. **The change-variable family predicts the size-hedged cross-section
   OOS** - every architecture lands t=+2.6 to +3.4 on the residualized
   target. The family is real.
2. **All of it is the champion.** new_conviction alone beats the full
   ML; the prediction is 0.52 rank-correlated with it; orthogonalized
   to it the ML is zero (t=+0.40); and the boosting's own permutation
   importance ranks new_conviction first by 3x. The champion is,
   empirically, the sufficient statistic of the change family.
3. **G2 fails cleanly: no nonlinear premium.** hgb vs ridge t=+0.27,
   rf/knn/ens negative. The linear FM already extracts what exists -
   the production choice is vindicated from a new direction.
4. **The raw-vs-residualized sign flip is the size lesson.** The
   prediction carries small-cap exposure inherited from the raw count
   features; unhedged (raw-return quintiles) that exposure cost
   -0.5 to -1.6%/q in this mega-cap regime. The tradable form of ANY
   positioning factor must be size-hedged - which the champion
   construction achieves by residualizing the signal itself.

Status: exploratory, candidate track, honest null on "ML as a new
factor" - and a THIRD independent replication router pointing at the
same signal (after the catalogue and the FM lambda): give a model 12
change variables and freedom, it rediscovers new_conviction.