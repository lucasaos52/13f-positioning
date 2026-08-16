# Distress-leg hyperparameter surface (arXiv:2510.12725 protocol)

**Provenance:** flow<-0.10 and the top-20% supply basket were set a priori and never varied before this script - the same status the champion's trio had before champion_hyperopt.

## (1) Mechanism monotonicity - no selection involved

| threshold | mean sold fraction | delta vs healthy (t) | avg n distressed/q |
|---|---|---|---|
| healthy (flow>0) | 0.231 | - | - |
| flow<-0.050 | 0.309 | +0.078 (t=+9.57) | 276 |
| flow<-0.075 | 0.333 | +0.102 (t=+10.46) | 193 |
| flow<-0.100 | 0.345 | +0.114 (t=+10.57) | 144 |
| flow<-0.150 | 0.363 | +0.132 (t=+11.41) | 91 |
| flow<-0.200 | 0.371 | +0.139 (t=+11.23) | 65 |

## (2) Price-leg surface (short-leg Sharpe; utility = -excess)

- IS 30 q (<= 2020-12-31), OOS 20 q; coupled block bootstrap block=4, B=2000

| config | IS Sharpe | boot p05 | OOS Sharpe | OOS t |
|---|---|---|---|---|
| thr-0.050_top10 | -0.14 | -0.57 | +0.60 | +1.87 |
| thr-0.075_top10 | -0.15 | -0.59 | +0.69 | +2.18 |
| thr-0.100_top10 | -0.16 | -0.60 | +0.68 | +2.05 |
| thr-0.150_top20 | -0.27 | -0.71 | +0.72 | +2.53 |
| thr-0.050_top20 | -0.26 | -0.72 | +0.62 | +2.15 |
| thr-0.050_top30 | -0.28 | -0.72 | +0.71 | +2.72 |
| thr-0.150_top10 | -0.29 | -0.73 | +0.61 | +1.75 |
| thr-0.075_top20 | -0.29 | -0.74 | +0.73 | +2.24 |
| thr-0.100_top30 | -0.28 | -0.74 | +0.79 | +2.91 |
| thr-0.075_top30 | -0.30 | -0.75 | +0.78 | +2.97 |
| thr-0.100_top20 **(default)** | -0.26 | -0.75 | +0.84 | +2.84 |
| thr-0.150_top30 | -0.30 | -0.76 | +0.72 | +2.64 |
| thr-0.200_top30 | -0.33 | -0.89 | +0.89 | +3.68 |
| thr-0.200_top20 | -0.39 | -1.05 | +0.98 | +4.02 |
| thr-0.200_top10 | -0.49 | -1.12 | +0.77 | +2.40 |

- robust p05 pick: thr-0.050_top10; a-priori default: thr-0.100_top20
- rank-corr(boot p05, OOS): -0.811; rank-corr(IS point, OOS): -0.632

## Verdict

1. **The threshold is justified by the mechanism, and the mechanism is
   monotone** (part 1, all-sample, no selection): sold-fraction rises
   smoothly 31%->37% as the cut tightens, t=+9.6 to +11.4 everywhere.
   -0.10 sits at the purity/sample-size balance (144 distressed
   managers/q vs 65 at -0.20). Not a cherry-pick.
2. **The price surface is uniform - and what it shows is REGIME, not
   hyperparameter.** Index-hedged, every one of the 15 configs loses
   modestly pre-2020 (IS Sharpe -0.14 to -0.49) and pays post-2020
   (OOS +0.60 to +0.98, t up to +4.0). The grid moves as one block:
   no config is special, no config is fragile - the short leg is a
   post-2020 (degrossing/rates) phenomenon at every setting, while
   the selling mechanism is all-sample.
3. **Instructive failure of the selection protocol itself**: rank-corr
   between IS statistics and OOS ranking is NEGATIVE (-0.81 for the
   bootstrap p05, -0.63 for the point estimate) - under a regime flip,
   any in-sample selector is anti-informative. The
   arXiv:2510.12725 machinery assumes the utility distribution is
   stationary; here it is not, and the honest conclusion is "do not
   select on this surface at all - report the regime". (Contrast with
   the champion surface, where IS did rank OOS, +0.53.)
4. **Benchmark correction propagated**: the "-4.5%/q cohort excess"
   quoted in earlier module docs was measured against the universe
   MEAN, which sits ~4%/q above the median by cross-sectional
   skewness (small-cap right tail); it overstated the alpha. The
   tradable statement is the index-hedged one above.
5. Combo implication: the distress short leg earns its place as a
   mechanism-grounded hedge/diversifier with measured regime
   dependence (conditioning via M2 is the natural pairing), not as an
   all-weather standalone alpha.