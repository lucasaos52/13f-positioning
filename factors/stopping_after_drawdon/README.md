# stopping_after_drawdon — onde está a implementação

Esta pasta contém apenas o memo de pesquisa
(`13F_stopout_forced_liquidation_reversal.md/.pdf`).

**A implementação está em [`factors/stopout/`](../stopout/):**

- `run_stopout.py` — MVP do memo (§5–9, 33): book sintético diário com
  pesos driftados, drawdown residual, PainBreadth, Stress, SOF, gate H1,
  eventos de exaustão H5 com placebo pareado, PnL tático líquido.
  ETFs removidos dos books com a lista auditada de
  `factors/ETF_strat/data/etf_universe_flags.csv`.
- `results/STOPOUT_REPORT.md` — resultados e veredito.

## Veredito (resumo)

- **Gate H1** (stress sintético → venda forçada no filing seguinte):
  direção certa nos 3 eixos — taxa de forced-sale DOBRA (12.2% vs 6.7%) —
  mas t=1.62 com 19 trimestres de labels: não passa a barra.
- **H5** (rebound pós-exaustão vs placebo "mesmo crash sem dono
  stressed"): delta +0.25%, t=0.95 — nada.
- **PnL tático líquido**: Sharpe +0.12 — morto.

Conclusão: mesmo no relógio diário, com detector de exaustão e placebo
pareado, o desconto mecânico de fire-sale não se separa do bounce
genérico de crash — refina a conclusão permanente do projeto (distress
institucional = informação em todos os relógios mensuráveis). O stress
sintético como INSTRUMENTO (identificar o vendedor um trimestre antes do
filing) tem sinal real e fica anotado para re-teste com labels mais
frequentes (ex.: N-PORT mensal).
