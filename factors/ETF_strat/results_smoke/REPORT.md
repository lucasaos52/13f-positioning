# ETF positioning — resultado point-in-time

## Conclusão executiva

Foram implementadas as cinco hipóteses do memo com atualização gestor a gestor na data real do filing. **Nenhuma estratégia foi aprovada como alpha robusto.** As duas pistas remanescentes são `double_down_specific` (baixo turnover, mas instável entre pré/pós-2022) e `fragility_reversal` (IC positivo em 21/63 dias, mas insuficiente para pagar custos). Elas são sugestivas, não aprovadas. O universo negociável usa somente ETFs de ações com CUSIP/ticker verificados e preços históricos pinados.

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

Eventos materializados: 357 datas de filing e 533 datas totais após incluir gatilhos diários de fragilidade, em 8 trimestres. Cobertura mediana de retorno no drift: 63.7% do valor anterior no universo bruto e 70.0% entre gestores usados nos sinais de churn.

O cutoff de cobertura por gestor é 50%. A sensibilidade em `data/manager_coverage_sensitivity.csv` mostra por que 80% não foi adotado: o cross-section mediano cai para cerca de 69 gestores, abaixo do mínimo de 100 releases; 50% preserva mediana próxima de 1,8 mil. A cobertura imperfeita continua sendo uma limitação, não uma variável escondida.

## Hipóteses primárias — backtest LS

| strategy             |   ann_return |   ann_vol |   sharpe |   max_drawdown |   ann_turnover |
|:---------------------|-------------:|----------:|---------:|---------------:|---------------:|
| sticky_quality       |      -0.0846 |    0.0337 |  -2.5069 |        -0.1735 |        29.3115 |
| double_down_specific |       0.1046 |    0.1129 |   0.9271 |        -0.0856 |        13.9314 |
| abnormal_adoption    |      -0.0755 |    0.0831 |  -0.9078 |        -0.2032 |        30.5419 |
| ccp                  |      -0.0184 |    0.0581 |  -0.3162 |        -0.1504 |         4.8291 |
| fragility_stress     |      -0.0947 |    0.0329 |  -2.881  |        -0.1891 |        27.1416 |
| fragility_reversal   |      -0.0293 |    0.0834 |  -0.3512 |        -0.1454 |        26.7224 |

## Decisão e estabilidade

| strategy             |   gross_ann_return |   net_ann_return_10bps |   sharpe |   mean_ic |   ic_t_nw |   pre_2022 |   post_2021 | verdict                 |
|:---------------------|-------------------:|-----------------------:|---------:|----------:|----------:|-----------:|------------:|:------------------------|
| sticky_quality       |            -0.0293 |                -0.0846 |  -2.5069 |   -0.0062 |   -1.2327 |        nan |         nan | reprovado               |
| double_down_specific |             0.1359 |                 0.1046 |   0.9271 |    0.0899 |    4.9533 |        nan |         nan | sugestivo; não aprovado |
| abnormal_adoption    |            -0.0172 |                -0.0755 |  -0.9078 |   -0.0033 |   -0.3015 |        nan |         nan | reprovado               |
| ccp                  |            -0.0088 |                -0.0184 |  -0.3162 |    0.0261 |    3.7935 |        nan |         nan | reprovado               |
| fragility_stress     |            -0.0441 |                -0.0947 |  -2.881  |   -0.0034 |   -0.2225 |        nan |         nan | reprovado               |
| fragility_reversal   |             0.024  |                -0.0293 |  -0.3512 |   -0.0114 |   -1.2308 |        nan |         nan | reprovado               |

## IC de 21 pregões

| signal_name          |   horizon_days |   n_events |   median_names |   mean_ic |   ic_t_nw |
|:---------------------|---------------:|-----------:|---------------:|----------:|----------:|
| abnormal_adoption    |             21 |        311 |           1921 |   -0.0033 |   -0.3015 |
| ccp                  |             21 |        357 |           1978 |    0.0261 |    3.7935 |
| double_down_specific |             21 |        357 |            791 |    0.0899 |    4.9533 |
| fragility_reversal   |             21 |        509 |           1908 |   -0.0114 |   -1.2308 |
| fragility_stress     |             21 |         59 |           1818 |   -0.0034 |   -0.2225 |
| sticky_quality       |             21 |        357 |           1978 |   -0.0062 |   -1.2327 |

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

Config fingerprint: `e359ec1481c6`.