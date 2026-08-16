# general_predictive_signals - 17 sinais, protocolo unico

Headline fixado ANTES dos retornos pelo teste do teorema (neutraliza ex-ante so o que correlacionaria com size/liquidez num mundo de gestores-macaco). raw e resid reportados para todos.

## Sumario (headline primeiro, ordenado por t EW)

| signal               | version   | theorem   |   spread_ew_q |    t_ew |   sharpe_ew |   spread_vw_q |    t_vw |      ic |   ic_ir |   mono |   n_events |
|:---------------------|:----------|:----------|--------------:|--------:|------------:|--------------:|--------:|--------:|--------:|-------:|-----------:|
| new_conviction       | resid     | True      |        0.0218 |  3.5393 |      1.0757 |        0.0911 |  2.0586 |  0.0231 |  0.3103 | 0.5765 |         49 |
| conviction_top       | resid     | True      |        0.0223 |  2.3881 |      0.6453 |        0.065  |  1.6474 |  0.0244 |  0.2277 | 0.5816 |         49 |
| breadth_level        | resid     | True      |        0.0193 |  1.4779 |      0.3624 |        0.0608 |  1.5526 |  0.0273 |  0.1951 | 0.5459 |         49 |
| late_minus_early_dio | raw       | False     |        0.0068 |  1.2369 |      0.3384 |       -0.0135 | -0.2781 | -0.0009 | -0.0165 | 0.5306 |         49 |
| entry_rate           | raw       | False     |        0.0134 |  1.2303 |      0.3568 |       -0.0807 | -2.122  |  0.0043 |  0.0472 | 0.5714 |         49 |
| dbreadth_common      | raw       | False     |        0.0049 |  1.07   |      0.2661 |       -0.0348 | -1.3483 |  0.0078 |  0.1251 | 0.5    |         49 |
| exit_rate            | raw       | False     |        0.0112 |  0.8861 |      0.2372 |       -0.0266 | -0.6681 |  0.0011 |  0.0086 | 0.5357 |         49 |
| ti                   | raw       | False     |        0.0031 |  0.56   |      0.1337 |       -0.0315 | -0.6256 |  0.0009 |  0.0136 | 0.5102 |         49 |
| vi                   | raw       | False     |        0.0016 |  0.371  |      0.0866 |        0.0212 |  0.401  | -0.0036 | -0.0776 | 0.5255 |         49 |
| net_entry            | raw       | False     |        0.0019 |  0.3311 |      0.0721 |        0.0251 |  0.4851 |  0.0022 |  0.0279 | 0.5102 |         49 |
| dbreadth             | raw       | False     |        0.0022 |  0.3202 |      0.0622 |       -0.0231 | -1.0562 | -0.0026 | -0.0246 | 0.5306 |         49 |
| d_days_adv           | resid     | True      |        0.0016 |  0.2832 |      0.0599 |       -0.0123 | -0.5932 | -0.0007 | -0.0101 | 0.5102 |         49 |
| days_adv             | resid     | True      |       -0.0066 | -0.4057 |     -0.1165 |        0.073  |  1.6295 |  0.0116 |  0.0941 | 0.5    |         49 |
| pso                  | raw       | False     |       -0.0068 | -0.7405 |     -0.1923 |        0.094  |  1.9496 |  0.0131 |  0.1975 | 0.5153 |         49 |
| dio                  | raw       | False     |       -0.0041 | -0.7587 |     -0.2211 |        0.055  |  1.5308 | -0.0078 | -0.1741 | 0.449  |         49 |
| herf_holders         | resid     | True      |       -0.0048 | -1.0875 |     -0.2886 |        0.061  |  1.8083 | -0.0121 | -0.2706 | 0.4745 |         49 |
| dio_2q               | raw       | False     |       -0.0083 | -1.8868 |     -0.4638 |       -0.0503 | -1.6218 | -0.0089 | -0.201  | 0.4796 |         49 |

## Versao alternativa (nao-headline)

| signal               | version   | theorem   |   spread_ew_q |    t_ew |   sharpe_ew |   spread_vw_q |    t_vw |      ic |   ic_ir |   mono |   n_events |
|:---------------------|:----------|:----------|--------------:|--------:|------------:|--------------:|--------:|--------:|--------:|-------:|-----------:|
| dbreadth             | resid     | False     |        0.009  |  1.8737 |      0.3414 |       -0.0097 | -0.3045 |  0.005  |  0.0577 | 0.5357 |         49 |
| net_entry            | resid     | False     |        0.0076 |  1.6623 |      0.3177 |       -0.0114 | -0.2736 |  0.0039 |  0.0528 | 0.5357 |         49 |
| late_minus_early_dio | resid     | False     |        0.0093 |  1.6231 |      0.4716 |       -0.0501 | -1.2473 |  0.0023 |  0.044  | 0.5561 |         49 |
| dbreadth_common      | resid     | False     |        0.0074 |  1.616  |      0.4158 |        0.0068 |  0.266  |  0.0082 |  0.1403 | 0.5255 |         49 |
| ti                   | resid     | False     |        0.0051 |  0.9583 |      0.2214 |       -0.0396 | -1.0286 |  0.0002 |  0.0037 | 0.5306 |         49 |
| entry_rate           | resid     | False     |        0.0046 |  0.4563 |      0.1387 |       -0.0799 | -1.9117 | -0.0048 | -0.0565 | 0.5255 |         49 |
| vi                   | resid     | False     |        0.0018 |  0.3622 |      0.0963 |       -0.0215 | -0.5749 | -0.0054 | -0.1261 | 0.5102 |         49 |
| herf_holders         | raw       | True      |       -0.0007 | -0.0627 |     -0.0173 |       -0.1459 | -2.7154 | -0.0302 | -0.3349 | 0.4796 |         49 |
| exit_rate            | resid     | False     |       -0.0012 | -0.1009 |     -0.0283 |       -0.0295 | -0.698  | -0.009  | -0.0748 | 0.5153 |         49 |
| dio                  | resid     | False     |       -0.0015 | -0.5084 |     -0.0918 |        0.0204 |  0.6354 | -0.0041 | -0.0975 | 0.5102 |         49 |
| d_days_adv           | raw       | True      |       -0.0032 | -0.6586 |     -0.1287 |       -0.0112 | -0.3041 | -0.0002 | -0.0025 | 0.4847 |         49 |
| days_adv             | raw       | True      |       -0.0128 | -0.8036 |     -0.2309 |        0.0813 |  2.0696 |  0.0003 |  0.0025 | 0.4796 |         49 |
| new_conviction       | raw       | True      |       -0.0091 | -0.8827 |     -0.2431 |        0.1245 |  1.9607 |  0.0143 |  0.1322 | 0.4796 |         49 |
| breadth_level        | raw       | True      |       -0.0154 | -1.0267 |     -0.2879 |        0.1372 |  2.0667 |  0.0203 |  0.1635 | 0.4949 |         49 |
| conviction_top       | raw       | True      |       -0.0174 | -1.2514 |     -0.3482 |        0.1563 |  2.325  |  0.0166 |  0.1327 | 0.4847 |         49 |
| pso                  | resid     | False     |       -0.01   | -1.5715 |     -0.3082 |       -0.0278 | -1.6666 | -0.0006 | -0.0092 | 0.4541 |         49 |
| dio_2q               | resid     | False     |       -0.0071 | -2.0585 |     -0.3894 |       -0.0227 | -0.957  | -0.0051 | -0.1165 | 0.4643 |         49 |

## conf_reveal (grupo flagged vs universo)
- excesso medio -0.0021/tri, t=-0.86, 49 trimestres, mediana 1419 nomes/tri

## Alvos de literatura

- **dbreadth**: CHS 2002: +6.38%/12m decile spread (~1.6%/q); replicated here at +1.65%/q
- **dbreadth_common**: CHS variant; common-filer lesson: delta over common filers only removes universe-churn noise
- **breadth_level**: CHS: LEVELS are weak; expected ~null after size
- **dio**: Chincarini et al.: no significant alpha (declared null)
- **pso**: Chincarini et al.: PSO carries no alpha (declared null)
- **days_adv**: BHL/Chincarini: raw VW FF3 alpha spread +1.44%/mo (t=9.67); Amihud-adjusted +0.89 - we replicated the point (+1.46) already
- **d_days_adv**: no direct published number; crowding freshness (E3 logic: capacity measures rot fast) implies short-horizon info
- **herf_holders**: Greenwood-Thesmar fragility direction: concentrated ownership -> fire-sale tail; sign ambiguous unconditionally
- **conviction_top**: ACP best ideas: +2.8-4.5%/yr, 6-factor alpha 25-36 bps/mo
- **new_conviction**: ACP + flow: conviction expressed by NEW/raised positions; fresher subset of best ideas
- **ti**: paper's contrarian edge lives INSIDE the disclosure window (our replica): honest-timing expectation ~0 or follow(+)
- **vi**: same as ti; volume version (composition-flow sensitive)
- **entry_rate**: CHS mechanism: new holders = optimists arriving; positive
- **exit_rate**: complete exits are the strongest negative statement a long-only book can make (the only 'short' it has); NEGATIVE
- **net_entry**: entry minus exit; CHS direction, positive
- **dio_2q**: Sias (2004): institutional demand is persistent and predicts returns; 2-quarter cumulated demand, positive
- **late_minus_early_dio**: Christoffersen-Danesh-Musto: strategic LATE filers hide information; their demand minus early filers' demand should carry the informative component. Original construction.
- **conf_reveal**: Agarwal et al. 2013: confidential holdings outperform up to 12m (~5.9%/yr for restatement reveals). Low coverage - evaluated as flagged-group excess, not quintiles

## Pares com |corr|>0.6 (um fator, nao dois)

- dbreadth x dbreadth_common: +0.79
- dbreadth x net_entry: +0.79
- dbreadth_common x net_entry: +0.72
- breadth_level x conviction_top: +0.90
- breadth_level x new_conviction: +0.83
- breadth_level x conf_reveal: +0.61
- dio x vi: +0.72
- dio x dio_2q: +0.68
- conviction_top x new_conviction: +0.90
- ti x net_entry: +0.72