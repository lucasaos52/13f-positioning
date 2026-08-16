# Classical 13F factor positioning — results

Run `0164da7a10ac`. Holdings are folded by CIK and observed at quarter-end + 45 calendar days; trading starts on the next market date. Static crowding is a placebo/risk state, not a short rule.

## Scope chosen before looking at returns

Implemented H1–H5 using SIZE, MOMENTUM, BETA, LOWVOL and LIQUIDITY. Accounting factors and sector-neutral variants are excluded because no point-in-time fundamentals/sector history exists locally. H3 and H5 are the directional hypotheses; H1 measures state and H4 is the required placebo.

## Data and measurement validation

- Exposure infrastructure: 51 quarter snapshots; 749 managers; median 35 managers/quarter.
- Directional flow panel: 23 quarter snapshots; median 93 managers/quarter after requiring both adjacent quarters to have >=50 eligible managers.
- Synthetic sign checks passed: 9/9.
- Maximum rotation identity error: 4.441e-16.
- Mean rejected impossible market caps/date: 49.4.
- Coverage sensitivity (quarters with >=50 eligible managers | median managers): 50%: 51 | 1710; 70%: 35 | 205; 80%: 24 | 35; 90%: 0 | 6.

The market-cap benchmark uses a 99th-percentile cap because the free Yahoo share history contains split artifacts. This is preferable to allowing multi-quadrillion-dollar phantom firms to dominate the baseline, but it is still a documented data-quality approximation.

## Pre-registered hypothesis tests

| hypothesis                 | term                    |     coef |      se |        t |   n |   clusters |
|:---------------------------|:------------------------|---------:|--------:|---------:|----:|-----------:|
| H1_position_persistence    | position                |  0.77329 | 0.08625 |  8.96518 | 110 |         22 |
| H2_rotation_persistence    | rotation                |  0.06332 | 0.20484 |  0.30911 | 110 |         22 |
| H3_flow_continuation       | pressure_cs_z           | -0.0058  | 0.01908 | -0.30401 | 110 |         22 |
| H4_static_crowding_placebo | position_cs_z           | -0.01402 | 0.03307 | -0.42405 | 110 |         22 |
| H5_adverse_flow_x_crowding | adverse_shock           | -0.12079 | 0.0659  | -1.83295 | 110 |         22 |
| H5_adverse_flow_x_crowding | vulnerability_rank      | -0.04998 | 0.15776 | -0.31677 | 110 |         22 |
| H5_adverse_flow_x_crowding | adverse_x_vulnerability |  0.1779  | 0.13678 |  1.30063 | 110 |         22 |

### Verdict at the registered sign

- state persistence: SUPPORTED (b=+0.7733, t=+8.97; expected positive).
- rotation persistence: NOT SUPPORTED (b=+0.0633, t=+0.31; expected positive).
- flow continuation: NOT SUPPORTED (b=-0.0058, t=-0.30; expected positive).
- static-crowding placebo: SUPPORTED (b=-0.0140, t=-0.42; expected null).
- adverse flow x crowding: NOT SUPPORTED (b=+0.1779, t=+1.30; expected negative).

Interpret signs as registered: H1/H2/H3 positive; H4 near zero; H5 interaction negative. Statistical evidence is descriptive with only 22 forward-return quarters; all panel errors are clustered by quarter.

## Tradable composite backtests (shared multifactor engine)

| strategy                |   fee_bps |   ann_return |   ann_vol |   sharpe |   max_drawdown |   ann_turnover |
|:------------------------|----------:|-------------:|----------:|---------:|---------------:|---------------:|
| flow_continuation       |         0 |      -0.0112 |    0.231  |  -0.0483 |        -0.4448 |         5.491  |
| funding_x_crowding      |         0 |      -0.1883 |    0.2398 |  -0.7851 |        -0.7641 |         5.3588 |
| static_crowding_placebo |         0 |       0.0376 |    0.2079 |   0.1808 |        -0.3504 |         2.7662 |
| flow_continuation       |         5 |      -0.0166 |    0.231  |  -0.0718 |        -0.4533 |         5.491  |
| funding_x_crowding      |         5 |      -0.1926 |    0.2398 |  -0.8032 |        -0.7713 |         5.3588 |
| static_crowding_placebo |         5 |       0.0347 |    0.2079 |   0.167  |        -0.3541 |         2.7662 |
| flow_continuation       |        10 |      -0.022  |    0.2311 |  -0.0951 |        -0.4617 |         5.491  |
| funding_x_crowding      |        10 |      -0.197  |    0.2398 |  -0.8212 |        -0.7783 |         5.3588 |
| static_crowding_placebo |        10 |       0.0319 |    0.208  |   0.1532 |        -0.3579 |         2.7662 |
| flow_continuation       |        20 |      -0.0327 |    0.2313 |  -0.1414 |        -0.4782 |         5.491  |
| funding_x_crowding      |        20 |      -0.2056 |    0.24   |  -0.8566 |        -0.7917 |         5.3588 |
| static_crowding_placebo |        20 |       0.0261 |    0.2081 |   0.1256 |        -0.3653 |         2.7662 |

`flow_continuation` maps active rotation pressure back to stocks through current factor scores. `funding_x_crowding` trades only adverse funding shocks against the direction of crowded positioning. `static_crowding_placebo` tests the tempting but unsupported crowded-means-short shortcut; it is never promoted based on its realized return.

## Latest positioning dashboard (sqrt-AUM manager weights)

| factor    |   position |   dispersion |   breadth_pos |   breadth_neg |   hhi_pos |   hhi_neg |
|:----------|-----------:|-------------:|--------------:|--------------:|----------:|----------:|
| size      |     0.1783 |       0.7314 |        0.273  |        0.1663 |    0.0228 |    0.0167 |
| momentum  |     0.2218 |       0.6865 |        0.2117 |        0.0339 |    0.0345 |    0.0331 |
| beta      |     0.5211 |       0.5257 |        0.5458 |        0.0268 |    0.0139 |    0.0889 |
| lowvol    |    -0.2349 |       0.4813 |        0      |        0.212  |    0.027  |    0.0282 |
| liquidity |    -0.0293 |       0.6116 |        0.1839 |        0.2439 |    0.0149 |    0.0267 |

## Limitations

- The label is **13F long-equity exposure**, not the manager's total fund exposure; shorts, swaps and cash are absent.
- The ticker/price universe is survivor-biased. Results are research diagnostics, not production evidence.
- Sector-neutral exposures are not fabricated from today's sector map. Add them only with a PIT SIC/GICS history.
- The factor-flow tests have K=5 and only 22 usable forward-return quarters; no multiple-testing search was performed.
