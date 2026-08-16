# Novos Fatores de Positioning com 13F

## Framework de pesquisa: de crowding estático para flow × structure × timing

**Objetivo.** Propor novas famílias de sinais de positioning usando a base 13F já construída, priorizando ideias que (i) sejam economicamente identificáveis, (ii) respeitem o relógio real de disclosure, (iii) aproveitem instrumentos já validados no projeto e (iv) evitem repetir famílias que o próprio funil de falsificação já rejeitou.

**Base principal.** *Fator de Posicionamento 13F — Conclusões consolidadas* (sessão de pesquisa de 14–16/08/2026). O relatório mostra que os sinais mais robustos vieram de **fluxo com direção e timing**, enquanto níveis de crowding, centralidade, “smart money” e outras variáveis de estado falharam como preditores direcionais. Em particular: `new_conviction` e `distress_mom` sobreviveram ao funil; o fluxo implícito por filer foi validado externamente; e o efeito de copycat pós-filing aparece como um bolso ainda aberto para pesquisa.

---

## 1. Princípio central

A pergunta não deve ser apenas:

> “Quão crowded está uma ação ou um fator?”

Mas sim:

> **“Para onde o capital institucional está se movendo, qual mecanismo força esse movimento e qual é o multiplicador de preço dessa movimentação?”**

O projeto já sugere uma regra prática:

- **Estado sem seta** (`crowding`, `HHI`, centralidade, exposição estática) → normalmente útil como **condicionador ou risco**.
- **Fluxo com seta** (compra deliberada, funding shock, venda forçada, disclosure shock) → candidato a **sinal direcional**.
- **Estrutura** (rede, fragilidade, co-holdings, liquidez) → deve entrar multiplicando ou propagando um choque validado, não substituindo-o.

---

## 2. Notação mínima

Em cada trimestre `t`, defina:

- `W_t ∈ R^(M×N)`: matriz gestor × ação; `W[m,i,t]` é o peso da ação `i` no book do gestor `m`.
- `X_t = ΔW_t^adj`: matriz de mudanças de posição, corrigida por splits, drift de preço e eventos corporativos.
- `f_t ∈ R^M`: vetor de fluxo implícito de AUM por gestor (instrumento já validado no projeto).
- `Z_t ∈ R^(N×K)`: matriz ação × fator (Momentum, Size, Beta, Low Vol, setores; depois Value/Quality se houver fundamentals PIT confiáveis).

A exposição de cada gestor aos fatores é:

```text
E_t = W_t Z_t

E[m,k,t] = Σ_i W[m,i,t] · Z[i,k,t]
```

Essa matriz `E_t` é o elo entre holdings individuais e positioning em fatores.

---

## 3. Ranking das novas ideias

| Prioridade | Ideia | Tipo | Dificuldade | Por que vale testar |
|---|---|---|---|---|
| 1 | Factor Flow Pressure | fator clássico + fluxo | média | transforma exposição em demanda de capital |
| 2 | Correlation-Adjusted Breadth | stock signal | média | desconta votos redundantes sem “smart money” |
| 3 | Disclosure Innovation | event-driven | média | usa o maior diferencial da base: timestamp real |
| 4 | Position-Age / Cohort Flow | stock signal | fácil | generaliza `new_conviction` vs demanda velha |
| 5 | Factor Rebalancing Mismatch | fator/stock | média | prevê trades necessários para manter estilo |
| 6 | Signed Fragility | flow × vulnerabilidade | média | ressuscita crowding com uma seta econômica |
| 7 | Institutional Stress Eigenmodes | matriz/eigenfactor | alta | aprende baskets de unwind endógenos |
| 8 | Factor Stress Eigenmodes | matriz de fatores | média-alta | mede fatores financiados pelo mesmo capital |
| 9 | Flow Eigenfactors (SVD de Δholdings) | latent factors | média-alta | descobre rotações institucionais sem rótulo |
| 10 | Extensive × Intensive Margin | stock signal | fácil | separa entradas/saídas de adds/trims |
| 11 | Demand-System Price Multiplier | estrutural | alta | transforma fluxo em impacto de equilíbrio |
| 12 | Holdings-Confirmed CoMomentum | holdings + preços | média | separa choque idiossincrático de fluxo comum |
| 13 | Institutional Headroom / Saturation | stock signal | fácil-média | mede capacidade futura de continuar comprando/vendendo |

---

# 4. Factor Flow Pressure

## Core idea

Em vez de perguntar **quanto** os gestores estão expostos a Momentum, Value ou Size, medir **quanto dinheiro está entrando ou saindo de cada fator**.

### 4.1 Active Factor Rotation

Quanto os gestores mudaram deliberadamente sua exposição:

```text
AFR[k,t] = Σ_m AUM[m,t-1] · ( E[m,k,t] - E_cf[m,k,t] )
```

`E_cf` é a exposição contrafactual do book antigo, reavaliado ao estado atual das ações/fatores. Isso evita chamar de “trade” uma mudança de exposição causada apenas por drift.

### 4.2 Funding-Induced Factor Flow

Quanto do fluxo do gestor deve mecanicamente atingir o fator que ele já carregava:

```text
FFF[k,t] = Σ_m f[m,t] · E[m,k,t-1]
```

### 4.3 Factor Flow total

```text
FactorFlow[k,t] = AFR[k,t] + FFF[k,t]
```

Normalize por capacidade/liquidez do basket do fator:

```text
FactorPressure[k,t]
    = FactorFlow[k,t]
      / Σ_i |Z[i,k,t]| · ADV[i,t]
```

### Interpretação

Em vez de “Momentum está +2σ crowded”, o painel passa a dizer:

- posicionamento atual;
- entrada/saída recente de capital;
- parte deliberada vs parte causada por funding;
- fluxo em unidades de capacidade/liquidez.

**Hipótese de teste:** `FactorPressure` prevê continuação de curto prazo quando o fluxo ainda está sendo executado e/ou reversão posterior quando a pressão se exaure. O sinal da hipótese deve ser pré-registrado por horizonte, porque o relatório atual já mostrou que continuação vs reversão depende criticamente da janela.

---

# 5. Correlation-Adjusted Breadth

## Problema do breadth tradicional

Se 20 gestores compram a mesma ação, `ΔBreadth` conta 20 votos. Mas, se 15 desses gestores historicamente copiam as mesmas fontes ou sempre se movem juntos, existem muito menos que 20 “experimentos independentes”.

A solução não é escolher “gestores inteligentes”; o próprio projeto mostrou que skill-weighting piorou os sinais. A solução é **descontar redundância**.

Para uma ação `i`, forme o vetor:

```text
x_i = [ sign(Δw[1,i]), ..., sign(Δw[M,i]) ]'
```

Estime a matriz histórica de correlação das decisões dos gestores:

```text
C[m,n] = Corr(x_m, x_n)
```

Então construa um consenso GLS:

```text
IB[i] = (1' C^(-1) x_i) / sqrt(1' C^(-1) 1)
```

Na prática, use shrinkage / ridge na inversão de `C`.

### Intuição

- 20 compradores independentes → score grande.
- 20 gestores altamente correlacionados → score muito menor.
- poucos compradores independentes contra muitos copycats → pode continuar sendo um sinal positivo.

**Aplicações naturais:** substituir o breadth bruto em `ΔBreadth`, `new_conviction`, births e deaths.

**Teste-chave:** comparar `IB` vs breadth bruto em rank-IC, sorts e regressão Fama-MacBeth; depois testar incrementalidade dentro do campeão `new_conviction`.

---

# 6. Disclosure Innovation

## Core idea

O nowcast de `ΔIO` não precisa gerar dinheiro por prever o filing. Seu valor pode estar em medir **o choque informacional causado pelo filing quando ele efetivamente se torna público**.

Antes de um novo filing entrar:

```text
μ[i,τ-] = E[ΔIO_i | informação pública até τ-]
```

Depois do filing:

```text
μ[i,τ+] = E[ΔIO_i | informação pública até τ+]
```

Defina:

```text
DisclosureShock[i,τ] = μ[i,τ+] - μ[i,τ-]
```

Idealmente, padronize pela incerteza da inovação:

```text
ZDisclosure[i,τ]
    = (μ[i,τ+] - μ[i,τ-]) / σ_innovation[i,τ]
```

E amplifique pelo capital seguidor e pela liquidez:

```text
DIS[i,τ]
    = ZDisclosure[i,τ]
      · ShadowAUM[m]
      / ADV[i,τ]
```

### Por que isso é diferente de “antecipar filing”

- Prever o filing: “consigo adivinhar o que ainda será revelado?”
- Disclosure innovation: “o filing que acabou de chegar **mudou muito** a expectativa pública sobre a posição final?”

O segundo é um verdadeiro event shock e combina diretamente com o bolso `follow-VI / copycat` já identificado no relatório.

### Horizonte

Primeiro teste: `τ → τ+1d`, `τ+3d`, `τ+5d`, `τ+10d`, sempre respeitando timestamp de aceitação real.

---

# 7. Position-Age / Cohort Flow

`new_conviction` funcionou; demanda institucional mais velha foi muito mais fraca ou invertida. Em vez de manter a distinção binária, construa a **term structure de idade da posição**.

Para cada edge gestor-ação:

```text
Age[m,i,t] = número de trimestres consecutivos com posição
```

Separe fluxos por cohort:

```text
Flow_i^(a) = Σ_{m : Age[m,i]=a} Δw[m,i]
```

com `a = 0, 1, 2, 3, 4+`.

Você passa a estimar uma curva:

```text
alpha(age=0), alpha(age=1), ..., alpha(age=4+)
```

Depois generalize:

```text
CohortFlow[i] = Σ_m g(Age[m,i]) · Δw[m,i]
```

onde `g(age)` é estimada somente dentro da amostra de treino ou sujeita a uma restrição monotônica para reduzir overfit.

### Hipótese econômica

Fresh buys representam nova convicção; posições antigas podem incorporar inércia, stale demand ou menor informação marginal.

---

# 8. Factor Rebalancing Mismatch

## Ideia

Gestores têm preferências relativamente persistentes por estilos/fatores. As características das ações mudam. Portanto, uma ação pode deixar de “combinar” com o estilo dos seus atuais donos, criando **trade previsível de rebalanceamento**.

Exemplo: gestor historicamente muito Momentum continua carregando uma ação cujo momentum colapsou.

Estime a preferência do gestor pelo fator `k`:

```text
phi[m,k] = preferência histórica / exposição estrutural do gestor ao fator k
```

Para a ação `i`, calcule a preferência média de seus owners:

```text
PhiOwner[i,k]
    = Σ_m h[m,i] · phi[m,k]
      / Σ_m h[m,i]
```

Compare com a característica atual da ação:

```text
Mismatch[i,k] = mismatch(Z[i,k], PhiOwner[i,k])
```

E agregue:

```text
PredictedRebalanceFlow[i]
    = Σ_k gamma[k] · Mismatch[i,k]
```

### Implementação inicial recomendada

Começar somente com **Momentum**, pois é construível com 13F + market data e evita o risco de fundamentals não-PIT.

### Teste principal

Verificar se `Mismatch[t]` prevê `Δholdings[t+1]` antes de testar retorno. Primeiro provar o mecanismo; depois testar preço.

---

# 9. Signed Fragility

Fragilidade sem direção já falhou como tese de retorno. A solução é usar fragilidade como **multiplicador de um choque direcional**.

Estime a covariância dos fluxos dos gestores:

```text
Sigma_f = Cov(f_t)
```

Para cada ação `i`, construa a exposição a funding shocks, escalada por liquidez:

```text
b_i = [ w[1,i]/ADV_i, ..., w[M,i]/ADV_i ]'
```

Fragilidade:

```text
Fragility[i] = b_i' Sigma_f b_i
```

Choque atual:

```text
Pressure[i] = Σ_m f[m,t] · w[m,i,t-1] / ADV[i]
```

Sinal:

```text
SignedFragility[i]
    = Pressure[i] · sqrt(Fragility[i])
```

### Interpretação

Não é “ação crowded cai”. É:

> há um choque vendedor **e** a ação está detida por gestores cujos funding shocks tendem a acontecer juntos.

Isso dá uma seta econômica clara à vulnerabilidade.

---

# 10. Institutional Stress Eigenmodes

Essa é uma das construções mais interessantes para um projeto quantitativo mais matemático.

Considere apenas a covariância de outflows:

```text
Sigma_f^- = Cov(min(f_t, 0))
```

Construa:

```text
G_t = D_ADV^(-1) W_t' Sigma_f^- W_t D_ADV^(-1)
```

`G_t` é uma matriz `N×N` em que `G[i,j]` mede quanto as ações `i` e `j` estão expostas a **venda simultânea causada pelos mesmos funding shocks**.

Faça a eigendecomposição:

```text
G_t = V Lambda V'
```

Os principais autovetores são **institutional unwind portfolios**: baskets endógenos que o sistema de ownership implica que tenderiam a ser liquidados em conjunto.

Mas o eigenvector sozinho ainda é estado. Dê direção com o choque atual:

```text
p_t = W_t' f_t

a_t = V' p_t
```

Se `a_1,t` é fortemente negativo, o funding shock atual está alinhado justamente ao primeiro modo vulnerável.

Reconstrua a componente de fluxo sistêmico:

```text
p_hat_t = V_r V_r' p_t
```

E use `p_hat[i,t]` como score cross-sectional.

### Diferença para Bonacich / rede estática

- Bonacich: `network structure → return`.
- Stress eigenmodes: `funding shock → ownership transmission matrix → forced-flow pressure`.

A segunda cadeia é economicamente identificável e falsificável.

---

# 11. Factor Stress Eigenmodes

Uma versão menor e extremamente interpretável usa diretamente a matriz de exposição dos gestores aos fatores:

```text
E = W Z
```

Construa:

```text
Gamma = E' Sigma_f E
```

`Gamma` é `K×K`.

- `Gamma[k,k]`: fragilidade do fator `k` a funding shocks.
- `Gamma[k,l]`: quanto os fatores `k` e `l` dependem do mesmo capital / de funding shocks correlacionados.

Eigendecomponha:

```text
Gamma = Q Lambda Q'
```

Os autovetores de `Gamma` são combinações endógenas de fatores financiadas pelo mesmo pool de capital.

Dê direção com:

```text
g_t = E' f_t

a_t = Q' g_t
```

Assim o relatório pode dizer algo do tipo:

> “O principal bloco vulnerável do mercado institucional hoje é uma combinação Momentum/Growth/short-Value, e esse bloco está sofrendo um funding shock de -1,8σ.”

O valor não está no rótulo do fator, mas na **dependência comum de capital**.

---

# 12. Flow Eigenfactors: SVD em Δholdings

O NMF em holdings de nível respondeu “quais receitas/estratégias os gestores carregam?”. O próximo objeto deveria responder:

> **“quais baskets os gestores estão movendo agora?”**

Use a matriz de trades, idealmente escalada por liquidez:

```text
X[m,i,t] = ΔDollarHolding[m,i,t] / ADV[i,t]
```

Faça:

```text
X_t = U_t S_t V_t'
```

Cada vetor `V[:,k]` é um **latent institutional flow factor**: um basket de ações sendo comprado/vendido coordenadamente naquele trimestre.

Meça a concentração do fluxo comum:

```text
FlowConcentration[t]
    = s_1[t]^2 / Σ_j s_j[t]^2
```

Decomponha:

```text
CommonFlow = 1' U_r S_r V_r'
IdioFlow   = 1' (X - X_r)
```

### Hipótese inicial

Dado o resultado do DFR no relatório, a prior natural é que **CommonFlow carregue mais informação que IdioFlow**, porque remover a parte mecânica destruiu o sinal em experimentos anteriores.

---

# 13. Extensive × Intensive Margin

Separar mudanças de ownership em quatro átomos:

```text
Birth[i] = # novas posições / # nonholders elegíveis
Death[i] = # exits completos / # holders anteriores
Add[i]   = Σ_existing max(Δw, 0)
Trim[i]  = Σ_existing max(-Δw, 0)
```

Defina:

```text
Extensive[i] = Birth[i] - Death[i]
Intensive[i] = Add[i] - Trim[i]
```

E teste a interação:

```text
Agreement[i] = Extensive[i] · Intensive[i]
```

### Mapa 2×2

| Extensive | Intensive | Leitura |
|---|---|---|
| + | + | novos gestores entram e incumbentes adicionam: consenso forte |
| + | - | novos entram enquanto incumbentes distribuem: transferência de ownership |
| - | + | número de holders cai, mas remanescentes concentram: believers mais concentrados |
| - | - | abandono coordenado: supply forte |

Esse fator é simples, barato e muito interpretável.

---

# 14. Demand-System Price Multiplier

Days-ADV assume aproximadamente:

```text
Impact ∝ DollarFlow / ADV
```

Uma versão estrutural pergunta quanto o preço precisa se mover para que todo o sistema de investidores absorva um choque de demanda.

Modele a demanda relativa do investidor `m` por ação `i` como função de preço e características:

```text
log(w[m,i] / w[m,0])
    = betaP[m] · log(P_i)
      + betaX[m]' X_i
      + epsilon[m,i]
```

Então, para um choque agregado `Δd`, estime:

```text
Δp = M_t · Δd
```

onde `M_t` é um **price multiplier** do sistema de demanda.

O score ideal vira:

```text
ExpectedPriceImpact
    = DemandShock × PriceMultiplier
```

### Por que isso é superior a Days-ADV

Dois nomes podem receber o mesmo fluxo de `$500m`, mas ter impactos muito diferentes por causa de:

- elasticidade dos holders;
- substitutibilidade entre ativos;
- capacidade de outside demand;
- concentração dos owners;
- restrições de portfolio;
- estilo de capital do holder.

É um projeto maior, mas é a ponte natural entre 13F e um modelo estrutural de preço.

---

# 15. Holdings-Confirmed CoMomentum / Common-Flow Return

Use a rede de common ownership para distinguir um choque idiossincrático de um choque de fluxo comum.

Construa uma matriz `A_t` de proximidade por co-holdings. Para cada ação:

```text
r_connected[i,t] = Σ_j A[i,j,t] · r[j,t]
```

Depois retire market, setores e fatores clássicos.

### Leitura

- ação cai sozinha → mais compatível com informação idiossincrática;
- ação cai junto com o basket conectado pelos mesmos owners → mais compatível com common-flow pressure.

A variável pode ser usada como **classificador de mecanismo** antes de decidir continuação/reversão.

Como o próprio projeto encontra continuação em distress, não se deve impor ex-ante que common-flow shocks revertam imediatamente.

---

# 16. Institutional Headroom / Saturation

Uma ideia mais experimental e barata.

Para cada gestor, estime o tamanho máximo “natural” de uma posição usando sua própria distribuição histórica:

```text
w_max[m] ≈ quantil_95 das posições do gestor m
```

Então:

```text
Headroom[m,i] = w_max[m] - w[m,i,t]
```

Agregue a capacidade dos compradores:

```text
BuyCapacity[i] = Σ_m Headroom[m,i] · 1{m está comprando i}
```

Teste:

```text
ContinuationScore[i]
    = NewConviction[i] × BuyCapacity[i]
```

E no lado vendedor uma métrica equivalente de `SellCapacity`.

### Intuição

Duas ações tiveram a mesma compra fresca. Em uma, os gestores ainda têm muito espaço para continuar aumentando; na outra, os principais holders já estão próximos do extremo histórico de concentração.

É menos fundamentado que as ideias anteriores, então deve ser tratado como exploratório.

---

# 17. Um produto unificado de factor positioning

Para cada fator `k`, produzir quatro números:

## 17.1 Position

```text
Position[k,t] = Σ_m AUM[m,t] · E[m,k,t]
```

Quanto capital está atualmente exposto ao fator.

## 17.2 Flow

```text
Flow[k,t]
    = Σ_m [ AUM[m] · ΔE[m,k] + f[m] · E[m,k] ]
```

Para onde o capital está se movendo.

## 17.3 Fragility

```text
Fragility[k,t]
    = E[:,k,t]' Sigma_f,t E[:,k,t]
```

Quão correlacionados são os funding shocks de quem carrega aquele fator.

## 17.4 Pressure

```text
Pressure[k,t]
    = Flow[k,t] / FactorLiquidity[k,t]
```

Quanto o fluxo representa relativamente à capacidade do basket.

### Exemplo de dashboard

```text
MOMENTUM
Position   +1.8σ
Flow       +0.4σ
Fragility  +2.1σ
Pressure   +0.9σ
```

Isso é muito mais informativo que “Momentum está crowded”.

---

# 18. Sequência recomendada de experimentos

## Experimento 1 — Correlation-Adjusted Breadth

**Custo:** baixo/médio.  
**Objetivo:** verificar se descontar redundância melhora `ΔBreadth` e `new_conviction` sem recorrer a skill-weighting.  
**Primeiro teste:** previsão de retorno e incrementalidade sobre breadth bruto.

## Experimento 2 — Position-Age Flow

**Custo:** baixo.  
**Objetivo:** estimar a curva de alpha por idade da posição.  
**Primeiro teste:** monotonicidade de `age=0 → 4+` e estabilidade cross-time.

## Experimento 3 — Factor Flow Pressure

**Custo:** médio.  
**Objetivo:** construir o painel de positioning por fator.  
**Primeiro universo:** Momentum, Size, Beta, Low Vol e setores.

## Experimento 4 — Disclosure Innovation × Shadow AUM / ADV

**Custo:** médio, exige motor diário/event-driven.  
**Objetivo:** explorar a janela 1–5 dias pós-filing com o relógio real.  
**Primeiro teste:** surpresa de disclosure vs retorno imediatamente posterior.

## Experimento 5 — Factor Rebalancing Mismatch

**Custo:** médio.  
**Objetivo:** prever `Δholdings[t+1]` a partir da incompatibilidade entre estilo do owner e característica atual do ativo.  
**Primeiro fator:** Momentum.

## Experimento 6 — Stress Eigenmodes

**Custo:** alto.  
**Objetivo:** transformar funding shocks e ownership em baskets endógenos de unwind.  
**Critério de sucesso:** primeiro prever fluxo/volume/price pressure; retorno vem depois.

---

# 19. Testes de falsificação que eu exigiria

Para evitar repetir o cemitério do projeto:

1. **Mechanism first.** Se a tese é flow, prove primeiro que o score prevê `Δholdings`, volume, saída de capital ou outra variável intermediária.
2. **Randomized ownership placebo.** Embaralhar edges gestor-ação preservando graus; o efeito de rede deve desaparecer ou degradar materialmente.
3. **Randomized flow placebo.** Permutar `f_m` entre gestores; Signed Fragility e stress modes devem perder força.
4. **Size/liquidity theorem test.** Verificar se a correlação com size/ADV aparece mecanicamente em books aleatórios antes de neutralizar.
5. **Timestamp placebo.** Mover o sinal para antes da informação pública; qualquer alpha pós-disclosure que “vaze” para antes do filing indica look-ahead ou má definição de relógio.
6. **Eigenmode stability.** Checar estabilidade de subespaço (`principal angles`) em vez de exigir estabilidade de sinais/ordem dos autovetores individualmente.
7. **Out-of-sample rank preservation.** Para sinais contínuos, exigir monotonicidade de buckets e não apenas top-minus-bottom significativo.
8. **Production suite.** Rebalance real, universo real, borrow, fees e a mesma régua dos fatores já testados.

---

# 20. O que eu não priorizaria agora

Com base no relatório consolidado, não colocaria mais tempo imediatamente em:

- HHI / ownership concentration puro;
- IO level puro;
- mais centralidades de grafo sem choque;
- outro NMF em níveis de holdings;
- seleção de “top managers”;
- skill-weighting;
- mais um residual “deliberado” removendo mecânica;
- regra simples “crowded = short”.

Essas famílias já foram direta ou indiretamente enfraquecidas pelo funil atual.

A fronteira mais promissora é:

```text
FLOW × STRUCTURE × TIMING
```

---

# 21. Escolha única para um projeto mais sofisticado

Se fosse preciso escolher **uma** construção matemática diferenciada:

```text
Gamma_t = E_t' Sigma_flow,t E_t
```

com eigendecomposição:

```text
Gamma_t = Q_t Lambda_t Q_t'
```

A interpretação é forte:

> **factor crowding não é “quantos gestores têm Momentum”; é quais exposições fatoriais estão financiadas pelo mesmo capital e, portanto, vulneráveis aos mesmos funding shocks.**

Depois, a direção vem do fluxo atual:

```text
g_t = E_t' f_t

a_t = Q_t' g_t
```

Isso gera um verdadeiro **Institutional Factor Stress Map**.

---

# 22. Fontes e trilhas de literatura

## Fonte primária do projeto

- **Fator de Posicionamento 13F — Conclusões consolidadas** (14–16 ago. 2026). Base do diagnóstico sobre sinais aprovados/reprovados, fluxo implícito, `new_conviction`, `distress_mom`, copycat, NMF/ICA, Bonacich, DFR e o funil de falsificação.

## Literatura / trilhas usadas na pesquisa anterior

- Sias, R. (2004). *Institutional Herding*. Review of Financial Studies.
- Greenwood, R.; Thesmar, D. (2011). *Stock Price Fragility*. Journal of Financial Economics.
- Antón, M.; Polk, C. *Connected Stocks* — common ownership e comovement.
- Lou, D.; Polk, C. *Comomentum* — crowding/arbitrage activity inferida por comovement.
- Koijen, R.; Yogo, M. *A Demand System Approach to Asset Pricing* — demanda institucional e elasticidades de preço.
- Peng & Wang (working paper, 2026), trilha de **factor rebalancing / factor demand** — mismatch entre estilo do gestor e característica corrente da ação.
- Christoffersen et al. — literatura sobre timing/disclosure de 13F, front-running e copycatting.
- Cella, Ellul & Giannetti — horizonte dos investidores e amplificação de choques via vendas institucionais.

## Material metodológico complementar anexado

- Oliveira, Sandfelder, Fujita, Dong & Cucuringu (2025), *Tactical Asset Allocation with Macroeconomic Regime Detection*. Embora não seja um paper de 13F, a construção de distribuições de regime e matrizes de transição sugere uma extensão futura: condicionar `FactorPressure`, `SignedFragility` e stress modes ao regime macro, sem transformar regime em sinal por si só.

---

## Resumo final

A evolução natural do projeto não é criar mais uma métrica estática de crowding. É construir uma arquitetura em que:

```text
13F holdings
    ↓
exposição / ownership structure
    +
funding & trading flows
    +
real disclosure clock
    ↓
flow pressure
    ↓
transmission / fragility
    ↓
expected price impact
```

As ideias de maior prioridade são **Correlation-Adjusted Breadth**, **Position-Age Flow**, **Factor Flow Pressure**, **Disclosure Innovation**, **Factor Rebalancing Mismatch** e, como projeto matemático principal, **Institutional / Factor Stress Eigenmodes**.
