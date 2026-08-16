# Drift-fluxo-rotacao - resultados

## Cadeia aninhada (IC medio | spread EW/tri, t NW)
- dW bruto (sujo): IC +0.0141 | spread +0.0091 t=+2.30
- D (sem drift/fluxo): IC +0.0033 | spread +0.0021 t=+0.53
- D_perp B1 (so aposta de nome): IC +0.0042 | spread +0.0009 t=+0.21
- D_perp B2 (robustez): IC -0.0041 | spread -0.0039 t=-0.72
- D_perp + desconto GLS: IC +0.0049 | spread +0.0016 t=+0.42

## Placebo de drift (controle positivo)
- IC do drift puro: +0.0180 | spread +0.0133 t=+2.37
- corr(drift, momento 12-1): +0.40 (deve ser ALTA - drift e momento disfarcado)

## Corrida Fama-MacBeth (so D_perp deve sobreviver)
- b_raw: +0.01613 t=+2.35
- b_mid: -0.00687 t=-0.85
- b_perp: +0.00021 t=+0.03

## Atribuicao de variancia (medianas, sequencial)
- fatia drift+fluxo em dW bruto: 21%
- fatia rotacao de fator em D: 2%
- (aposta da nota: drift e a maior fatia - a literatura de dIO mede drift sem saber)