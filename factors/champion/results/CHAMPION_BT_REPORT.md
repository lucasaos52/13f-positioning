# Champion no backtester de producao (factors/)

| modo | ret a.a. | vol | Sharpe | maxDD | hit |
|---|---|---|---|---|---|
| LS | +0.86% | 5.84% | **0.15** | -25.44% | 50.8% |
| LO | -1.23% | 6.35% | **-0.19** | -34.34% | 50.1% |

Convencoes: rebal mensal com drift, fee 5bps por lado, borrow 50bps a.a. acruado diario no short, cash leg em T-bill (LS), excesso vs S&P (LO), vol-weighted como o multifactor. Sinal trimestral em step function a partir da data de decisao (PIT).