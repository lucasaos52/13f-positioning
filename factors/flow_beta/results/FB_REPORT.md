# flow_beta - beta de funding comum x choque corrente

g_t = fluxo implicito medio ponderado por AUM (o choque de funding do dolar medio); beta_m estimado so no passado (>=8 obs); exposicao = sum valor x beta / ADV.

- 19 tri avaliados | betas medios/tri: 647 | g_t: media -0.017, min -0.143, max +0.024

- **F1 estado puro (FlowBeta sem choque)**: spread -0.0026/tri (t=-0.36), IC +0.0060 (t=+0.51) - esperado ~0
- **F2 TESE: FlowBeta x g_t**: spread +0.0090/tri (t=+0.77), IC +0.0204 (t=+1.02) - esperado POSITIVO
- **F3 placebo (beta permutado) x g_t**: spread +0.0028/tri (t=+0.21), IC +0.0093 (t=+0.47) - esperado ~0
- **delta pareado F2-F1**: +0.0116/tri (t=+0.88)
- **delta pareado F2-F3**: +0.0063/tri (t=+0.91)
## Veredito (19 tri avaliaveis)

F1 estado ~0 (t=-0.36): 13a confirmacao da lei "estado sem seta". F2
(interacao com o choque corrente) tem a direcao pre-registrada mas t=+0.77;
F3 placebo limpo. NAO promovido.

Limite ESTRUTURAL do desenho, nao do codigo: g_t e um escalar por
trimestre e episodios de choque comum grande sao raros na janela (min
-0.14 = COVID; 2-3 episodios relevantes). O teste se apoia em meia duzia
de trimestres informativos - underpowered por construcao ate existir outro
ciclo de funding. Registrado como nao-testavel-ainda, nao como falso.
