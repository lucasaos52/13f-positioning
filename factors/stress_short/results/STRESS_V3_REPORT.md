# stress_short v3 - variante D (pegada de liquidacao: PCShare x Alignment)

D = z_t(lambda1-share x |cos(v1, vetor dolar/ADV)|) > 2.0 absoluto, grade de 5d; V1FIX = spec original na MESMA grade/amostra/placebo.

## V1FIX - spec original (baseline) (2657 eventos, 22 tri)
- +3d: tese +0.0000 (t=+0.83) | placebo -0.0003 | **delta +0.0008 (t=+1.04)**
- +5d: tese +0.0001 (t=+0.64) | placebo -0.0005 | **delta +0.0009 (t=+1.11)**
- +10d: tese +0.0000 (t=-0.12) | placebo -0.0014 | **delta +0.0008 (t=+0.51)**

## D - pegada de liquidacao (6277 eventos, 22 tri)
- +3d: tese +0.0004 (t=+0.73) | placebo +0.0001 | **delta +0.0001 (t=+0.48)**
- +5d: tese +0.0005 (t=+0.43) | placebo +0.0003 | **delta +0.0001 (t=+0.34)**
- +10d: tese +0.0022 (t=+0.88) | placebo +0.0023 | **delta +0.0001 (t=+0.08)**

## Veredito (22 tri)

1. VARIANTE D MORTA: delta +0.0001 em todos os horizontes (t 0.1-0.5),
   6.277 eventos - o gatilho de "pegada de liquidacao" dispara demais e
   nao carrega nada. Com isso a FAMILIA CORRELACAO FECHA COMPLETA:
   nivel (CorrShock, v2) -> nao adiciona; forma (PCShare x Alignment,
   v3) -> nada. A spec v1 (DD + PainBreadth, corte absoluto 2.0) fica
   blindada em definitivo - drawdown e amplitude da dor ja carregam toda
   a informacao explotavel do estado do book.
2. SUBPRODUTO IMPORTANTE - o efeito v1 e RAPIDO: o proprio V1FIX na
   grade de 5d perde o efeito INTEIRO (delta vira +0.09%, t=+1.1, vs
   -0.15% t=-2.16 na versao diaria). Entrar com ate 4 pregoes de atraso
   destroi o edge - consistente com fluxo que comeca na deteccao. A
   implicacao de implementacao e dura e util: o overlay stress_short so
   funciona operado NO DIA da deteccao, sem batch.
