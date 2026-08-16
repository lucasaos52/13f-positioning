# nowcasting - resultados vs literatura

## X1 Niveis vs variacoes (§2)
- R2 do NIVEL sob persistencia pura: media **0.9645** (literatura: ~0,99 - 'niveis sao triviais')
- desvio do nivel 0.1570 vs desvio do dIO 0.0524

## X2 Baselines aninhados no dIO (§6.2)
| model    |      r2 |      ic |    hit |
|:---------|--------:|--------:|-------:|
| ema_disc | -0.441  | -0.0146 | 0.498  |
| last_dio | -1.6537 | -0.0787 | 0.4772 |

Literatura: melhor proxy diario existente (lendable) = 13,8% OOS; heuristicas de nivel nao ajudam no delta; hit rate esperado 52-58%.

## X3 Borda irregular como informacao (ancora y5)
|                         |      r2 |   r2_wins |     ic |    hit |   coverage |
|:------------------------|--------:|----------:|-------:|-------:|-----------:|
| ('revealed', 15)        |  0.0045 |    0.0049 | 0.0676 | 0.5324 |     0.0289 |
| ('revealed', 30)        |  0.0469 |    0.0339 | 0.1481 | 0.5592 |     0.1192 |
| ('revealed', 45)        |  0.6017 |    0.5119 | 0.7579 | 0.8212 |     0.8473 |
| ('revealed', 60)        |  0.7484 |    0.6304 | 0.8452 | 0.8627 |     0.9439 |
| ('revealed_scaled', 15) | -0.1528 |   -0.0322 | 0.0676 | 0.5324 |     0.0289 |
| ('revealed_scaled', 30) | -0.952  |   -0.422  | 0.1481 | 0.5592 |     0.1192 |
| ('revealed_scaled', 45) |  0.443  |    0.285  | 0.7579 | 0.8212 |     0.8473 |
| ('revealed_scaled', 60) |  0.6671 |    0.4975 | 0.8452 | 0.8627 |     0.9439 |

R2 cresce com h porque a cobertura dos filers revelados cresce - a curva de acumulacao de informacao do filing season.

## X4 E1-lite: dIO revelado cedo preve retorno? (PIT)
|   h |    mean |    std |   size |       t |
|----:|--------:|-------:|-------:|--------:|
|  15 |  0.0049 | 0.0183 |     49 |  1.8638 |
|  30 | -0.0034 | 0.014  |     49 | -1.6786 |
|  45 |  0.0022 | 0.0207 |     49 |  0.7508 |
|  60 | -0.0005 | 0.0132 |     49 | -0.285  |

Christoffersen-Danesh-Musto preveem ~nada; um nulo aqui e resultado, nao fracasso.

## X5 NDCG@10 das heuristicas (replica §3.6)
|                       |   mean |   count |
|:----------------------|-------:|--------:|
| ('active', 'ema')     | 0.9244 |    4069 |
| ('active', 'persist') | 0.928  |    4166 |
| ('mega', 'ema')       | 0.9186 |    4558 |
| ('mega', 'persist')   | 0.9185 |    4642 |

Publicado: persistent 0,8891 | EMA 0,8882 | melhor ML 0,9127. Aterrissar perto de 0,89 valida o painel; o ganho do ML publicado e de 2,4 pontos - o argumento para NAO treinar grafos aqui.

## X6 E3: Days-ADV tempo real vs defasado
|   h |   rank_corr |   migr_2dec |
|----:|------------:|------------:|
|  15 |      0.9996 |      0.0002 |
|  45 |      0.9726 |      0.0159 |

migr_2dec = fracao dos nomes cujo rank de crowding muda mais de 2 decis quando medido em tempo real - o valor do nowcast como ferramenta de RISCO.
