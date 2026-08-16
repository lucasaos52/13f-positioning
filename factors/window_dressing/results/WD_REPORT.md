# window_dressing - oferta previsivel na foto de fim de tri

Universo: gestores ativos (AUM < mediana + churn >= 10%/tri) com propensao WD aprendida em 8 tri estritamente passados. Teste DENTRO dos losers (mata o confound de momentum): tercil alto vs baixo de WDPressure.

- 44 trimestres | media 807 gestores WD-elegiveis, 653 losers/tri

- **P1 pressao (ds -> quarter-end)**: +0.0059 (t=+1.58) - esperado NEGATIVO
- **P2 reversao (quarter-end -> +7td)**: -0.0052 (t=-1.94) - esperado POSITIVO
- **P3a placebo pressao (WD permutado)**: +0.0036 (t=+1.12) - esperado ~0
- **P3b placebo reversao**: -0.0061 (t=-2.68) - esperado ~0
- **P4 d_press**: Q4 +0.0037 (11 anos) vs Q1-Q3 +0.0067 (t=+1.99)
- **P4 d_rev**: Q4 -0.0191 (11 anos) vs Q1-Q3 -0.0005 (t=-0.14)
## Veredito (44 fins de trimestre)

WINDOW DRESSING (versao do doc) REJEITADO - os DOIS sinais pre-registrados
sairam errados: pressao +0.59% (t=+1.58, esperado negativo) e reversao
-0.52% (t=-1.94, esperado positivo). E o placebo de permutacao acompanha a
tese (reversao -0.61%, t=-2.68): o que quer que exista, vive na ESTRUTURA
ownership/ADV, nao na propensao WD do gestor - gestor "dumpador de loser"
nao gera oferta detectavel antes da foto.

O QUE SOBROU NOS DADOS (anomalia residual, geradora de hipotese):
um efeito 100% de FIM DE ANO - a reversao pos-foto e -1.91% em Q4 (11
anos) vs -0.05% em Q1-Q3. Losers muito detidos por gestores ativos pequenos
sobem levemente na ultima quinzena de dezembro e DEVOLVEM forte na primeira
semana de janeiro, relativo a losers pouco detidos. Duas historias
observacionalmente equivalentes neste desenho:
  (a) portfolio pumping / leaning for the tape (Carhart-Kaniel-Musto-Reed
      2002): marcam os proprios nomes pra cima na foto do ano;
  (b) January bounce classico no TERCIL BAIXO: losers de varejo/tax-loss
      (pouca instituicao) quicam em janeiro, e o tercil alto so nao quica.
Separar (a) de (b) exige decompor hi e lo contra a mediana - anotado como
extensao de meio dia SE a anomalia merecer perseguicao; com 11 observacoes
anuais, por ora e nota de rodape, nao sinal.
