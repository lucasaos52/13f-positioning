# Resultado empirico: demanda institucional por ETF

Todos os sinais entram somente em period_end + 70 dias. O teste e uma adaptacao 13F:
mudanca nas acoes de ETF divulgadas por instituicoes nao e criacao/resgate no mercado primario.
A ausencia de shares outstanding historico tambem impede chamar a medida de delta de ownership.

Custos: 10 bps one-way; o spread liquido desconta entrada e saida das duas pernas.

|   horizon |   n_events |   n_names_median |   ic_mean |   ic_t_nw |   spread_gross_mean |   spread_net_mean |   spread_net_t_nw |   spread_net_sharpe_ann |   positive_share | signal_name         | sample   |
|----------:|-----------:|-----------------:|----------:|----------:|--------------------:|------------------:|------------------:|------------------------:|-----------------:|:--------------------|:---------|
|        21 |         51 |               40 |    0.0264 |    1.0183 |              0.0026 |           -0.0014 |           -0.8837 |                 -0.4134 |           0.451  | raw_reversal        | full     |
|        63 |         50 |               40 |    0.0385 |    1.488  |              0.0049 |            0.0009 |            0.2189 |                  0.0613 |           0.48   | raw_reversal        | full     |
|        21 |         50 |               40 |    0.0179 |    0.6762 |              0.0028 |           -0.0012 |           -0.8528 |                 -0.3814 |           0.4    | quality_reversal    | full     |
|        63 |         49 |               40 |    0.04   |    1.4528 |              0.0062 |            0.0022 |            0.5614 |                  0.149  |           0.551  | quality_reversal    | full     |
|        21 |         50 |               40 |   -0.0122 |   -0.5306 |              0.0009 |           -0.0031 |           -2.244  |                 -1.0826 |           0.38   | specialist_reversal | full     |
|        63 |         49 |               40 |   -0.0136 |   -0.7466 |             -0.001  |           -0.005  |           -1.5299 |                 -0.4239 |           0.3878 | specialist_reversal | full     |
|        21 |         47 |               40 |    0.0105 |    0.3973 |              0.0014 |           -0.0026 |           -1.5697 |                 -0.7347 |           0.383  | run_prone_reversal  | full     |
|        63 |         46 |               40 |    0.009  |    0.3417 |             -0.0002 |           -0.0042 |           -1.0445 |                 -0.3056 |           0.4565 | run_prone_reversal  | full     |

O arquivo summary.csv contem 5/21/63/126 dias e cortes pre-2022/post-2021.