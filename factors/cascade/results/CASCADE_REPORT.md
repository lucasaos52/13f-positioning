# cascade - choque single-name -> resgate -> venda dos inocentes

## Estagio A - mecanismo (SE_t -> fluxo_t+1)

- slope pooled: -0.9564 (19297 obs gestor-tri)
- slope por tri: media -2.8006 (t=-1.47, 30 tri) - pre-registro: NEGATIVO (dor -> resgate)

## Estagio B - preco nos inocentes (spread Q4-Q0, esperado POSITIVO: quem tem mais pressao esperada de venda rende menos)

- **raw**: -0.0032/tri (t=-0.23, 10 tri)
- **resid size/ADV**: -0.0085/tri (t=-0.51, 10 tri)
- **placebo (SE permutado)**: +0.0026/tri (t=+0.27, 10 tri)
## Veredito (30 tri de mecanismo, 10 de preco)

PAROU NO ESTAGIO A, como a disciplina mecanismo-primeiro manda: o elo do
meio (dor single-name -> resgate no tri seguinte) tem a direcao certa mas
nao passa da barra (slope medio -2.80, t=-1.47). Sem o elo do meio, o
teste de preco nao significa nada - e de fato deu nulo (t=-0.23/-0.51,
placebo limpo).

Leitura: resgate responde a PERFORMANCE AGREGADA do fundo (que o fluxo
implicito ja captura contemporaneamente, t=13.8) e nao ao crash saliente
de UMA posicao com defasagem trimestral. A sensibilidade fluxo-a-acao-
individual documentada (Di Maggio et al.) vive em dados de fluxo diarios/
mensais de mutual funds - a granularidade trimestral do 13F e grossa
demais para o canal. Nao e "a tese e falsa"; e "o relogio 13F nao a ve".
