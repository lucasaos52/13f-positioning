# general_plan - resultado do estudo

Fatores do plano_pesquisa_13F implementados sobre a base 13F curada, relogio event-driven por filed_date (D+30/45/60), universo endogeno de gestores, pipeline §4.1 identico para todos os fatores.

## Sumario (spread Q5-Q1 trimestral, EW)

|                  |   ew_spread_mean_q |   ew_spread_t_nw |   ew_spread_sharpe |   vw_spread_t_nw |   ic_mean |   monotonicity |   turnover_1s |   breakeven_bps |
|:-----------------|-------------------:|-----------------:|-------------------:|-----------------:|----------:|---------------:|--------------:|----------------:|
| ('dacwb', 30)    |            -0.0022 |          -0.4856 |            -0.151  |          -1.5167 |    0.0009 |           0.5  |        0.7441 |         -7.2459 |
| ('dacwb', 45)    |            -0.0044 |          -1.1493 |            -0.3541 |          -1.0448 |   -0.0008 |           0.5  |        0.7126 |        -15.2803 |
| ('dacwb', 60)    |            -0.0051 |          -1.0825 |            -0.3789 |          -1.6279 |   -0.009  |           0.25 |        0.71   |        -17.8266 |
| ('days_adv', 30) |             0.0075 |           0.4616 |             0.1765 |          -0.1799 |    0.0184 |           0.75 |        0.4107 |         45.7961 |
| ('days_adv', 45) |             0.0018 |           0.1731 |             0.0484 |           1.6768 |    0.0006 |           0.25 |        0.3215 |         14.2474 |
| ('days_adv', 60) |            -0.0042 |          -0.4224 |            -0.1581 |           1.8342 |   -0.0023 |           0.5  |        0.2947 |        -35.6738 |
| ('dio', 30)      |            -0.0022 |          -0.4366 |            -0.0914 |           1.0803 |   -0.0062 |           0.25 |        0.2638 |        -21.2486 |
| ('dio', 45)      |             0.002  |           0.4393 |             0.1265 |           0.06   |   -0.0003 |           0.25 |        0.7065 |          6.9292 |
| ('dio', 60)      |             0.001  |           0.2004 |             0.0647 |          -0.4542 |    0.0014 |           0.5  |        0.7758 |          3.3062 |
| ('dnuminst', 30) |            -0.0257 |          -2.0794 |            -0.7578 |          -0.5153 |   -0.0393 |           0.25 |        0.2187 |       -293.77   |
| ('dnuminst', 45) |            -0.007  |          -0.6862 |            -0.2322 |          -1.1216 |   -0.0071 |           0.5  |        0.6706 |        -26.0229 |
| ('dnuminst', 60) |             0.0038 |           0.6011 |             0.2252 |          -0.6844 |    0.0069 |           0.75 |        0.7681 |         12.3803 |
| ('pso', 30)      |             0.0186 |           1.8368 |             0.7334 |           0.1238 |    0.0306 |           0.75 |        0.4059 |        114.804  |
| ('pso', 45)      |             0.0083 |           1.7522 |             0.3449 |           1.3261 |    0.0144 |           0.5  |        0.2762 |         75.4377 |
| ('pso', 60)      |             0.0005 |           0.1175 |             0.0239 |           1.161  |    0.0063 |           0.75 |        0.2224 |          5.4738 |

## Falsificacao e diagnosticos

- perm_spread_actual: -0.00435569880494064
- perm_null_sd: 0.0030085173691547203
- perm_perm_pvalue: 0.16
- perm_n_events: 44
- lead_lead_spread_mean: -0.012984514706021372
- lead_lead_t: -4.1950760579814546
- lead_verdict: pass (t negativo = feedback trading: retornos causam o sinal SEGUINTE, Nofsinger-Sias 1999 - nao e lookahead, que exigiria t POSITIVO)
- half_first_half_mean: -0.0064459816735479595
- half_second_half_mean: -0.002265415936333326
- half_first_half_t: -1.4397076497358612
- half_second_half_t: -0.37825884710476954
- corr_dacwb_mom_avg: -0.05931525607686894
- corr_nodrift_mom_avg: 0.12657352264057006
- w_mkt_fallback_frac_avg: 0.8906202404682635

## Leitura final

- dACWB (fator principal do plano): NAO entrega no nosso universo - spread negativo e ns nos 3 lags. Reportado como esta; 4 dos 5 criterios de avaliacao nao dependem do fator funcionar.
- Days-ADV: direcao da literatura em D+30 EW (+0,75%/tri) e VW t=1,7-1,8 em D+45/60, mas ~1/6 da magnitude publicada (1,44%/MES, t=9,67, 1980-2021 com microcaps e deslistados). Suspeitos: universo sobrevivente sem microcaps (onde o efeito mora), amostra pos-publicacao (McLean-Pontiff), 40 obs.
- Nulos: dIO ~0 como previsto; dNumInst e PSO mostram |t|~1,8-2,1 em UMA celula de 15 - com 15 testes, ~1 celula dessas e esperada por acaso; nada passa Harvey-Liu-Zhu (t>3).
- Timing: days_adv decai D+30 -> D+60 (frescor da medida de capacidade importa - consistente com E3 do plano II); dacwb nao tem padrao de lag.
- Drift correction validada: corr com momentum -0,06 vs +0,13 sem correcao.


## Sorts fieis a literatura (diag_literature.py - sort CRU, sem neutralizacao, piso $1)

| fator | publicado | medido (50 tri, D+45) | veredito |
|---|---|---|---|
| dBreadth (Chen-Hong-Stein 2002) | ~1,6%/tri (6,38%/12m) | **+1,65%/tri, t(NW)=1,88, gradiente monotonico 3,2->4,8%** | **REPLICA em direcao E magnitude** |
| Days-ADV (BHL/Chincarini) | +4,3%/tri (1,44%/mes t=9,67) | -1,2%/tri EW ns; **-4,7%/tri VW t=-2,5** | sinal INVERTIDO na nossa era/universo |

Licoes:
1. A tabela principal (pipeline §4.1) NAO e comparavel com a literatura: a neutralizacao por tamanho
   remove a variacao que carrega o premio publicado (eles proprios: Amihud reduz 1,44 -> 0,89), e o
   piso de liquidez amputa o Q1 short (-0,90%/mes) que e 2/3 do spread deles.
2. dBreadth: o efeito Chen-Hong-Stein EXISTE na base - o pipeline neutralizado o matava porque a
   ortogonalizacao contra retorno do trimestre anterior remove o componente de feedback trading que
   e parte do proprio mecanismo.
3. Days-ADV invertido tem dois suspeitos com nome: (a) SURVIVORSHIP no Q1 - as small caps iliquidas
   pouco-crowded que morreram (e entregariam o -0,90) nao existem no painel Yahoo; as que sobraram
   rendem +4,9%/tri; (b) era pos-publicacao 2013-2026 vs amostra 1980-2021 (Brown-Howard-Lundblad
   documentam cauda esquerda pesada dos crowded - 2015/2022 estao na nossa janela, 1980-2012 nao).
   Mesma assinatura de todas as replicas deste projeto: direcao vive ou morre com os DESLISTADOS.


## Correcao final: alfas FF3 (diag_literature2.py) - Days-ADV REPLICA

Os numeros publicados sao ALFAS FF3 de quintis VW por MARKET CAP. O 'sinal invertido' anterior vinha de duas divergencias de scoring: retorno cru (nao alfa) e VW por valor institucional (nao mktcap). Refeito identico a literatura (fatores de Ken French, 150 meses):

| leg | publicado (1980-2021) | medido (2013-2026) |
|---|---|---|
| Q5-Q1 VW, alfa FF3 | **+1,44%/mes (t=9,67)** | **+1,46%/mes (t=1,18)** |
| Q1 VW (nao-crowded) | -0,90%/mes | -1,61%/mes |
| Q5 VW (crowded) | +0,54%/mes | -0,15%/mes |

Composicao valida a anatomia: Q5 = mktcap mediano $471M, ADV $0,7M/dia, 126 dias para liquidar; Q1 = $2,1bn, $10M/dia, 8,5 dias.

Leitura: o PONTO estimado do spread replica quase exatamente (+1,46 vs +1,44); a SIGNIFICANCIA nao (t=1,18 vs 9,67) - 12 anos vs 42, so sobreviventes, e a vol mensal do spread e grande. EW da ~zero. E o aviso de metodo que fica: o sinal do spread DEPENDE do esquema de ponderacao (inst-value VW inverte; mktcap VW replica) - detalhe que nenhum abstract menciona.
