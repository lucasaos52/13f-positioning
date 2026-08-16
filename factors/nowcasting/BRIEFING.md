# Briefing — Nowcasting de posições institucionais 13F: o que foi feito, resultados, e onde queremos alternativas

Documento autocontido para revisão externa. Pedido ao revisor: **propor
alternativas e extensões viáveis dadas as restrições da seção 6** — desenhos de
sinal, fontes de dados públicas negligenciadas, formas de monetizar o que já
funciona, e críticas ao que fizemos.

## 1. Contexto e ativos disponíveis

- Base 13F própria, curada dos filings brutos da EDGAR: **58 milhões de
  posições, 16.327 filers, 2013Q2–2026Q1**, com data de arquivamento E
  timestamp de aceite **reais por versão** (originais + amendments, com
  semântica RESTATEMENT substitui / NEW HOLDINGS soma, validada em casos
  reais). Point-in-time estrito: `snapshot_as_of(trimestre, data_decisão)`
  devolve o que era público na data — nada de "D+45 fixo".
- Preços/volumes/shares outstanding do Yahoo Finance (grátis): ~3.900 tickers
  mapeados por nome de emissor, **só sobreviventes**, shares outstanding
  históricas de ~out/2015 em diante.
- Fatores Fama-French (Ken French, grátis) para atribuição.
- **Restrição dura: zero dados comerciais** (sem CRSP, sem Markit/DataLend,
  sem TAQ, sem CRSP Mutual Funds, sem Compustat).

## 2. O problema (plano de pesquisa que guiou o trabalho)

A literatura estabelece dois fatos que definem o desenho:

1. **Níveis de holdings são triviais** — persistência pura atinge NDCG ~0,889
   vs 0,913 do melhor modelo de ML (grafos temporais); features de domínio
   adicionam <1,2%;
2. **Variações são quase imprevisíveis** — o melhor proxy diário do mundo
   (variação de inventário emprestável, dado comercial da S&P Global;
   Barardehi-Da-Dixon-Wang 2024/25) explica **13,8%** da variância do ΔIO
   trimestral fora da amostra. Alternativas: trades reais ANcerno 5,8%,
   varejo BJZZ 0,34%, tape à la Campbell-Ramadorai-Schwartz 0,29%.

Logo: o alvo tem que ser a **variação** (ΔIO), o baseline obrigatório é
persistência, unidades sempre em **quantidade** (shares / razão IO =
shares detidas ÷ shares outstanding — valor mistura preço e fabrica R²).

## 3. O que foi implementado (6 experimentos) e os resultados

Protocolo comum: ~49 trimestres, avaliação PIT (alvo ΔIO só é conhecido em
T+75d; sinais usam exclusivamente filings com `filed_date ≤ data de decisão`).

| # | experimento | referência | resultado |
|---|---|---|---|
| X1 | R² do nível sob persistência pura | lit: ~0,99 | **0,964** ✓ |
| X2 | prever ΔIO com EMA dos ΔIO passados (Modelo 1 do teste aninhado) | não deve ajudar | **R² OOS negativo** (−0,44 a −1,65); hit rate 47-50% ✓ zero é difícil de bater |
| X3 | **âncora da borda irregular**: em D+15/30/45/60, usar o ΔIO já revelado pelos filers que arquivaram cedo para nowcastar o ΔIO final | inédito | IC 0,07 → 0,15 → 0,76 → 0,85; **R² winsorizado 0,5% → 3,4% → 51% → 63%** |
| X4 | E1: o ΔIO revelado cedo prevê RETORNO de d até T+75d? (PIT estrito) | Christoffersen-Danesh-Musto: nada | **nulo** — \|t\| ≤ 1,9 em 49 tri, sinais trocados entre horizontes ✓ |
| X5 | NDCG@10 de persistência/EMA em painel de 99 gestores (mega vs ativos) | 0,8891 / 0,8882 | 0,919-0,928 (mesma ordem; métrica @10 graded ≠ node-affinity deles). **Surpresa: painel ATIVO não é menos previsível no top-10** — o churn vive abaixo do top-10 |
| X6 | E3: Days-ADV (crowding) em tempo real com painel misto (filers frescos + defasados) vs versão defasada uniforme | uso defensivo | rank corr 0,96-0,999; **1,6% dos nomes migram >2 decis de crowding em D+45** |

**O resultado central (X3)**: a informação do filing season acumula numa curva
íngreme — quase nada até D+30 (cobertura ~12% do book agregado), explosão entre
D+30 e D+45 quando a massa dos filers entrega. **Em D+45 a âncora grátis
explica 51% do ΔIO final vs 13,8% do melhor proxy comercial.** (Comparação com
assimetria declarada: o proxy comercial é diário e disponível desde D+1; a
âncora só ganha valor quando filings chegam. O ponto é que na janela D+30→D+75
o dado público domina.)

## 4. O que foi deliberadamente cortado (e por quê)

| cortado | razão |
|---|---|
| Inventário emprestável (melhor método publicado) | exige S&P Global/Markit — comercial |
| FIT de Lou (fluxos de mutual funds × holdings defasadas) | exige TNA mensal por fundo (CRSP MF/Morningstar) |
| Nowcast exato de ETFs (criação/resgate × holdings diárias) | holdings diárias de ETF são públicas HOJE mas não há arquivo histórico grátis para backtest |
| Filtro de Kalman completo (Camada 2) | as observações de alta frequência (y1-y4) são as fontes pagas acima; só o y5 (âncora) é grátis — e foi promovido a experimento central |
| Return gap de Kacperczyk-Sialm-Zheng (teto econômico) | exige retorno reportado por fundo + mapa fundo↔filer (viria de N-PORT) |
| Order flow do tape | R² 0,29% em mercado moderno — morto por fatiamento algorítmico |

## 5. Conclusões

1. O painel replica os fatos estilizados da literatura (níveis triviais, deltas
   quase imprevisíveis, heurísticas imbatíveis no nível);
2. **Prever ΔIO ≠ prever retorno**: a âncora atinge IC 0,85 no ΔIO e ~zero em
   retorno (X4) — coerente com a literatura (instituições não temem copycats);
   o valor do nowcast é **risco e timing**, não seleção;
3. Usos monetizáveis identificados: (a) Days-ADV em tempo real como overlay de
   risco (a falha dos ETFs GURU/ALFA em 2015); (b) filtro de staleness para
   fatores de positioning (pesar menos observações que a âncora indica terem
   mudado); (c) calendário de ativação por cobertura observada (quando o
   trimestre fica "utilizável");
4. A composição do painel varia com a data de decisão (D+30 = bancos e
   quasi-indexers; D+50 = todo mundo incl. hedge funds estratégicos) — isso é
   informação, não bug.

## 6. Restrições para as alternativas propostas

- Só dados públicos/gratuitos (EDGAR ilimitado, Yahoo Finance com rate limit,
  Ken French, FINRA short interest quinzenal é aceitável, Nasdaq symbol
  directories, N-PORT público via EDGAR é aceitável mas é projeto de ingestão);
- Amostra máxima 2013Q2–2026Q1 (~50 trimestres); sobreviventes no painel de
  preços (sem deslistados);
- Infra existente: snapshots parquet por trimestre com metadados de versão,
  painel Yahoo cacheado, motor de quintis/eventos com NW, escada FF6.

## 7. Perguntas ao revisor

1. **Monetização da âncora**: dado que ΔIO-revelado-cedo não prevê retorno
   direto (X4), que outros usos/transformações da curva de acumulação
   valeriam teste? (ex.: surpresa do late-filer vs early-filer; dispersão
   entre filers revelados como proxy de discordância; velocidade de revelação
   como sinal de urgência?)
2. **Camada 1 sem dados pagos**: existe alguma fonte pública que substitua
   parcialmente fluxos de mutual funds ou lendable? (N-PORT tem TNA e até
   securities lending por fundo — vale o projeto de ingestão?)
3. **O Kalman vale a pena** só com y5 + short interest quinzenal da FINRA como
   segunda observação? Ou a âncora sozinha já extrai ~tudo?
4. **X5**: alguma explicação alternativa para o painel ativo NÃO ser menos
   previsível que o mega no NDCG@10? Métrica melhor para "previsibilidade do
   churn abaixo do top-10"?
5. **E4 (staleness filter)**: melhor desenho para acoplar a âncora aos fatores
   de positioning — reponderar por cobertura? por variância condicional da
   posição? descartar nomes com |Δrevelado| alto?
6. Crítica livre: onde o desenho acima está errado ou enganando a si mesmo?
