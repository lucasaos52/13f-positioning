# wbreadth - breadth ponderado por sigmoide de performance (4 tri, book congelado, excesso vs mercado)

peso_m = sigmoid(z(perf4)); media 3071 gestores com score/tri. Pre-registro (historico 0-de-3 da familia performance-weight): deltas <= 0.

## Sinais (headline: nivel resid, delta raw)

- **breadth_level**: +0.0187/tri (t=+1.39), Sharpe +0.35, IC +0.0233, 48 tri
- **wb_level**: +0.0186/tri (t=+1.32), Sharpe +0.34, IC +0.0247, 48 tri
- **ub_level**: +0.0184/tri (t=+1.32), Sharpe +0.34, IC +0.0242, 48 tri
- **dbreadth**: +0.0017/tri (t=+0.26), Sharpe +0.05, IC +0.0013, 48 tri
- **wdb**: +0.0136/tri (t=+1.14), Sharpe +0.31, IC -0.0013, 48 tri
- **udb**: +0.0127/tri (t=+1.08), Sharpe +0.28, IC -0.0019, 48 tri

## Deltas pareados (decomposicao)

- **efeito SIGMOIDE no nivel (wb vs uniforme, mesmo eleitorado)**: dSpread +0.0002/tri (t=+0.19), dIC +0.0004 (t=+0.48), 48 tri
- **efeito SIGMOIDE na variacao (wdb vs udb)**: dSpread +0.0010/tri (t=+0.86), dIC +0.0005 (t=+0.77), 48 tri
- **efeito ELEITORADO no nivel (uniforme-com-score vs censo)**: dSpread -0.0003/tri (t=-0.15), dIC +0.0009 (t=+0.60), 48 tri
- **efeito ELEITORADO na variacao**: dSpread +0.0110/tri (t=+0.73), dIC -0.0031 (t=-0.18), 48 tri