---
title: "13F Positioning: Novos Eventos e Mecanismos Causais para Fatores"
subtitle: "Ideias de pesquisa a partir de holdings, amendments, fluxos e restricoes reveladas"
author: "Research memo"
date: "16 de agosto de 2026"
geometry: margin=1in
fontsize: 10.5pt
toc: true
toc-depth: 2
numbersections: true
header-includes:
  - |
    \usepackage{booktabs}
    \usepackage{longtable}
    \usepackage{array}
    \usepackage{microtype}
    \usepackage{xcolor}
    \definecolor{darkred}{RGB}{130,20,20}
---

# Sumario executivo

O ponto de partida nao e inventar mais uma estatistica estatica de ownership. O resumo consolidado do projeto ja mostrou um padrao claro: descritores de estado como crowding, centralidade, NMF/SSI sem choque e outras medidas estruturais tenderam a falhar como apostas direcionais; em contraste, os sinais que sobreviveram estavam ligados a **movimento de capital, direcao, timing e mecanismos de trading** - conviccao fresca, distress/forced selling, fluxo implicito por filer e efeitos relacionados ao disclosure.

A regra de design proposta para a proxima rodada e:

$$
\boxed{
\text{evento observavel}
\rightarrow
\text{restricao/incentivo do gestor}
\rightarrow
\text{trade previsivel}
\rightarrow
\text{price pressure}
}
$$

Em outras palavras: **estrutura so deve virar sinal quando existe uma seta causal**.

As ideias abaixo foram selecionadas para explorar coisas que o 13F revela particularmente bem: amendments, mudancas de peso, co-ownership, idade/cost basis aproximada da posicao, turnover do gestor, exposicao a shocks de funding e composicao do book.

## Ranking inicial

| Rank | Ideia | Mecanismo central | Dificuldade | Prioridade |
|---:|---|---|---|---|
| 1 | Restatement Shock | amendment muda publicamente a informacao de demanda | baixa-media | muito alta |
| 2 | Stock Shock -> Fund Outflow -> Other Holdings | choque em uma posicao gera redemption risk e vendas nas demais | media | muito alta |
| 3 | Position Limit Cliff | price drift empurra weights contra limites revelados de concentracao | media | muito alta |
| 4 | Cost-Basis Synchronization | muitos holders cruzam break-even ao mesmo tempo | media | alta |
| 5 | Manager Sell-Hazard | prever quando o holder tipico tende a vender | media | alta |
| 6 | Common Fund-Flow Beta | stocks herdando risco dos funding betas de seus holders | media | alta |
| 7 | Window-Dressing Supply | quarter-end cria trades previsiveis por incentivo de disclosure | baixa-media | alta |
| 8 | Tournament / Catch-Up Rotation | underperformers mudam risco/fatores para recuperar ranking | media-alta | media-alta |
| 9 | Fast-Money Migration x Shock | ownership migra para capital de horizonte curto e fica mais elastico | baixa-media | media-alta |
| 10 | Put/Call Clientele | long options revelam protecao/alavancagem parcial do holder | media | exploratoria |

# 1. O que o projeto atual sugere sobre onde procurar alpha

O relatorio consolidado do projeto chega a quatro conclusoes que importam diretamente para o desenho de novos fatores:

1. **Estado nao tem seta.** Crowding, sig-share de PCA, SSI e vulnerabilidade de rede falharam quando usados sozinhos como predicao direcional.
2. **Fluxo tem seta.** Conviccao fresca e vendas de gestores em distress produziram continuation, e o fluxo implicito por filer foi um instrumento particularmente bem validado.
3. **O relogio importa.** O tratamento point-in-time dos filings e amendments e uma vantagem estrutural da base.
4. **A informacao do 13F parece coletiva e cinetica.** Skill-weighting e smart-money selection pioraram, enquanto a mudanca agregada e a mecanica do capital foram mais uteis.

Isso sugere que novas ideias devem usar a estrutura de holdings como **canal de transmissao**, e nao como aposta por si so.

# 2. Restatement Shock

## Ideia economica

Um 13F original cria um estado publico de informacao. Um amendment posterior pode mudar esse estado de forma discreta. Se a correcao for grande, surpreendente e ocorrer em um nome com pouco ADV ou com gestor muito seguido, ela pode gerar uma nova onda de copycatting ou atualizacao de crenças.

A literatura de 2026 em *Management Science* documenta que restatements de 13F sao economicamente relevantes e suficientemente frequentes para serem estudados sistematicamente. Isso torna a ideia particularmente atraente porque a base do projeto ja preserva versoes, timestamps e semantica de amendments.

## Construcao

Para gestor $m$, acao $i$ e filing/amendment $\tau$:

$$
RestatementShock_{mi,\tau}
=
H^{restated}_{mi,\tau}-H^{original}_{mi,\tau}.
$$

Versao stock-level normalizada por liquidez:

$$
RS_{i,\tau}
=
\frac{\sum_m RestatementShock_{mi,\tau}}{ADV_{i,\tau}}.
$$

Versao mais alinhada ao mecanismo de copycat:

$$
RS^{copy}_{i,\tau}
=
\frac{\sum_m RestatementShock_{mi,\tau}\cdot ShadowAUM_m}{ADV_{i,\tau}}.
$$

## Teste causal

Fazer event study no **timestamp real do amendment**:

$$
AR_{[0,+1]},\quad AR_{[0,+5]},\quad AR_{[+5,+20]}.
$$

Separar:

- amendment que aumenta a posicao;
- amendment que reduz a posicao;
- correcoes pequenas vs grandes;
- alta vs baixa liquidez;
- alto vs baixo Shadow AUM do filer.

## Falsificacao

O efeito deveria ser muito menor para amendments administrativos sem mudanca economica material. Tambem deveria aumentar monotonicamente com magnitude da correcao e diminuir com ADV se o canal for price pressure.

## Horizonte

Evento diario, principalmente 0-5 dias apos o amendment.

# 3. Stock Shock -> Fund Outflow -> Other Holdings Cascade

## Ideia economica

Uma unica posicao pode gerar um grande choque idiossincratico no book. Se investidores finais reagem a esse risco/performance com resgates, o gestor precisa levantar caixa. A venda pode atingir **outras acoes do portfolio que nao tiveram noticia propria**.

O canal e:

$$
\boxed{
\text{single-name shock}
\rightarrow
\text{expected fund outflow}
\rightarrow
\text{liquidation of remaining holdings}
\rightarrow
\text{cross-stock spillover}
}
$$

Isso e conceitualmente diferente de um grafo de centralidade. O grafo apenas define **por onde o choque passa**.

## Etapa 1 - exposicao do gestor ao choque

Use abnormal return ou retorno idiossincratico:

$$
ShockExposure_{m,t}
=
\sum_i w_{mi,t-1}\,|AR_{i,t}|\,\mathbf 1(|AR_{i,t}|>c).
$$

Pode-se separar good/bad shocks.

## Etapa 2 - aprender sensibilidade de funding

Como o projeto ja possui fluxo implicito por gestor $f_{m,t}$, estime:

$$
f_{m,t+1}
=
\alpha_m+\beta\,ShockExposure_{m,t}+\gamma'Controls_{m,t}+\varepsilon_{m,t+1}.
$$

Gere:

$$
\widehat{Outflow}_{m,t+1}.
$$

## Etapa 3 - projetar nas outras holdings

Para cada acao $j$, excluindo o originador do choque:

$$
CascadePressure_{j,t}
=
\frac{
\sum_m \widehat{Outflow}_{m,t+1}w_{mj,t}
}{ADV_{j,t}}.
$$

## Teste causal forte

Matching dentro de pares de acoes semelhantes:

- B e C tem mesmo setor, size, momentum e beta;
- B compartilha muitos holders com a acao A que sofreu o choque;
- C nao compartilha;
- testar se B tem retorno futuro pior que C.

Isso produz uma identificacao muito mais convincente que `centrality -> return`.

## Horizonte

Dias a alguns meses, dependendo de quao rapido o redemption/funding shock se materializa.

# 4. Position Limit Cliff / Institutional Headroom

## Ideia economica

Gestores possuem limites formais ou informais de concentracao. O 13F nao reporta esses limites, mas a historia do proprio gestor pode revelar uma fronteira empirica.

O mecanismo nao e simplesmente "winner reverte". E:

$$
\text{price appreciation}
\rightarrow
\text{weight drift}
\rightarrow
\text{position encosta na constraint}
\rightarrow
\text{trim futuro previsivel}.
$$

## Estimando a constraint revelada

Para cada gestor, estime um limite empirico usando a distribuicao historica dos pesos:

$$
c_m = Q_{0.95}(w_{mi,t})
$$

ou, melhor, um limite condicional por rank do nome no book, liquidez e setor.

Calcule o peso contra-factual apos drift de preco, sem trade:

$$
w^{drift}_{mi,t}.
$$

A distancia para a parede e:

$$
Headroom_{mi,t}=c_m-w^{drift}_{mi,t}.
$$

## Primeiro teste: a parede existe?

Estime:

$$
P(\Delta Shares_{mi,t+1}<0\mid w^{drift}_{mi,t}/c_m).
$$

Se houver uma funcao convexa/monotonica perto da fronteira, o mecanismo ganha credibilidade.

## Sinal stock-level

$$
ExpectedTrim_{mi,t}
=
\hat P(trim\mid state_{mi,t})\times \widehat{SizeTrim}_{mi,t}
$$

$$
CapacityWall_{i,t}
=
\frac{\sum_m ExpectedTrim_{mi,t}}{ADV_{i,t}}.
$$

## Falsificacao

O efeito deveria ser mais forte quando o aumento de peso veio de **price drift**, e nao de uma compra deliberada recente. Tambem deveria ser mais forte em gestores com historico de limites mais estaveis.

# 5. Institutional Cost-Basis Synchronization

## Ideia economica

O 13F nao fornece o preco exato de entrada, mas mudancas trimestrais de shares permitem construir uma aproximacao da base de custo. Se muitos holders relevantes estiverem perto do mesmo break-even, pequenos movimentos de preco podem deslocar simultaneamente muitos portfolios de ganho para perda ou vice-versa.

A literatura de disposition effect mostra que capital gains overhang dos holders pode alterar a velocidade de reacao dos precos a noticias.

## Pseudo cost basis

Quando shares aumentam, associe as novas shares a um preco medio do trimestre ou VWAP aproximado:

$$
CB_{mi,t}=\text{estimated weighted purchase price}.
$$

Unrealized P&L:

$$
UPL_{mi,t}
=
\frac{P_t-CB_{mi,t}}{CB_{mi,t}}.
$$

## Massa perto do break-even

$$
BreakEvenMass_{i,t}(h)
=
\sum_m OwnershipShare_{mi,t}
\mathbf 1(|UPL_{mi,t}|<h).
$$

Uma versao continua usa kernel density em torno do preco atual.

## Sinal condicional

Nao usar `BreakEvenMass` sozinho. Interagir com evento/direcao:

$$
BreakEvenPressure_{i,t}
=
BreakEvenMass_{i,t}\times RecentReturn_{i,t}
$$

ou com earnings surprise / abnormal return.

## Teste economico

Se o canal for comportamento de realizacao, a reacao deveria depender do sinal da noticia e do sinal do UPL agregado. Se for apenas momentum disfarçado, essa assimetria nao aparecera.

# 6. Manager Sell-Hazard Model

## Ideia economica

Em vez de tentar prever "qual acao o gestor gosta", aprender **quando um holder tende a apertar SELL**.

Dados institucionais de alta frequencia documentam que as decisoes de venda de portfolio managers podem ser muito mais sistematicas que as de compra, inclusive com padroes nao lineares em ganhos/perdas.

## Modelo por edge gestor-stock

Defina:

$$
Sell_{mi,t+1}=\mathbf 1(\Delta Shares_{mi,t+1}<0).
$$

Features possiveis:

- unrealized P&L aproximado;
- idade da posicao;
- peso atual e percentile dentro do book;
- weight drift desde o filing anterior;
- drawdown desde entrada;
- retorno recente;
- liquidez da acao;
- distress/funding state do gestor;
- distancia para a concentration wall.

Aprenda:

$$
\hat h_m(x)=P(Sell_{mi,t+1}=1\mid x_{mi,t}).
$$

Se houver poucas observacoes por gestor, use partial pooling / hierarchical logistic regression.

## Supply previsto

$$
ExpectedSupply_{i,t+1}
=
\sum_m H_{mi,t}\hat h_m(x_{mi,t}).
$$

Normalizacao:

$$
SellPressure_{i,t+1}
=
\frac{ExpectedSupply_{i,t+1}}{ADV_{i,t}}.
$$

## Principal teste

Separar poder preditivo de:

1. `quem vende`;
2. `quanto vende`;
3. `retorno futuro apos a venda`.

O modelo pode ser util como **detector de oferta** mesmo que nem toda venda gere alpha.

# 7. Common Fund-Flow Beta Factor

## Ideia economica

Flows de fundos possuem um componente comum. Se determinados gestores tem alta sensibilidade a esse common funding shock, as acoes que eles possuem herdam uma exposicao ao risco de liquidacao conjunta.

A literatura de Dou, Kogan e Wu mostra uma estrutura de fator nos fund flows e implicacoes de asset pricing associadas a flow betas.

## PCA dos fluxos dos gestores

Com $f_t\in\mathbb R^M$:

$$
f_t = B g_t + \epsilon_t,
$$

onde $g_t$ e o primeiro ou os primeiros common flow factors.

Para cada gestor:

$$
f_{m,t}=\alpha_m+\beta_m^F g_t+\epsilon_{m,t}.
$$

## Exposicao stock-level

$$
FlowBeta_{i,t}
=
\sum_m OwnershipShare_{mi,t}\beta_m^F.
$$

Uma versao mais estrutural usa holdings em dolar/ADV:

$$
FundingFragility_{i,t}
=
\sum_m \frac{H_{mi,t}}{ADV_{i,t}}\beta_m^F.
$$

## Uso correto

Pode ser testado como risk factor de longo prazo, mas a versao mais alinhada ao projeto e interagir com o shock corrente:

$$
SignedFlowBeta_{i,t}
=
FlowBeta_{i,t}\times g_t.
$$

Assim o estado de funding ganha direcao.

# 8. Window-Dressing Supply Forecast

## Ideia economica

O fechamento do trimestre e um evento institucional: a carteira que sera divulgada e observada por investidores e pares fica "fotografada". Se alguns gestores historicamente limpam losers ou adicionam winners proximo ao quarter-end, o 13F anterior pode ser usado para prever **quem potencialmente precisa negociar antes da foto seguinte**.

## Aprender propensao do gestor

Para cada gestor, use historico de mudancas em holdings condicionadas a performance intra-quarter:

$$
WD_m
=
P(\text{sell loser / buy winner at quarter end}).
$$

## Oferta prevista antes do quarter-end

Usando o book conhecido do trimestre anterior:

$$
ExpectedWDSell_{i,q}
=
\sum_m w_{mi,q-1}\,WD_m\,\mathbf 1(Return_{i,q}\ll0).
$$

$$
WDPressure_{i,q}
=
\frac{ExpectedWDSell_{i,q}}{ADV_i}.
$$

## Desenho de teste

Comparar:

- ultimos 5 dias do trimestre vs dias comuns;
- Q4 vs Q1-Q3;
- gestores com alta vs baixa propensao historica;
- losers que sao top positions vs pequenas posicoes.

Uma reversao nos primeiros dias do novo trimestre fortaleceria o canal de price pressure temporario.

# 9. Tournament / Catch-Up Factor Rotation

## Ideia economica

Gestores podem responder a underperformance relativa alterando risco, concentracao ou exposicao a fatores para recuperar ranking. Isso cria uma forma de **flow previsivel de fatores antes que o proximo 13F seja observado**.

Essa ideia fica especialmente interessante depois de construir a matriz manager-factor:

$$
E_{m,k,t}
=
\sum_i w_{mi,t}X_{i,k,t}.
$$

## Etapa 1 - inferir performance do book

Reconstituir o retorno aproximado do book entre filings:

$$
Perf_{m,t}.
$$

Definir underperformance relativa a um benchmark de estilo:

$$
Underperf_{m,t}=Perf_{m,t}-Benchmark_{m,t}.
$$

## Etapa 2 - aprender resposta de risco

Estimar historicamente:

$$
\Delta E_{m,k,t+1}
=
\alpha_k+\beta_k Underperf_{m,t}+\gamma_k'Controls+\varepsilon.
$$

Exemplos:

- underperformers aumentam beta?
- aumentam momentum?
- aumentam concentracao?
- migram para fatores que performaram recentemente?

## Etapa 3 - converter target factor rotation em stocks

$$
PredictedFactorDemand_{i,t}
=
\sum_m AUM_m\sum_k \widehat{\Delta E}_{m,k,t+1}X_{i,k,t}.
$$

Depois normalize por ADV.

## Falsificacao

O efeito deve ser maior em gestores com historico de risk-shifting e em momentos do ano em que ranking/incentivos importam mais. Se a relacao nao se repete dentro do mesmo gestor, a historia de tournament fica fraca.

# 10. Fast-Money Migration x Shock

## Ideia economica

Duas acoes podem ter o mesmo institutional ownership, mas uma ser detida por capital de horizonte muito mais curto. A composicao dos holders altera a elasticidade da oferta futura.

Turnover/churn de holdings e uma proxy classica de horizonte institucional.

## Churn do gestor

Exemplo de medida:

$$
Churn_m
=
\frac{\sum_i |\Delta DollarHolding_{mi}|}{\sum_i AverageDollarHolding_{mi}}.
$$

Construa um score de fast money:

$$
Fast_m=z(Churn_m).
$$

## Composicao da ownership

$$
FastShare_{i,t}
=
\sum_m OwnershipShare_{mi,t}Fast_m.
$$

A variavel mais interessante e a migracao:

$$
FastMoneyMigration_{i,t}
=
FastShare_{i,t}-FastShare_{i,t-1}.
$$

## Nao tradar sem seta

Usar interacoes como:

$$
NegativeShock_{i,t}\times FastShare_{i,t}
$$

ou

$$
FundingStress_t\times FastMoneyMigration_{i,t}.
$$

A hipotese e que a mesma noticia ruim produz mais oferta futura quando o shareholder base e mais curto e elastico.

# 11. Put/Call Clientele e Protected Ownership

## Ideia economica

Form 13F inclui determinadas long put/call positions, enquanto written options e short equity positions nao aparecem. Se a ingestao preservou o campo `putCall`, isso permite observar parcialmente **como um holder implementa a exposicao**.

Nao e possivel reconstruir delta/gamma exatos sem strike, maturity e demais detalhes. Portanto a proposta nao e tratar isso como exposure equivalente a shares, e sim como **tipo de clientele**.

## Estados possiveis

### Protected holder

$$
Stock_{mi}>0,\qquad Put_{mi}>0.
$$

### Levered/synthetic bullish holder

$$
Call_{mi}\gg Stock_{mi}.
$$

### Bearish/protection-heavy overlay

$$
Put_{mi}\gg Stock_{mi}.
$$

## Primeira validacao

Perguntar se o comportamento subsequente do holder e diferente:

$$
P(SellStock_{mi,t+1}\mid Stock+Put)
$$

vs

$$
P(SellStock_{mi,t+1}\mid StockOnly).
$$

Se protected holders liquidarem menos apos drawdowns, pode haver um canal de supply resiliency.

## Status

Exploratorio. A limitacao de informacao sobre opcoes e real, entao o primeiro objetivo e validar se `putCall` melhora a previsao de trades posteriores, nao construir alpha diretamente.

# 12. Como combinar as ideias em uma arquitetura unica

As melhores ideias acima podem ser expressas dentro de um mesmo modelo de **expected institutional supply/demand**.

Para cada edge gestor-stock, defina um state vector:

$$
x_{mi,t}
=
[
UPL,
Age,
Weight,
Headroom,
Churn_m,
FundingState_m,
ShockExposure_m,
PutCallState,
\ldots
].
$$

Aprenda duas funcoes:

$$
p^{sell}_{mi,t}=P(Sell_{mi,t+1}=1\mid x_{mi,t}),
$$

$$
p^{buy}_{mi,t}=P(Buy_{mi,t+1}=1\mid x_{mi,t}).
$$

Com intensidade esperada:

$$
q^{sell}_{mi,t}=E[DollarSell\mid Sell,x],
$$

$$
q^{buy}_{mi,t}=E[DollarBuy\mid Buy,x].
$$

O imbalance previsto por stock seria:

$$
ExpectedNetDemand_{i,t+1}
=
\sum_m
\left(
 p^{buy}_{mi,t}q^{buy}_{mi,t}
-
 p^{sell}_{mi,t}q^{sell}_{mi,t}
\right).
$$

Finalmente:

$$
\boxed{
InstitutionalPressure_{i,t+1}
=
\frac{ExpectedNetDemand_{i,t+1}}{ADV_{i,t}}
}
$$

Essa arquitetura e uma extensao natural do achado central do projeto: o 13F parece mais util quando tratado como **sistema de demanda institucional** do que como catalogo de "best ideas".

# 13. Roadmap de implementacao recomendado

## Fase 1 - quick wins

### Experimento A - Restatement Shock

**Dados:** versoes do filing + timestamps + ADV + retornos diarios.  
**Prazo conceitual:** curto.  
**Teste:** event study, magnitude x ShadowAUM x 1/ADV.

### Experimento B - Position Limit Cliff

**Dados:** holdings historicos + precos.  
**Teste:** probabilidade de trim por distancia da fronteira.

### Experimento C - Fast-Money Migration x Shock

**Dados:** 13F puro + precos.  
**Teste:** abnormal return futuro apos shock, condicionado a churn dos holders.

## Fase 2 - mecanismos com maior potencial

### Experimento D - Shock Cascade

Integrar single-stock abnormal returns, fluxo implicito por gestor e co-ownership.

### Experimento E - Cost-Basis Synchronization

Criar pseudo-lotes e validar a relacao entre UPL e sell hazard antes de tradar qualquer sinal.

### Experimento F - Common Flow Beta

Extrair fatores dos fluxos dos gestores e mapear a ownership para flow-beta stock-level.

## Fase 3 - modelo estrutural unificado

Combinar sell hazard, headroom, funding shock e cost basis em um estimador de expected net demand por stock.

# 14. Testes de falsificacao que deveriam ser obrigatorios

Para evitar que mecanismos causais virem apenas nomes bonitos para momentum/size/liquidity:

1. **Placebo temporal:** deslocar o evento para datas sem evento.
2. **Placebo de ownership:** embaralhar holders dentro de buckets de size/setor.
3. **Matched stocks:** comparar acoes com mesmos fatores, mas diferente exposicao ao canal institucional.
4. **Monotonicidade:** magnitude do efeito deve crescer com a intensidade causal prevista.
5. **Liquidez:** price-pressure mechanisms deveriam ser mais fortes quando o mesmo dollar flow representa mais ADV.
6. **Dentro do gestor:** quando possivel, identificar a funcao de reacao dentro do mesmo filer, reduzindo confound entre tipos de gestores.
7. **Direcao pre-registrada:** definir antes do backtest o sinal esperado e a janela.
8. **Separar detector de alpha:** primeiro provar que o instrumento preve trade/flow; somente depois testar retorno.

# 15. O que eu implementaria primeiro

Se o objetivo e maximizar informacao por unidade de trabalho, minha ordem seria:

1. **Restatement Shock** - infraestrutura quase pronta, evento claro, literatura recente e timestamp exato.
2. **Position Limit Cliff** - simples o suficiente para falsificar rapido e com boa historia mecanica.
3. **Shock -> Outflow -> Other Holdings** - melhor projeto causal; combina o instrumento de fluxo que ja funcionou com a rede de ownership.
4. **Manager Sell-Hazard** - transforma varios sinais em uma funcao unica de expected supply.
5. **Cost-Basis Synchronization** - behavioral mechanism forte, mas exige cuidado com aproximacao do preco de entrada.
6. **Common Fund-Flow Beta** - bom candidato a fator de positioning mais estrutural.
7. **Window Dressing** - barato e bom como evento sazonal/event-driven.
8. **Tournament Rotation** - interessante depois da decomposicao manager-factor estar pronta.

# 16. Referencias e evidencias relacionadas

**Base interna do projeto**

- *Fator de Posicionamento 13F - Conclusoes consolidadas* (16 ago. 2026). Principais conclusoes usadas aqui: importancia do timestamp real; sucesso relativo de sinais de fluxo; falha de descritores de estado sem direcao; validacao do fluxo implicito por filer; desempenho de `new_conviction`, `distress_mom` e `copycat`.

**13F restatements**

- Cao, S.; Da, Z.; Jiang, X. D.; Yang, B. (2026). *Do Hedge Funds Strategically Misreport Their Holdings? Evidence from 13F Restatements*. Management Science. DOI: 10.1287/mnsc.2024.08833.

**Capital gains overhang / disposition effect**

- Frazzini, A. (2006). *The Disposition Effect and Underreaction to News*. Journal of Finance, 61(4), 2017-2046.

**Common fund-flow risk**

- Dou, W. W.; Kogan, L.; Wu, W. *Common Fund Flows: Flow Hedging and Factor Pricing*. NBER Working Paper 30234; Journal of Finance forthcoming in the versions surfaced by the authors.

**Institutional sell behavior**

- Akepanidtaworn, K.; Di Mascio, R.; Imas, A.; Schmidt, L. *Selling Fast and Buying Slow: Heuristics and Trading Performance of Institutional Investors*. Evidence from detailed institutional portfolio data; selling decisions exhibit strong systematic patterns, including a U-shaped relation with position performance.

**Idiosyncratic stock risk and fund flows**

- Di Maggio, M.; Franzoni, F.; Kogan, S.; Xing, R. (2023 working-paper version). *Avoiding Idiosyncratic Volatility: Flow Sensitivity to Individual Stock Returns*. Useful motivation for the shock -> flow channel.

**Investment horizon / churn**

- Yan, X.; Zhang, Z. (2009). *Institutional Investors and Equity Returns: Are Short-term Institutions Better Informed?* Review of Financial Studies. Uses historical portfolio turnover to distinguish short- and long-horizon institutions.

**Form 13F option reporting**

- U.S. Securities and Exchange Commission. *Frequently Asked Questions About Form 13F*. Long put/call positions meeting the reporting rules may appear; written options are not reported.

# Conclusao

O maior espaco ainda aberto nao parece ser "mais uma metrica de crowding". O espaco mais interessante e reconstruir **funcoes de reacao institucionais** a partir dos holdings:

$$
\boxed{
\text{Quem sera forcado/incentivado a negociar?}
\times
\text{quanto capital?}
\times
\text{em quais stocks?}
\times
\text{contra quanta liquidez?}
}
$$

Restatements, concentration walls, cost-basis cliffs, funding shocks e horizon migration sao todos exemplos de eventos/estados em que o 13F pode ajudar a responder essa pergunta de forma causalmente mais limpa do que um simples `institutional ownership -> return`.
