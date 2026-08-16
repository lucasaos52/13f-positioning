# ETF positioning — resultado point-in-time

## Conclusão executiva

Foram implementadas as cinco hipóteses do memo com atualização gestor a gestor na data real do filing. **Nenhuma estratégia foi aprovada como alpha robusto.** A melhor hipótese primária no período cheio foi `ccp` (Sharpe líquido 0.71), mas falhou no gate de estabilidade. A decomposição de universo, baseline causal e fatores de mercado está em `results/candidate_diagnostics/REPORT.md`. O universo negociável usa somente ETFs de ações com CUSIP/ticker verificados e preços históricos pinados.

## Universo

- candidatos marcados como `fund` na 13F: 16,853;
- ETFs de ações verificados no universo primário: 2,208;
- cobertura histórica em valor da triagem `fund`: 71.0%;
- candidatos sem verificação permanecem em quarentena; `fund` não é sinônimo de ETF;
- identidade do ETF é estática, mas elegibilidade de preço/liquidez é calculada apenas com dados disponíveis no evento.

Essa é uma escolha deliberada de precisão sobre recall. Ampliar por regex misturaria CEFs, BDCs e ações comuns e contaminaria adoção/consenso. A sensibilidade completa está em `data/universe_candidate_audit.csv`.

## Relógio e construção

- restatements substituem o livro por CIK; `NEW HOLDINGS` posterior é aditivo; CIKs irmãos só são somados depois;
- como o parquet preserva data, não hora, o livro selecionado do gestor é liberado conservadoramente na última data de filing selecionada;
- `Trade` e churn usam pesos driftados por total return; posições sem ticker recebem SPY apenas no denominador de drift;
- entrada ocorre no primeiro pregão após o filing e o motor compartilhado ainda aplica `weights.shift(1)` ao P&L;
- custos principais: 10 bps one-way, com escada 0/5/10/20 bps.

Eventos materializados: 1,990 datas de filing e 3,229 datas totais após incluir gatilhos diários de fragilidade, em 51 trimestres. Cobertura mediana de retorno no drift: 59.2% do valor anterior no universo bruto e 62.0% entre gestores usados nos sinais de churn.

O cutoff de cobertura por gestor é 50%. A sensibilidade em `data/manager_coverage_sensitivity.csv` mostra por que 80% não foi adotado: o cross-section mediano cai para cerca de 69 gestores, abaixo do mínimo de 100 releases; 50% preserva mediana próxima de 1,8 mil. A cobertura imperfeita continua sendo uma limitação, não uma variável escondida.

## Hipóteses primárias — backtest LS

| strategy             |   ann_return |   ann_vol |   sharpe |   max_drawdown |   ann_turnover |
|:---------------------|-------------:|----------:|---------:|---------------:|---------------:|
| sticky_quality       |      -0.0506 |    0.0348 |  -1.4545 |        -0.4916 |        23.499  |
| double_down_specific |      -0.0439 |    0.074  |  -0.593  |        -0.5321 |        11.1238 |
| abnormal_adoption    |      -0.1125 |    0.1089 |  -1.0329 |        -0.7997 |        34.5005 |
| ccp                  |       0.0596 |    0.0834 |   0.7144 |        -0.1313 |         4.3845 |
| fragility_stress     |      -0.0462 |    0.0355 |  -1.3019 |        -0.4572 |        22.0832 |
| fragility_reversal   |      -0.0215 |    0.0788 |  -0.2728 |        -0.2694 |        23.5433 |

## Decisão e estabilidade

| strategy             |   gross_ann_return |   net_ann_return_10bps |   sharpe |   mean_ic |   ic_t_nw |   pre_2022 |   pre_2022_sharpe |   post_2021 |   post_2021_sharpe | verdict                 |
|:---------------------|-------------------:|-----------------------:|---------:|----------:|----------:|-----------:|------------------:|------------:|-------------------:|:------------------------|
| sticky_quality       |            -0.0049 |                -0.0506 |  -1.4545 |   -0.0022 |   -0.8898 |    -0.0515 |           -1.5536 |     -0.0491 |            -1.3057 | reprovado               |
| double_down_specific |            -0.0224 |                -0.0439 |  -0.593  |    0.0052 |    0.6357 |    -0.0688 |           -0.9928 |      0.0022 |             0.0275 | reprovado               |
| abnormal_adoption    |            -0.049  |                -0.1125 |  -1.0329 |   -0.0145 |   -3.0558 |    -0.1377 |           -1.188  |     -0.0657 |            -0.691  | reprovado               |
| ccp                  |             0.0689 |                 0.0596 |   0.7144 |    0.0263 |    9.4637 |     0.0942 |            1.0679 |      0.0006 |             0.0076 | sugestivo; não aprovado |
| fragility_stress     |            -0.0031 |                -0.0462 |  -1.3019 |    0.006  |    0.6698 |    -0.0312 |           -0.8284 |     -0.0724 |            -2.3148 | reprovado               |
| fragility_reversal   |             0.0257 |                -0.0215 |  -0.2728 |   -0.0075 |   -2.0932 |    -0.0171 |           -0.2265 |     -0.0292 |            -0.3474 | reprovado               |

Gate: Sharpe líquido cheio ≥ 0.50, t(IC 21d) ≥ 1.96 e Sharpe líquido ≥ 0.25 tanto pré-2022 quanto pós-2021.

## IC de 21 pregões

| signal_name          |   horizon_days |   n_events |   median_names |   mean_ic |   ic_t_nw |
|:---------------------|---------------:|-----------:|---------------:|----------:|----------:|
| abnormal_adoption    |             21 |       1960 |           1033 |   -0.0145 |   -3.0558 |
| ccp                  |             21 |       1990 |           1075 |    0.0263 |    9.4637 |
| double_down_specific |             21 |       1990 |            471 |    0.0052 |    0.6357 |
| fragility_reversal   |             21 |       3199 |            933 |   -0.0075 |   -2.0932 |
| fragility_stress     |             21 |        331 |            933 |    0.006  |    0.6698 |
| sticky_quality       |             21 |       1990 |           1075 |   -0.0022 |   -0.8898 |

## Interpretação das cinco ideias

1. `sticky_quality`: demanda líquida em peso, ponderada por 1 menos o percentil do churn suavizado em quatro trimestres. `sticky_raw` e `sticky_specificity` são as ablações.
2. `double_down_specific`: compras por gestores sticky após underperformance residual do ETF. O primário exclui broad ETFs; `double_down_all` testa a restrição.
3. `abnormal_adoption`: mudança no residual de log-breadth após controlar ownership divulgado, momentum, vol, beta, ADV, preço, idade e estilo. `abnormal_level` e new-holder breadth são ablações.
4. `ccp`: conviction dentro do ETF sleeve × quality × persistência consecutiva truncada em quatro trimestres; consensus puro é a comparação.
5. Fragilidade nunca é tratada como alpha incondicional: `fragility_stress` protege contra holders de alto churn em stress de mercado e `fragility_reversal` compra fragilidade apenas após choque residual negativo.

## Limitações que permanecem

- o universo verificado privilegia grandes ETFs sobreviventes e cobre poucos produtos temáticos;
- 13F mostra holdings long trimestrais, não intenção, short, criação/resgate primário nem AUM econômico total do gestor;
- timestamps intradiários foram perdidos no parquet e por isso a implementação atrasa, mas nunca antecipa, emendas;
- eventos de filing próximos se sobrepõem; ICs usam Newey–West, mas devem ser lidos junto com estabilidade temporal e turnover;
- nenhum metasignal é promovido antes de componentes individuais mostrarem robustez fora da amostra.

Config fingerprint: `014ce7874464`.