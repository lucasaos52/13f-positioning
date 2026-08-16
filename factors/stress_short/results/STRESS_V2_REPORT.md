# stress_short v2 - ablacao do trigger de correlacao + sensibilidade de limiares

A = z(-DD)+z(PainBreadth) [v1] | B = A + z_t(CorrShock) [v2] | C = z_t(CorrShock) puro. Corte headline = top 2% do dia (quantil, nao valor fixo). Grade completa reportada sem selecao.

## A - v1 (DD+PainBreadth) (1692 eventos, 22 tri)
- +3d: tese -0.0000 (t=-0.52) | placebo -0.0002 | **delta -0.0002 (t=-0.33)**
- +5d: tese -0.0007 (t=-0.78) | placebo +0.0000 | **delta -0.0012 (t=-1.03)**
- +10d: tese -0.0013 (t=-0.96) | placebo -0.0005 | **delta -0.0019 (t=-0.90)**

## B - v2 (+ CorrShock) (2216 eventos, 22 tri)
- +3d: tese -0.0005 (t=-1.70) | placebo -0.0003 | **delta -0.0005 (t=-1.09)**
- +5d: tese -0.0007 (t=-1.27) | placebo +0.0000 | **delta -0.0006 (t=-2.01)**
- +10d: tese -0.0005 (t=-0.84) | placebo -0.0001 | **delta -0.0010 (t=-1.01)**

## C - CorrShock puro (3577 eventos, 22 tri)
- +3d: tese -0.0006 (t=-1.31) | placebo -0.0008 | **delta +0.0005 (t=+1.89)**
- +5d: tese -0.0010 (t=-1.60) | placebo -0.0012 | **delta +0.0005 (t=+1.42)**
- +10d: tese -0.0006 (t=-0.80) | placebo -0.0015 | **delta +0.0009 (t=+1.27)**

## Grade de sensibilidade (variante B, delta tese-placebo)

- corte p97 (2216 ev): +3d -0.0005 (t=-1.09) | +5d -0.0006 (t=-2.01) | +10d -0.0010 (t=-1.01)
- corte p98 (2216 ev): +3d -0.0005 (t=-1.09) | +5d -0.0006 (t=-2.01) | +10d -0.0010 (t=-1.01)
- corte p99 (1018 ev): +3d -0.0001 (t=-0.12) | +5d -0.0005 (t=-0.66) | +10d -0.0004 (t=-0.23)
## Veredito da ablacao (22 tri)

A LAPIDACAO NAO MELHOROU - e o resultado e informativo em tres pontos:

1. CorrShock NAO adiciona: B (+correlacao) da delta -0.06%/5d (t=-2.01),
   MENOR em magnitude que o v1 original de corte fixo (-0.15%, t=-2.16).
   E o C (correlacao pura) INVERTEU no full (delta +0.05%, t=+1.89) - a
   promessa do smoke (t=-4.6 em 10 tri recentes) era miragem de amostra
   pequena, mais uma vez.
2. O corte por QUANTIL piorou tudo: a propria variante A (mesmas features
   do v1) cai de t=-2.16 para t=-1.03 quando o corte vira "top 2% do dia".
   Licao economica real: stress e um estado ABSOLUTO, nao relativo - em
   mercado calmo o "2% pior" nao esta estressado, e o trigger dispara em
   falso. O 2.0 fixo pre-registrado era a especificacao certa pelo motivo
   certo.
3. A grade de sensibilidade responde "por que 5?": a superficie e plana a
   pior em volta da especificacao original (p99 mata eventos sem ganhar
   t; +3d/+10d nao superam +5d). Nenhuma celula escondida e melhor.

ESPECIFICACAO FINAL: a do v1 (Stress absoluto > 2.0, DD+PainBreadth,
hold 5d) - agora com a ablacao que PROVA que cada alternativa razoavel e
igual ou pior, que e exatamente o que uma defesa exige de um parametro.
