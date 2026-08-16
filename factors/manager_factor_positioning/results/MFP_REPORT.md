# manager_factor_positioning - resultados

- 50 trimestres, 5827 gestores distintos, K=6

## Validacao (antes de alpha)

- 2014-09-30 top-decile momentum EW: E[mom] = +1.63 (esperado ~ +1.5 a +2.0)
- 2014-09-30 small-cap decile EW: E[size] = +4.70 (esperado ~ +1.5 a +2.0)
- 2019-12-31 top-decile momentum EW: E[mom] = +2.95 (esperado ~ +1.5 a +2.0)
- 2019-12-31 small-cap decile EW: E[size] = +4.40 (esperado ~ +1.5 a +2.0)
- 2025-12-31 top-decile momentum EW: E[mom] = +1.99 (esperado ~ +1.5 a +2.0)
- 2025-12-31 small-cap decile EW: E[size] = +3.46 (esperado ~ +1.5 a +2.0)
- persistencia P_mom real AR1 = +0.59 vs placebo (shuffle intra-size) AR1 = -0.16 (placebo deve colapsar)

## E5 dashboard (media e ultimo trimestre, AUM-weighted)

| factor   |   P_aum |   dispersion |   breadth_pos |   hhi_pos |   P_aum_last |
|:---------|--------:|-------------:|--------------:|----------:|-------------:|
| beta     |   0.321 |        0.246 |         0.298 |     0.072 |        0.007 |
| liq      |   1.308 |        0.281 |         0.88  |     0.082 |        0.09  |
| lowvol   |   1.683 |        0.167 |         0.859 |     0.08  |        0.041 |
| mom      |   0.337 |        0.227 |         0.376 |     0.106 |       -0.026 |
| size     |   0.963 |        0.406 |         0.786 |     0.068 |       -0.018 |
| strev    |   0.06  |        0.156 |         0.25  |     0.127 |        0.001 |

## E2/E3 - decomposicao e testes de painel

Desvio-padrao temporal de cada componente (quem move a exposicao agregada):
| factor   |   drift_price |   drift_char |   rot_agg |
|:---------|--------------:|-------------:|----------:|
| beta     |        0.0328 |       0.5216 |    0.0073 |
| liq      |        0.0061 |       0.3211 |    0.0035 |
| lowvol   |        0.0096 |       1.2143 |    0.0039 |
| mom      |        0.0192 |       0.5883 |    0.0054 |
| size     |        0.0102 |       0.2535 |    0.0082 |
| strev    |        0.0112 |       1.5978 |    0.0058 |

- H1 AR1 da posicao agregada: beta +0.37, liq +0.82, lowvol +0.51, mom +0.59, size +0.89, strev -0.47
- H2 AR1 da rotacao ativa: beta +0.11, liq +0.08, lowvol -0.12, mom +0.09, size +0.15, strev -0.06

- H3 (pressure -> retorno do fator t+1, painel K x T, SE cluster/tri): b = -0.02394 (t = -1.05, n = 294)
- H4 (crowding sozinho): b = -0.01007 (t = -1.56, n = 246) - esperado ~0
- H5 (choque adverso x crowding): b_inter = -0.00630 (t = -0.42, n = 246) - esperado NEGATIVO

## E4 - mismatch de rebalanceamento (momentum)

- MECANISMO: IC(mismatch_t, dIO_t+1) = -0.0132 (t = -1.79, 45 tri) - pre-registro: NEGATIVO (owners vendem o que saiu do estilo)
- RETORNO: spread Q5-Q1 +0.0007/tri (t = +0.10), IC +0.0101, 46 tri - pre-registro: NEGATIVO