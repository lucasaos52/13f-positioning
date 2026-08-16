# general_predictive_signals — 17 sinais de positioning, um protocolo

Busca sistemática de sinais preditivos sobre a base 13F curada (58M posições,
relógio por `filed_date`), com a regra de neutralização decidida **antes de
olhar qualquer retorno** e justificada sinal a sinal.

## A regra única: neutralizar ex-ante só quando é TEOREMA

**Teste do macaco**: o sinal correlacionaria com size/liquidez num mundo de
gestores jogando dardos (zero informação, books aleatórios value-weighted)?

- **SIM → a correlação é construção, não escolha** — carrega zero informação
  por matemática. Resíduo cross-section contra log(mktcap)+log(ADV) é a
  versão headline. Não há o que perder: essa parte um screen grátis entrega;
- **NÃO → a correlação é hipótese empírica** (canal causal ou confounder —
  indistinguível olhando o sinal). Cru é headline; estilo/momentum se julgam
  **ex-post** na escada de fatores, onde medir não destrói. Apagar ex-ante é
  irreversível e não-identificado: sinal morto não diz se era "momentum
  requentado" ou "canal amputado".

As duas versões (raw e resid) são computadas e avaliadas **para todos** — nos
não-teoremas as duas devem concordar (a concordância é diagnóstico); nos
teoremas a diferença mede a parte mecânica. O flag headline está fixado em
`signal_defs.py`, não é escolhido pelo backtest.

## O catálogo e os vereditos de teorema

| sinal | teorema? | por quê | alvo de literatura |
|---|---|---|---|
| dbreadth | não | Δ de razão: macaco dá ~0 pra toda ação | CHS 2002: ~1,6%/tri (replicado: +1,65%) |
| dbreadth_common | não | idem, filers comuns (lição do flip do VI) | CHS |
| breadth_level | **SIM** | books finitos value-weighted ⟹ P(deter) cresce com mktcap por construção | CHS: níveis fracos |
| dio | não | Δ de razão IO com SO contemporâneo | Chincarini: nulo declarado |
| pso | não | **macaco value-weighted dá IO% CONSTANTE** — a correlação empírica com size é preferência (Gompers-Metrick), comportamento, não aritmética → testa-se ex-post | Chincarini: nulo |
| days_adv | **SIM** | ADV no denominador ⟹ macaco dá const/velocidade = screen de iliquidez | BHL: α VW FF3 +1,44%/mês (ponto replicado: +1,46) |
| d_days_adv | **SIM** | herda o denominador | (sem número publicado; lógica E3) |
| herf_holders | **SIM** | HHI cai mecanicamente com n_holders, que cresce com size | Greenwood-Thesmar (fragilidade) |
| conviction_top | não | top-decil do PRÓPRIO book: todo book tem um top-decil, relativo a si mesmo | ACP best ideas: 25-36 bps/mês |
| new_conviction | não | idem, restrito a posições novas/aumentadas | ACP + fluxo |
| ti / vi | não | razões limitadas em ±1 dentro da ação | nossa réplica: ~0 no timing honesto |
| entry_rate | não | razão de contagem vs base anterior | CHS: otimistas chegando (+) |
| exit_rate | não | idem | saída total = o único "short" do long-only (−) |
| net_entry | não | diferença de duas razões simétricas | CHS (+) |
| dio_2q | não | soma de dois Δ split-safe | Sias 2004: demanda persistente (+) |
| late_minus_early_dio | não | diferença de agregados do MESMO trimestre — size cancela nos dois termos | Christoffersen: atraso é estratégico; original nosso |
| conf_reveal | não | flag binário de evento | Agarwal 2013: confidenciais superam ~12m |

## Protocolo de avaliação (idêntico pra todos)

- decisão em p+45d, snapshots `filed_date ≤ d` (RESTATEMENT substitui, NEW
  HOLDINGS soma), piso ≥5 holders;
- universo: ticker mapeado, preço ≥ $1 — **sem corte de ADV** (a perna
  ilíquida da literatura fica dentro; custos são etapa posterior);
- quintis EW e VW(mktcap), holding até a próxima decisão;
- spread médio, t Newey-West(4), Sharpe anualizado, IC Spearman, monotonia;
- matriz de correlação entre sinais (0,8 = um fator, não dois);
- `conf_reveal` avaliado como excesso do grupo flagged (cobertura fina demais
  pra quintis).

## Avisos que continuam valendo

- ~50 eventos independentes: **nada aqui passa Harvey-Liu-Zhu (t>3) sozinho**;
  os t-stats servem pra ordenar candidatos, não pra declarar descobertas. Com
  17 sinais × 2 versões, ~2 células |t|>2 são esperadas por acaso — o REPORT
  lista tudo, não só o que passou;
- sobreviventes Yahoo (perna curta da literatura sub-representada);
- custos ficam pra etapa de portfólio (breakeven no general_plan).
