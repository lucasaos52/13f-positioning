# Relatorio de pesquisa — 13F x ETF positioning

## Veredito

O baseline 13F-only foi **reprovado como alpha de producao**. Ha IC positivo no periodo
inicial e no horizonte longo, mas o spread liquido nao e significativo e o efeito nao
sobrevive ao corte pos-2021. O resultado apoia a tese do blueprint de que ownership bruto
deve ser apenas controle; o mecanismo forte exige baskets historicos e/ou fluxo primario.

## Universo auditado

- 16,853 instrumentos receberam `fund` em ao menos um snapshot.
- 51 ETFs verificados apareceram na base; cobertura de valor: 54.7%.
- 51 produtos no painel, 2059 ETF-quarters de acoes.
- 7,693 gestores em 2026-03-31; mediana ETF intensity verificada 4.2%.
- A triagem `fund` teria mediana 29.0%: a diferenca mostra por que ela nao entra no sinal.
- `passive_manager` nao foi inferido; estilos sao comportamentais e variam por trimestre.

## Full sample — 10 bps one-way

| signal_name         |   horizon |   n_events |   n_names_median |   ic_mean |   ic_t_nw |   spread_net_mean |   spread_net_t_nw |   spread_net_sharpe_ann |   positive_share |
|:--------------------|----------:|-----------:|-----------------:|----------:|----------:|------------------:|------------------:|------------------------:|-----------------:|
| raw_reversal        |        21 |         51 |               40 |    0.0264 |    1.0183 |           -0.0014 |           -0.8837 |                 -0.4134 |           0.451  |
| raw_reversal        |        63 |         50 |               40 |    0.0385 |    1.488  |            0.0009 |            0.2189 |                  0.0613 |           0.48   |
| raw_reversal        |       126 |         49 |               40 |    0.06   |    1.9398 |            0.0063 |            1.0354 |                  0.2106 |           0.5918 |
| quality_reversal    |        21 |         50 |               40 |    0.0179 |    0.6762 |           -0.0012 |           -0.8528 |                 -0.3814 |           0.4    |
| quality_reversal    |        63 |         49 |               40 |    0.04   |    1.4528 |            0.0022 |            0.5614 |                  0.149  |           0.551  |
| quality_reversal    |       126 |         48 |               40 |    0.063  |    1.9906 |            0.0071 |            1.217  |                  0.2371 |           0.5833 |
| specialist_reversal |        21 |         50 |               40 |   -0.0122 |   -0.5306 |           -0.0031 |           -2.244  |                 -1.0826 |           0.38   |
| specialist_reversal |        63 |         49 |               40 |   -0.0136 |   -0.7466 |           -0.005  |           -1.5299 |                 -0.4239 |           0.3878 |
| specialist_reversal |       126 |         48 |               40 |   -0.0091 |   -0.3997 |            0.0001 |            0.0255 |                  0.0046 |           0.5    |
| run_prone_reversal  |        21 |         47 |               40 |    0.0105 |    0.3973 |           -0.0026 |           -1.5697 |                 -0.7347 |           0.383  |
| run_prone_reversal  |        63 |         46 |               40 |    0.009  |    0.3417 |           -0.0042 |           -1.0445 |                 -0.3056 |           0.4565 |
| run_prone_reversal  |       126 |         45 |               40 |    0.0424 |    1.3025 |           -0.0007 |           -0.1198 |                 -0.0245 |           0.5556 |

## Estabilidade do baseline bruto

| sample    |   horizon |   n_events |   ic_mean |   ic_t_nw |   spread_net_mean |   spread_net_t_nw |
|:----------|----------:|-----------:|----------:|----------:|------------------:|------------------:|
| full      |        63 |         50 |    0.0385 |    1.488  |            0.0009 |            0.2189 |
| full      |       126 |         49 |    0.06   |    1.9398 |            0.0063 |            1.0354 |
| pre_2022  |        63 |         34 |    0.0681 |    2.1454 |            0.0049 |            0.9063 |
| pre_2022  |       126 |         34 |    0.0903 |    2.2467 |            0.0095 |            1.1995 |
| post_2021 |        63 |         16 |   -0.0243 |   -0.6294 |           -0.0076 |           -1.4224 |
| post_2021 |       126 |         15 |   -0.0087 |   -0.229  |           -0.0008 |           -0.096  |

## Interpretacao

- O raw reversal em 126d tem IC medio proximo de 0,06, mas t do spread liquido proximo de 1.
- O quality tilt nao produz incremento estavel sobre o raw baseline.
- Direct-specialist e run-prone nao resgatam o sinal ETF-level.
- Resultado ETF-level nao testa ainda o principal uso de #8: ponderar a conviccao residual #5.
- D+70 e honesto/conservador, mas nao e o nowcast filing-by-filing recomendado para producao.

## O que falta para o teste principal

Baskets historicos, AUM/shares outstanding point-in-time e fluxo primario. Sem esses contratos,
#1–#4 nao podem ser apresentados como replicas da literatura. Consulte `docs/DATA_CONTRACTS.md`.