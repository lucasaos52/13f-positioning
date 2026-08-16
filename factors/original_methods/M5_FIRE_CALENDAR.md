# M5 — Fire-Sale Forward Calendar: oferta forçada prevista, alocada por pecking order

## A ideia em uma frase

Gestor em distress vai vender; **o que** ele vende primeiro é previsível (a
ordem de liquidez do próprio book); **quanto** vem é previsível (o outflow
implícito); e **quando** é já — então dá pra construir, ação por ação, o
calendário da oferta forçada que está a caminho, e ser pago por tomar o outro
lado (Coval-Stafford: "quem provê liquidez quando poucos podem ganha retornos
altamente significativos").

## As três peças, cada uma com o truque que só o 13F nosso dá

**1. QUANTO: fluxo implícito por filer, SEM CRSP MF.** A identidade contábil
por gestor entre dois filings:

```
outflow_implícito(i) = ΔAUM_reportado(i)  −  retorno do book congelado-com-drift(i)
```

O primeiro termo vem dos dois filings; o segundo é a Camada 0 do nowcasting
(holdings × preços diários — já construída e validada). O que sobra é
entrada/saída de capital — **para TODOS os filers 13F, incluindo hedge funds
e advisors que nenhuma base de fluxo cobre**. A literatura inteira de fire
sale usa fluxos do CRSP MF (só mutual funds); o JFE 2023 de fire-sale risk
idem. Este é o diferencial estrutural.

**2. O QUE: alocação por pecking order, não pro-rata.** Coval-Stafford
assumem venda proporcional. A literatura de liquidez (Jiang et al., bonds;
Scholes) mostra que sob outflow INESPERADO vende-se o líquido primeiro —
minimizar impacto hoje, aceitar book pior amanhã. Então a oferta prevista de
um distressed não é w_ij pro-rata: concentra nos nomes de MAIOR liquidez
dentro do book dele nas primeiras semanas, cascateia pros ilíquidos se o
outflow persiste:

```
supply(j,t) = Σ_{i em distress} outflow_i × w_ij × pecking_ij / ADV_j(defasado)
pecking_ij  = rank de liquidez de j DENTRO do book de i (líquido primeiro)
ADV defasado (não contemporâneo) — a armadilha de Wardlaw, evitada por desenho
```

**3. QUANDO: distress observável em tempo real.** Drawdown do book
congelado-com-drift (diário, sem esperar filing) + outflow implícito do
último par de filings. Distress = os dois piscando.

## A validação em dois estágios — a parte mais forte do desenho

**Estágio 1 (fluxo, sem retornos!)**: o modelo prevê QUEM vende O QUÊ. O
próximo 13F do distressed mostra o que ele DE FATO vendeu. Testar: (a) os
distressed venderam mais que os não-distressed? (b) dentro do book deles, a
venda concentrou nos nomes de pecking alto (líquidos), como a teoria diz?
Isso valida a máquina inteira contra dado realizado ANTES de qualquer
afirmação sobre preço — como o SSI validou contra short interest (0,47).

**Estágio 2 (retorno)**: nomes com supply prevista alta → pressão negativa
no curto prazo → REVERSÃO depois (a assinatura Coval-Stafford completa).
Direções pré-registradas; a reversão é o trade (E2 do plano II: prover
liquidez contra fluxo previsível — "a fonte de retorno mais defensável").

## Falsificações embutidas

- placebo: mesma conta para gestores NÃO-distressed (liquid names deles não
  devem sofrer pressão);
- Wardlaw-check: refazer com ADV contemporâneo e mostrar que os resultados
  NÃO dependem da contaminação (ou que dependem — e aí a versão defasada é
  a única reportável);
- pecking-null: se o estágio 1b mostrar venda pro-rata (não pecking), a
  alocação degrada para Coval-Stafford padrão — ainda funciona, perde a
  originalidade da alocação (dito de antemão).

## Linhagem citada e gap

Coval-Stafford (2007, pro-rata); Jiang-Li-Wang (pecking order em bonds);
[JFE 2023 fire-sale risk](https://www.sciencedirect.com/science/article/abs/pii/S0304405X23001204)
(stock-level, MAS fluxos CRSP MF/só mutual funds); Duarte-Eisenbach
(vulnerabilidade agregada); Wardlaw (2020, a armadilha da medida); nosso
Death Supply (IDEAS.md) é o caso-limite (outflow=100%). **Gap: fluxo
implícito de 13F para todos os filers + alocação por pecking order dentro do
book + validação contra vendas realizadas — não encontrado.**

## Custo e encaixe

Tudo já existe: books (snapshots), frozen-drift (nowcasting Camada 0), ADV,
identidade contábil por par de filings. ~1 dia. Encaixa como perna E2 do
stack: new_conviction (seguir informação) + fire calendar (prover liquidez
contra mecânica) — os dois lados da mesma economia, descorrelacionados por
construção.
