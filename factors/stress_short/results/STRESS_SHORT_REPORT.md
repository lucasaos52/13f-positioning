# stress_short - short no book do gestor no DIA da deteccao de stress

Basket = top-20 nomes por dolar/ADV do gestor recem-hot; placebo = gestor calmo do mesmo tercil de AUM no mesmo dia. Pre-registro: CAR do basket NEGATIVO (tese short), placebo ~0.

- 16757 eventos em 49 tri

- **CAR +5d**: tese -0.0003 (t=-0.32) | placebo -0.0003 (t=-1.43) | delta +0.0002 (t=+0.37)
- **CAR +10d**: tese -0.0001 (t=+0.14) | placebo -0.0004 (t=-1.02) | delta +0.0005 (t=+0.76)
- **CAR +20d**: tese -0.0004 (t=-0.26) | placebo -0.0009 (t=-0.87) | delta +0.0005 (t=+0.52)

## PnL tatico do short (hold 5d, media dos baskets ativos por dia)
- 2435 dias ativos
- **BRUTO**: Sharpe -0.05 | -0.3%/aa nos dias ativos
- **líquido trading, BORROW=0**: Sharpe -0.86 | -5.3%/aa nos dias ativos
- **líquido trading + borrow do motor**: Sharpe -0.94 | -5.8%/aa nos dias ativos
## RETRACTION (2026-08-16, expanded-universe re-run)

The delta t=-2.16 does NOT survive the crosswalk fix: with complete books
the coverage-eligible sample grows 22->49 quarters and 3.6k->16.8k
events, and the effect is zero EVERYWHERE - including the 2020+ window
where it was originally measured (delta t=-0.50 there; t=+1.51 in the
newly-eligible 2013-19 years). The original result was an artifact of
eligibility selection (only well-mapped books passed the coverage
filter). The overlay candidacy is WITHDRAWN. Note the funnel had already
declined promotion ("suggestive, conditional on overlap") - the
discipline held. What survives of this module: the daily synthetic-book
machinery (reused by daily_monitor) and the negative finding itself.
