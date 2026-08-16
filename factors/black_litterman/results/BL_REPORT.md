# Black-Litterman implicito - views por otimizacao reversa

## Pre-teste da nota (rodado ANTES do backtest)
- corr(q_idio, vol idio) media: -0.10 (alto = tilt de vol por construcao -> ver variante vol-neutra)

## Banda MEGA (cadeia aninhada: IC | spread EW/tri, t)
- M1 peso ativo cru: IC +0.0746 | spread +0.0398 t=+1.76 (n=50)
- M2 Sigma w (1-fator): IC +0.0811 | spread +0.0419 t=+2.21 (n=50)
- M3 q_idio (exato): IC +0.0648 | spread +0.0365 t=+1.93 (n=50)
- M3v q_idio vol-neutro: IC +0.0618 | spread +0.0327 t=+1.93 (n=50)
- M3d risco diagonal (robustez): IC +0.0735 | spread +0.0345 t=+1.76 (n=50)
- M4 skill-weighted EB: IC +0.0323 | spread +0.0056 t=+0.57 (n=48)

## Banda MID (cadeia aninhada: IC | spread EW/tri, t)
- M1 peso ativo cru: IC +0.0499 | spread +0.0228 t=+2.15 (n=50)
- M2 Sigma w (1-fator): IC +0.0539 | spread +0.0339 t=+2.84 (n=50)
- M3 q_idio (exato): IC +0.0437 | spread +0.0296 t=+2.92 (n=50)
- M3v q_idio vol-neutro: IC +0.0417 | spread +0.0283 t=+2.75 (n=50)
- M3d risco diagonal (robustez): IC +0.0478 | spread +0.0297 t=+2.98 (n=50)
- M4 skill-weighted EB: IC +0.0181 | spread +0.0082 t=+0.96 (n=48)

## Banda FULL (cadeia aninhada: IC | spread EW/tri, t)
- M1 peso ativo cru: IC +0.0463 | spread +0.0231 t=+1.58 (n=50)
- M2 Sigma w (1-fator): IC +0.0514 | spread +0.0261 t=+2.11 (n=50)
- M3 q_idio (exato): IC +0.0425 | spread +0.0247 t=+2.35 (n=50)
- M3v q_idio vol-neutro: IC +0.0411 | spread +0.0228 t=+2.56 (n=50)
- M3d risco diagonal (robustez): IC +0.0463 | spread +0.0268 t=+2.52 (n=50)
- M4 skill-weighted EB: IC +0.0168 | spread +0.0012 t=+0.15 (n=48)
