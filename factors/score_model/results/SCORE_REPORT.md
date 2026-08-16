# score_model - E[r] unificado: classicos + posicionamento 13F

- 50 tri no painel, 38 tri avaliados OOS (apos 12 tri de warm-up de lambda/IC)

## Marginalidade conjunta (lambda medio full-sample, NW t)

A pergunta que a escada FF6 nao responde: o preditor carrega premio segurando TODOS os outros simultaneamente?

|          |   lambda_medio |    t_NW |   IC_medio |    t_IC |
|:---------|---------------:|--------:|-----------:|--------:|
| size     |         0.1049 |  4.4492 |     0.0286 |  2.3871 |
| mom      |        -0.0107 | -1.3765 |     0.0019 |  0.1209 |
| beta     |        -0.0061 | -0.6169 |     0.0264 |  1.4621 |
| lowvol   |        -0.0242 | -0.9393 |    -0.0022 | -0.0852 |
| strev    |        -0.0049 | -0.4136 |    -0.0015 | -0.0931 |
| liq      |         0.0751 |  4.3892 |     0.0144 |  1.0936 |
| new_conv |         0.0204 |  3.0396 |     0.0207 |  2.5368 |
| dbreadth |         0.0153 |  4.0068 |     0.0106 |  1.4564 |
| distress |         0.0004 |  0.0449 |     0.0131 |  0.8385 |
| pressure |         0.0097 |  1.7876 |    -0.0019 | -0.2082 |

## Corrida dos combinadores (OOS estrito, mesma amostra)

- **A Fama-MacBeth/Lewellen**: spread +0.0539/tri (t=+2.65), Sharpe +0.86, IC +0.0299
- **B IC-weighted (Grinold-Kahn)**: spread +0.0431/tri (t=+2.09), Sharpe +0.69, IC +0.0171
- **C rank-average new_conv+distress**: spread +0.0257/tri (t=+2.09), Sharpe +0.74, IC -0.0013
- delta A_fm vs B_ic: +0.0109/tri (t=+1.18)
- delta A_fm vs C_naive: +0.0282/tri (t=+1.96)
- delta B_ic vs C_naive: +0.0173/tri (t=+1.06)