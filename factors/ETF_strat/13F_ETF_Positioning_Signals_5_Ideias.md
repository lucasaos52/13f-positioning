---
title: "13F + ETF Positioning Signals"
subtitle: "5 ideias causais e implementáveis com 13F + Yahoo Finance"
author: "Research Blueprint"
date: "August 2026"
geometry: margin=0.8in
fontsize: 10.5pt
header-includes:
  - \usepackage{amsmath}
  - \usepackage{booktabs}
  - \usepackage{longtable}
  - \usepackage{array}
  - \usepackage{hyperref}
---

# Objetivo

O objetivo é construir **positioning factors em ETFs usando essencialmente duas fontes**:

1. **13F**: holdings por manager, shares, market value, filing date e histórico trimestral;
2. **Yahoo Finance**: preço, retorno, volume e proxies simples de risco/market state.

A restrição é deliberada: evitar sinais que dependam de ETF creations/redemptions, opções, Compustat, holdings históricas dos constituents ou dados proprietários. A pergunta central para cada sinal é:

> **Qual é a cadeia causal que transforma uma posição observada no 13F em retorno futuro, mesmo com o atraso de divulgação?**

O atraso do 13F é crítico: o sinal só é tradável **a partir do timestamp público do filing**, nunca no quarter-end. A SEC exige que o Form 13F seja apresentado dentro de 45 dias do fim do trimestre; na prática, managers podem reportar antes do prazo. O backtest deve, portanto, atualizar a informação manager a manager na data efetiva de publicação.

# Ranking executivo

| Rank | Sinal | Tese econômica | Dificuldade | Prioridade |
|---:|---|---|---:|---:|
| 1 | **Sticky Institutional ETF Demand** | Trades de gestores de horizonte longo sobrevivem melhor ao disclosure lag | Baixa-média | **Muito alta** |
| 2 | **ETF Doubling Down** | Aumentar uma posição perdedora revela convicção excepcional | Baixa-média | **Muito alta** |
| 3 | **Abnormal ETF Institutional Adoption** | Remove demanda institucional “mecânica” e isola preferência anormal | Média | **Alta** |
| 4 | **Conviction × Consensus × Persistence** | Best ideas compartilhadas por gestores persistentes contêm mais informação | Baixa | **Alta / baseline** |
| 5 | **Transient-Holder Fragility × Market Shock** | Short-horizon holders amplificam selling pressure em stress e criam reversal | Média | **Alta como conditional factor** |

---

# 1. Sticky Institutional ETF Demand

## Core idea

Nem todo gestor 13F deve receber o mesmo peso. Uma decisão observada com 30-45 dias de atraso só é útil se o investidor tiver uma **tese suficientemente persistente**.

A literatura de 13F mostra que conviction + consensus funciona melhor quando se selecionam managers com horizonte mais longo. Em paralelo, a literatura de ETFs mostra que ETFs concorrentes podem atrair clientelas com horizontes diferentes: ETFs mais líquidos tendem a atrair investidores de horizonte mais curto.

Logo, em vez de perguntar apenas:

> "Quais ETFs instituições compraram?"

pergunte:

> **"Quais ETFs estão sendo comprados por managers que historicamente negociam pouco e mantêm posições por mais tempo?"**

## Passo 1 - estimar churn corretamente

Mudança de peso não é necessariamente trade: parte dela vem do próprio retorno do ativo. Para o manager $m$ e ativo $i$:

$$
w^{drift}_{m,i,t}=
\frac{w_{m,i,t-1}(1+R_{i,t})}
{\sum_j w_{m,j,t-1}(1+R_{j,t})}.
$$

O turnover trimestral corrigido por drift pode ser aproximado por:

$$
Churn_{m,t}=\frac{1}{2}\sum_i
\left|w_{m,i,t}-w^{drift}_{m,i,t}\right|.
$$

Depois suavize, por exemplo:

$$
\overline{Churn}_{m,t}=\frac{1}{4}\sum_{q=0}^{3}Churn_{m,t-q}.
$$

Defina uma qualidade de horizonte:

$$
Quality_{m,t}=1-\operatorname{PercentileRank}(\overline{Churn}_{m,t}).
$$

Managers de churn baixo recebem peso alto.

## Passo 2 - inferir trade no ETF

Para ETF $e$:

$$
Trade_{m,e,t}=w_{m,e,t}-w^{drift}_{m,e,t}.
$$

Uma versão simples do sinal:

$$
\boxed{
StickyDemand_{e,t}=\sum_m Quality_{m,t}\cdot Trade_{m,e,t}
}
$$

Uma versão ainda mais interpretável:

$$
StickyDemand_e = NetBuying^{LowChurn}_e-NetBuying^{HighChurn}_e.
$$

## Estrutura causal

$$
\text{research / strategic allocation}
\rightarrow
\text{persistent trade}
\rightarrow
\text{position survives reporting lag}
\rightarrow
\text{13F reveals part of the view}
\rightarrow
\text{future return}
$$

O ponto causal importante é que o **manager horizon funciona como filtro de stale information**. Se a posição vem de um gestor transient, o trade pode já ter sido fechado quando o filing aparece. Se vem de um gestor sticky, a probabilidade de a tese ainda existir é maior.

## Backtest recomendado

- Universo: equity ETFs com liquidez mínima;
- excluir ou separar broad-beta ETFs como SPY/IVV/VOO;
- rankear ETFs por `StickyDemand`;
- long top decile, short bottom decile;
- rebalancear somente quando novos filings se tornam públicos;
- horizontes de avaliação: 1 semana, 1 mês, 3 meses após disclosure;
- neutralizar beta de mercado na avaliação.

## Teste causal-chave

Compare:

1. raw institutional demand;
2. demand ponderado por manager horizon;
3. demand apenas de low-churn managers.

Se (2) e (3) melhorarem IC/Sharpe em relação a (1), você tem evidência de que **o horizonte do manager é justamente o mecanismo que preserva informação apesar do lag**.

## Principal risco

Churn baixo pode capturar simplesmente gestores passivos ou asset allocators, não skill. Por isso, a versão mais forte deve cruzar `StickyDemand` com conviction ou com ETF specificity.

---

# 2. ETF Doubling Down

## Core idea

Um manager que aumenta uma posição depois que ela andou contra ele está fazendo algo comportamentalmente custoso: tornando o erro anterior ainda mais visível. Isso pode revelar **convicção excepcional**.

A evidência de *Doubling Down* em hedge funds documenta que posições aumentadas após underperformance carregam informação sobre retornos futuros. A extensão aqui é aplicar o mesmo princípio especificamente ao ETF sleeve.

## Passo 1 - medir underperformance residual

Evite confundir um ETF setorial com um simples movimento do mercado. Estime, por exemplo:

$$
r_{e,d}=\alpha_e+\beta_{SPY,e}r_{SPY,d}+\beta_{IWM,e}r_{IWM,d}+\beta_{QQQ,e}r_{QQQ,d}+\epsilon_{e,d}.
$$

No período entre os dois snapshots 13F, compute:

$$
R^{res}_{e,t}=\sum_d \epsilon_{e,d}.
$$

## Passo 2 - identificar o doubling down

$$
DD_{m,e,t}=\mathbf{1}
\left[
Trade_{m,e,t}>0
\;\land\;
R^{res}_{e,t}<0
\right].
$$

Score contínuo:

$$
\boxed{
DoubleDown_e=
\sum_m Quality_m
\cdot Trade_{m,e,t}^{+}
\cdot (-R^{res}_{e,t})^{+}
}
$$

## Estrutura causal

$$
\text{position loses money}
\rightarrow
\text{incentive to cut / hide / window-dress}
$$

mas o manager decide:

$$
\textbf{BUY MORE}
$$

Logo, o trade contém uma informação de segunda ordem: não é apenas uma compra, é uma compra **condicional a uma evidência adversa que já ocorreu**.

## Onde a versão ETF fica mais interessante

Evite interpretar aumento em SPY como convicção específica; pode ser cash management ou beta. O sinal deve ser mais informativo em:

- sector ETFs;
- industry ETFs;
- style/factor ETFs;
- thematic ETFs.

Exemplos conceituais: XLE, XBI, KRE, SMH, XRT, etc.

## Backtest recomendado

Cross-section de ETFs a cada disclosure:

- long ETFs com alto `DoubleDown`;
- controle contra ETFs com institutional buying semelhante, mas **sem** underperformance anterior;
- controle adicional contra ETFs que caíram, mas não receberam aumento de posição.

Esse desenho é melhor do que simplesmente comparar winners vs losers porque tenta isolar a informação contida na reação do manager à perda.

## Teste causal-chave

Faça matching por:

- momentum anterior;
- volatilidade;
- beta;
- volume;
- tamanho aproximado/AUM, se disponível.

A pergunta é:

> Entre ETFs igualmente perdedores, aqueles em que managers aumentaram convicção performam melhor depois do disclosure?

## Principal risco

Pode ser apenas contrarian/reversal. O controle contra ETFs com underperformance semelhante é essencial.

---

# 3. Abnormal ETF Institutional Adoption

## Core idea

Raw institutional ownership é contaminado por **investability**. Um ETF grande, líquido, antigo e barato naturalmente tem mais holders. Isso não significa que o posicionamento contenha informação.

A ideia é modelar o nível de institutional adoption que seria esperado dadas características públicas do ETF e usar apenas o **resíduo anormal**.

## Features disponíveis com 13F + Yahoo

Para cada ETF $e$ e trimestre $t$:

- `Breadth`: número de managers com posição;
- `OwnershipValue`: valor total reportado;
- preço;
- dollar volume médio;
- volatilidade;
- momentum 1m/3m/12m;
- beta vs SPY;
- idade, se puder ser obtida por metadata simples.

Use preferencialmente breadth porque reduz a dominância de um único whale:

$$
Breadth_{e,t}=\log(1+\#ManagersHolding_{e,t}).
$$

## Modelo cross-sectional

A cada trimestre:

$$
Breadth_{e,t}=
\beta_{0,t}
+\beta_{1,t}\log(DollarVolume_{e,t})
+\beta_{2,t}Vol_{e,t}
+\beta_{3,t}Mom_{12m,e,t}
+\beta_{4,t}Beta_{e,t}
+\beta_{5,t}\log(Price_{e,t})
+\varepsilon_{e,t}.
$$

O fator é:

$$
\boxed{AbnormalBreadth_{e,t}=\widehat{\varepsilon}_{e,t}}
$$

ou, talvez mais informativo:

$$
\boxed{\Delta AbnormalBreadth_{e,t}}
$$

## Estrutura causal

Raw ownership mistura:

$$
\text{institutional preference}
+
\text{liquidity}
+
\text{size}
+
\text{accessibility}
+
\text{past returns}
+
\text{benchmark demand}.
$$

Ao retirar a parte previsível, sobra uma aproximação de:

$$
\textbf{latent institutional preference / information}.
$$

A literatura recente em ações mostra que **abnormal institutional ownership**, estimado a partir de características observáveis, contém informação sobre retornos futuros mesmo usando 13F público e atrasado. A versão ETF é uma extensão natural desse framework.

## Melhorias

### 3.1 New-holder breadth

Em vez de nível:

$$
NewHolders_{e,t}=\#\{m: Position_{m,e,t}>0,\ Position_{m,e,t-1}=0\}.
$$

Depois modele a expectativa de `NewHolders` e use o resíduo.

### 3.2 Independent consensus

Dê menos peso a managers cujas carteiras são muito parecidas. Dez managers clonados não equivalem a dez decisões independentes.

## Backtest recomendado

- long top residual decile, short bottom;
- testar nível e mudança;
- comparar breadth vs dollar ownership;
- neutralizar momentum e beta no portfolio final.

## Principal risco

O residual pode estar capturando características omitidas do ETF. A melhor defesa é mostrar que o sinal sobrevive a diferentes especificações e que **a mudança do residual** é mais forte que o nível.

---

# 4. Conviction × Consensus × Persistence no ETF Sleeve

## Core idea

Esse é o melhor **baseline econômico** para o projeto. Ele adapta a literatura de *Best Ideas* e *Systematic 13F Hedge Fund Alpha* para ETFs.

Uma holding só é potencialmente informativa quando combina três dimensões:

1. **Conviction**: é grande para aquele manager;
2. **Consensus**: vários managers independentes expressam a mesma view;
3. **Persistence**: a posição permanece ao longo dos quarters.

## Conviction

Não compare o peso de XBI em um macro fund com o peso de SPY em um asset allocator. Rank dentro do próprio ETF sleeve do manager:

$$
Conviction_{m,e,t}=PercentileRank_m(w^{ETF}_{m,e,t}).
$$

ou padronize:

$$
Conviction_{m,e,t}=z_m(w^{ETF}_{m,e,t}).
$$

## Consensus

$$
Consensus_{e,t}=
\#\left\{m: Conviction_{m,e,t}>q_{90}\right\}.
$$

Pode-se ponderar por manager quality/horizon.

## Persistence

$$
Persistence_{m,e,t}=\min(QuartersHeld_{m,e,t},4)/4.
$$

## Sinal final

$$
\boxed{
Score_{e,t}=\sum_m
Conviction_{m,e,t}
\times Quality_{m,t}
\times Persistence_{m,e,t}
}
$$

Opcionalmente, imponha um mínimo de consenso independente.

## Estrutura causal

Uma posição pequena pode existir por:

- liquidity management;
- hedge;
- diversification;
- benchmark replication;
- residual exposure.

Uma posição excepcionalmente grande revela:

$$
\text{manager willingly spends scarce risk budget}
\Rightarrow
\text{revealed conviction}.
$$

Consensus reduz o risco de uma única tese idiossincrática estar errada. Persistence reduz o risco de a posição ter sido um trade temporário que morreu antes do disclosure.

## Restrição ETF-specific

Separe broad beta de ETFs que carregam uma view mais específica. Uma boa taxonomia simples:

- broad market;
- sector/industry;
- style/factor;
- thematic;
- international/country;
- fixed income/commodity/outros - possivelmente excluir no primeiro pass.

O sinal deve ser mais interpretável no subconjunto de ETFs de **view específica**.

## Backtest recomendado

Use como baseline contra os sinais 1-3. Se `StickyDemand` ou `DoubleDown` não baterem esse baseline simples, talvez a complexidade adicional não esteja comprando muita informação.

## Principal risco

Conviction pode representar hedging ou exposição macro, não alpha. O split por tipo de ETF é fundamental.

---

# 5. Transient-Holder Fragility × Market Shock

## Core idea

Esse sinal é diferente dos anteriores: ele não tenta prever retorno continuamente. Ele tenta identificar **onde um choque de mercado deve ser amplificado por uma base de holders de curto horizonte**.

A literatura de investor horizons mostra que, durante market turmoil, instituições 13F de horizonte curto vendem mais. Ações dominadas por esses holders sofrem quedas maiores e reversões subsequentes maiores.

A extensão ETF é direta: medir a fragilidade da base de holders do próprio ETF.

## Holder composition

Para ETF $e$:

$$
OwnerShare_{m,e,t}=\frac{Position_{m,e,t}}
{\sum_j Position_{j,e,t}}.
$$

Com $Churn_m$ já estimado:

$$
\boxed{
Fragility_{e,t}=\sum_m OwnerShare_{m,e,t}\cdot Churn_{m,t}
}
$$

Alta fragilidade significa que uma fração maior do ownership institucional está em mãos de gestores historicamente mais transient.

## Gatilho de mercado com Yahoo

Exemplo simples:

$$
Shock_{e,d}=-z\left(R^{res}_{e,d-20:d}\right).
$$

Ou um market-state trigger:

$$
\mathbf{1}[R_{SPY,20d}<-x\%].
$$

Sinal condicional:

$$
\boxed{
StressExposure_{e,d}=Fragility_{e,t}^{13F}\times Shock_{e,d}
}
$$

## Estrutura causal

$$
\text{negative market shock}
\rightarrow
\text{liquidity / deleveraging need}
\rightarrow
\text{short-horizon holders sell first}
\rightarrow
\text{price pressure exceeds fundamental news}
\rightarrow
\text{subsequent reversal}
$$

A previsão deve ser **assimétrica no tempo**.

### Fase 1 - durante o stress

High-fragility ETFs devem sofrer mais selling pressure.

### Fase 2 - depois do extreme selloff

Entre ETFs com quedas residuais parecidas, os de maior fragilidade devem ter reversão maior se parte da queda foi fire-sale pressure.

## Backtest recomendado

Não faça simplesmente `long high fragility`.

Teste eventos:

1. identifique market stress;
2. rankeie ETFs por fragility antes do evento;
3. teste drawdown relativo durante o shock;
4. depois teste reversal 5d/20d/60d;
5. compare high vs low fragility dentro de bins de beta, liquidity e prior momentum.

## Principal risco

O sinal pode ser esparso e dependente do regime. Isso não é um problema se a hipótese for apresentada como **conditional crowding/fire-sale factor**, e não como alpha diário universal.

---

# Como eu implementaria em 48 horas

## Prioridade 1 - construir a camada de manager horizon

Ela é reutilizada por quase todos os sinais:

1. reconstruct drifted portfolio;
2. compute churn;
3. smooth churn over 4 quarters;
4. classify managers em sticky / neutral / transient.

Esse componente, sozinho, já melhora a interpretação de qualquer fator 13F.

## Prioridade 2 - três sinais principais

Eu implementaria primeiro:

### A. StickyDemand

Mais simples e diretamente ligado ao problema do 13F lag.

### B. DoubleDown

Provavelmente a história causal mais forte e diferenciada.

### C. Conviction × Consensus × Persistence

Baseline robusto e muito defensável na literatura.

## Prioridade 3 - extensões

Depois:

- AbnormalBreadth;
- Fragility × Shock.

# Arquitetura de features

Uma tabela trimestral/event-driven por ETF:

| Feature | Fonte |
|---|---|
| institutional ownership | 13F |
| holder breadth | 13F |
| new holders / exits | 13F |
| conviction | 13F |
| manager churn | 13F + preços |
| manager persistence | 13F |
| consensus | 13F |
| doubling down | 13F + Yahoo |
| residual return | Yahoo |
| momentum | Yahoo |
| volatility | Yahoo |
| beta | Yahoo |
| dollar volume | Yahoo |
| holder fragility | 13F |

# Point-in-time discipline

Essa parte é obrigatória.

Para cada filing:

```text
quarter-end holdings exist economically
        |
        |  not observable yet
        v
manager files 13F at timestamp T
        |
        |  signal becomes public here
        v
update manager-level features
        |
        v
recompute ETF cross-section
        |
        v
trade at first feasible price after T
```

Nunca disponibilize simultaneamente todos os holdings do trimestre na deadline de 45 dias se os managers publicaram em datas distintas. Uma versão mais realista é um **13F nowcast event-driven**: cada novo filing atualiza o estado agregado.

# Como avaliar se realmente há alpha

Não olhe apenas Sharpe.

Para cada factor:

1. Spearman rank IC vs 1w/1m/3m forward returns;
2. monotonicity por quintiles/deciles;
3. top-minus-bottom return;
4. beta-neutral e market-neutral return;
5. turnover;
6. performance por regime;
7. persistence após custos;
8. incremental IC após controles simples de momentum, volatility, beta e liquidity.

## O teste mais importante: ablation causal

Cada sinal deve ter uma versão naive e uma versão que incorpora o mecanismo causal.

| Hipótese | Naive | Causal/estrutural |
|---|---|---|
| Institutional demand | raw net buying | **StickyDemand** |
| Contrarian | ETF caiu | **manager doubled down após queda** |
| Institutional popularity | raw breadth | **AbnormalBreadth** |
| Best ideas | large position | **Conviction × Consensus × Persistence** |
| Crowding risk | high ownership | **Transient-holder Fragility × Shock** |

Se a versão estrutural consistentemente domina a naive, a defesa econômica fica muito mais forte.

# Minha ordem final de implementação

## 1. Sticky Institutional ETF Demand - 9.5/10

Melhor combinação de implementação rápida, interpretação e solução explícita para o disclosure lag.

## 2. ETF Doubling Down - 9.0/10

Excelente mecanismo de revealed conviction e sinal bem diferente do crowding padrão.

## 3. Abnormal ETF Institutional Adoption - 8.5/10

Mais "quant research": residualiza mechanically expected ownership e procura latent preference.

## 4. Conviction × Consensus × Persistence - 8.0/10

Baseline obrigatório e fortemente conectado à literatura de 13F best ideas.

## 5. Transient-Holder Fragility × Shock - 8.5/10 em research quality

Provavelmente menos constante como alpha, mas talvez o mais causal como crowding/fire-sale signal.

# Combinação que eu mais gosto

Depois de testar os fatores separadamente, eu tentaria uma interação simples:

$$
\boxed{
MetaSignal_{e,t}=
StickyDemand_{e,t}
\times
\left(1+DoubleDownIntensity_{e,t}\right)
}
$$

Interpretando:

> O melhor long não é apenas o ETF que instituições compraram. É o ETF em que **gestores de horizonte longo aumentaram posição mesmo depois de underperformance**.

Essa combinação tenta maximizar simultaneamente:

- persistence da informação;
- revealed conviction;
- resistência ao disclosure lag.

Eu trataria isso como hipótese principal apenas depois de mostrar que os dois componentes funcionam separadamente para evitar overfitting narrativo.

# Referências principais

1. **Angelini, L., Iqbal, M., Jivraj, F. (2019). _Systematic 13F Hedge Fund Alpha_.** SSRN 3459526. O paper constrói conviction e consensus e enfatiza a seleção de managers com visões de horizonte mais longo. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3459526

2. **Rhinesmith, J. _Doubling Down_.** Evidência de que aumentos de exposição após underperformance carregam informação em portfolios de hedge funds. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2491636

3. **Khomyn, M. (2024). _The Value of ETF Liquidity_. Review of Financial Studies 37(10), 3092-3134.** ETFs mais líquidos que seguem o mesmo índice atraem investidores de horizonte mais curto. https://academic.oup.com/rfs/article/37/10/3092/7738093

4. **Kirk, M. (2025/2026). _Abnormal Institutional Ownership and Expected Returns_. Journal of Accounting, Auditing & Finance 41(2), 524-546.** Modela institutional ownership esperado por características e mostra informação incremental no componente anormal. https://journals.sagepub.com/doi/10.1177/0148558X251319189

5. **Cella, C., Ellul, A., Giannetti, M. (2013). _Investors' Horizons and the Amplification of Market Shocks_. Review of Financial Studies 26(7), 1607-1648.** Short-horizon 13F investors vendem mais durante turmoil; ativos dominados por eles sofrem price drops e reversals maiores. https://doi.org/10.1093/rfs/hht023

6. **Antón, M., Cohen, R. B., Polk, C. _Best Ideas_.** Evidência de que posições de maior convicção dos gestores contêm mais informação que o restante da carteira. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1364827

7. **U.S. SEC - Form 13F guidance.** Form 13F é trimestral e deve ser apresentado dentro de 45 dias do fim do trimestre. https://www.sec.gov/rules-regulations/staff-guidance/division-investment-management-frequently-asked-questions/frequently-asked-questions-about-form-13f

---

## Bottom line

Se o objetivo é achar um positioning factor de ETF que seja ao mesmo tempo **simples, causal e defensável**, eu começaria por:

$$
\boxed{StickyDemand}
$$

Depois testaria:

$$
\boxed{DoubleDown}
$$

como segundo sinal independente.

A tese geral é mais forte que "institutions bought it, therefore it goes up":

$$
\boxed{
13F
\rightarrow
Manager\ Horizon
\rightarrow
Nature\ of\ ETF\ Demand
\rightarrow
Persistence/Forced\ Selling
\rightarrow
Future\ Returns
}
$$

Esse é o eixo estrutural que eu usaria para organizar o research.
