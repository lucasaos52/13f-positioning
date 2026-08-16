# Sinais de posicionamento a partir de 13F-HR — revisão para construção de fator

**Propósito.** Catálogo de 31 sinais distintos extraíveis de Form 13F, com definição formal, hipótese econômica, direção esperada, evidência acadêmica e armadilhas de implementação. Escrito para servir de input a uma sessão de implementação (Claude Code) e de base para o memo de 3–5 páginas do take-home.

**Como ler.** Seção 1 delimita o espaço de sinais possível (o que o 13F fisicamente contém). Seção 2 dá a taxonomia. Seção 3 é o catálogo. Seção 4 é o ranking priorizado — se você só ler uma seção, leia essa. Seções 5–6 são disciplina point-in-time e engenharia de dados. Seção 7 são as alternativas descartadas (material direto para o memo). Seção 8 é a bibliografia.

---

## 1. O que o 13F é — e o que ele não é

Isto não é preâmbulo: **o espaço de fatores viáveis é inteiramente determinado por estas restrições.** Todo sinal do catálogo é uma tentativa de extrair informação apesar delas.

### 1.1 Escopo do formulário

| Dimensão | Realidade |
|---|---|
| Quem filia | Institutional investment managers com discricionariedade sobre ≥ US$ 100M em 13(f) securities |
| Frequência | Trimestral, snapshot de fim de trimestre |
| Prazo | 45 dias corridos após o fim do trimestre → 14/fev, 15/mai, 14/ago, 14/nov (aprox.) |
| Cobertura | Apenas *long* em 13(f) securities: ações listadas nos EUA, ADRs, ETFs, closed-end funds, alguns conversíveis e **opções listadas** |
| Não contém | Posições short, derivativos OTC, caixa, renda fixa, ações estrangeiras não-listadas nos EUA, cotas de fundos abertos, alavancagem |

### 1.2 As sete restrições que moldam qualquer fator

1. **Lag de 45 dias (no mínimo).** A posição é de 31/mar mas só é pública em 15/mai. Filers atrasados existem e são comuns. Qualquer backtest que use `report_date` como data de disponibilidade tem lookahead — este é o erro nº 1 e é exatamente o que o avaliador vai procurar.

2. **Snapshot, não fluxo.** Você vê o estoque no dia 31/mar, não a trajetória. Puckett & Yan (2011) mostram que boa parte da habilidade institucional está no *interim trading* — comprar e vender dentro do trimestre — que é estruturalmente invisível. Um fundo pode comprar 1/jan, vender 15/mar e o 13F não mostra nada. Isto impõe um teto na força de qualquer sinal 13F.

3. **Long-only, sem a perna short.** Não existe informação bearish direta, com uma exceção: a coluna PUT/CALL da information table (ver sinal #25). A Rule 13f-2 / Form SHO — que traria posições short agregadas — foi adiada para fevereiro de 2028 após o remand do Fifth Circuit (ordem da SEC de 3/dez/2025). **Não conte com ela.**

4. **De minimis.** Posições abaixo de 10.000 ações *e* US$ 200.000 podem ser omitidas. Isso trunca sistematicamente a cauda de small caps e enviesa qualquer medida de *breadth* nesse segmento.

5. **Confidential treatment.** Posições podem ser omitidas do filing público mediante pedido à SEC e reveladas depois, via emenda. Isso cria (a) buracos silenciosos no painel e (b) um sinal de evento de alto valor (#21).

6. **Emendas de dois tipos, com semântica oposta.** *Restatement* substitui o filing inteiro; *"adds new holdings entries"* apenas acrescenta linhas. Tratar as duas igualmente corrompe o painel. Se um filing está ao mesmo tempo errado e incompleto, o gestor precisa mandar duas emendas separadas.

7. **Agregação de entidade ambígua.** Uma família de gestão pode filiar por múltiplos CIKs; um sub-adviser pode filiar 13F-NT ("minhas posições estão reportadas por outro"); e há *combination reports*. Contagem ingênua de "quantos filers detêm a ação" dupla-conta e infla breadth de forma não-estacionária.

### 1.3 Consequência para o desenho do fator

Três implicações que devem aparecer explicitamente no memo:

- **O sinal é de baixa frequência e alta latência.** Isso empurra para horizontes de 1–12 meses, não dias. Custo de transação é secundário; timing luck e sobreposição de carteiras é primário.
- **A informação está no *corte transversal entre gestores*, não no agregado.** O agregado institucional é ~80% do float de large caps — é o mercado. Qualquer sinal precisa de uma partição (hedge funds vs. quasi-indexers, alta vs. baixa convicção, alto vs. baixo alpha passado).
- **Preço contamina tudo.** Peso de carteira sobe quando a ação sobe, sem nenhum trade. Sem correção de *drift*, metade dos "fatores 13F" são momentum disfarçado. Ver §5.3 — é o segundo erro mais comum depois do lookahead.

---

## 2. Taxonomia

Seis famílias, por *tipo de informação extraída*:

| Família | Pergunta que responde | Sinais |
|---|---|---|
| **A. Breadth / margem extensiva** | Quantos donos distintos? | 1–5 |
| **B. Convicção / margem intensiva** | Quão grande é a aposta, relativa à alternativa? | 6–10 |
| **C. Crowding, herding e fragilidade** | Quantos estão no mesmo lado, e quão apertada é a saída? | 11–17 |
| **D. Seleção de gestor (smart money)** | *Quem* está comprando? | 18–24 |
| **E. Demanda e microestrutura de posicionamento** | Qual o desequilíbrio de demanda vs. a oferta disponível? | 25–28 |
| **F. Meta-sinais (comportamento do filing)** | O que o *ato de filiar* revela? | 29–31 |

As famílias A e B têm sinal esperado **positivo** (mais/maior posicionamento → retorno futuro maior). A família C é a mais interessante porque o sinal **inverte com o horizonte**: crowding prevê retorno positivo em 1 trimestre e negativo em 4–8. Ignorar essa inversão é o erro conceitual mais comum na literatura aplicada de 13F.

---

## 3. Catálogo de sinais

Notação usada em todo o catálogo:

- `m` = gestor (filer), `i` = ação, `t` = trimestre de referência (report date), `τ` = data de disponibilidade (filing date)
- `S_{m,i,t}` = ações detidas, ajustadas por split
- `V_{m,i,t}` = valor de mercado da posição
- `w_{m,i,t} = V_{m,i,t} / Σ_j V_{m,j,t}` = peso na carteira do gestor
- `w^mkt_{i,t}` = peso da ação no universo por market cap
- `N_t` = número de filers ativos no trimestre t
- `SO_{i,t}` = shares outstanding

---

### FAMÍLIA A — Breadth / margem extensiva

---

#### #1 — ΔBREADTH (mudança na amplitude de propriedade) ★★★

**Definição**
```
Breadth_{i,t} = (# gestores com S_{m,i,t} > 0) / N_t
ΔBreadth_{i,t} = Breadth_{i,t} − Breadth_{i,t−1}
```
A normalização por `N_t` é obrigatória: o número de filers 13F cresceu de ~1.000 para ~5.000+ ao longo das décadas, e sem normalizar você mede crescimento da indústria, não posicionamento.

**Hipótese.** Com restrição de venda a descoberto e divergência de opinião (Miller 1977), investidores pessimistas ficam fora do mercado em vez de vender short. Breadth baixa sinaliza que a restrição está apertada → o preço reflete só os otimistas → sobrevalorização. Quedas em breadth prevêem retornos baixos.

**Direção.** Positiva.

**Evidência.** Chen, Hong & Stein (2002, JFE): decil inferior de ΔBreadth *underperforma* o decil superior em ~6,4% nos 12 meses seguintes; ~5,0% após ajuste por size, book-to-market e momentum. Usaram holdings de fundos mútuos 1979–1998.

**Armadilhas.**
- CHS usaram fundos mútuos ativos. O universo 13F inclui quasi-indexers (BlackRock, Vanguard, State Street), custodiantes e bancos, cuja entrada/saída não carrega opinião. **Restrinja a subamostra ativa** antes de computar — é onde o sinal está (ver #5).
- Vulnerável ao truncamento de de minimis em small caps.
- Choi, Jin & Yan (2013) mostram que em dados de mercado inteiro (Xangai) a relação inverte para investidores de varejo, mas se mantém — e é mais forte — para institucionais. Reforça restringir a subamostra certa.

---

#### #2 — INITIATIONS vs. EXITS (assimetria de entrada e saída) ★★★

**Definição**
```
IN_{i,t}  = (# gestores com S_{m,i,t} > 0 e S_{m,i,t−1} = 0) / N_t
OUT_{i,t} = (# gestores com S_{m,i,t} = 0 e S_{m,i,t−1} > 0) / N_t
NetInit_{i,t} = IN_{i,t} − OUT_{i,t}
```
Requer que o gestor exista nos dois trimestres (senão entradas de filers novos poluem `IN`).

**Hipótese.** Abrir uma posição do zero exige mais convicção do que aumentar uma existente — há custo de due diligence, custo de comitê, custo reputacional. Zerar uma posição é mais informativo que aparar. As duas pernas não são simétricas: saídas podem ser forçadas por resgates, então `OUT` é mais ruidoso que `IN`.

**Direção.** `IN` positiva (forte); `OUT` negativa (fraca). Teste as pernas separadamente — se elas têm força igual, é sinal de que você está capturando fluxo, não informação.

**Evidência.** São as variáveis IN/OUT do próprio Chen, Hong & Stein (2002).

**Armadilhas.** Uma "saída" pode ser (a) venda deliberada, (b) resgate forçado, (c) queda abaixo do de minimis, (d) pedido de confidential treatment concedido, (e) o gestor mudou de CIK. Trate (c)–(e) explicitamente ou você vai gerar saídas fantasma.

---

#### #3 — ΔIO (variação na propriedade institucional agregada) ★★

**Definição**
```
IO_{i,t} = Σ_m S_{m,i,t} / SO_{i,t}
ΔIO_{i,t} = IO_{i,t} − IO_{i,t−1}
```

**Hipótese.** Margem intensiva agregada: demanda institucional líquida como pressão de preço e/ou como proxy de informação.

**Direção.** Positiva em horizonte curto, mas **contestada** e fortemente condicional ao tipo de instituição.

**Evidência.** Gompers & Metrick (2001, QJE) documentam relação positiva entre IO e retornos. Yan & Zhang (2009, RFS) mostram que essa relação é inteiramente atribuível a instituições de **horizonte curto** — o trading delas prevê retornos e surpresas de lucro; o de instituições de horizonte longo não prevê nada.

**Armadilhas.**
- `SO` deve ser point-in-time (o do fim do trimestre t), não o atual.
- Muito correlacionado com size e com momentum. Neutralize os dois ou o fator não é novo.
- **Nunca use sem partição por tipo de gestor** — é a lição direta de Yan & Zhang.

---

#### #4 — NÍVEL DE IO / IO RESIDUAL (como variável de condicionamento) ★★

**Definição**
```
Residual_IO_i = resíduo de:  logit(IO_i) ~ log(MktCap_i) + log(MktCap_i)²
```

**Hipótese.** IO baixa é proxy de restrição efetiva de venda a descoberto (pouca oferta de ações para empréstimo). Anomalias de sobrevalorização são muito mais fortes onde arbitradores não conseguem operar.

**Direção.** Não é um sinal *standalone* — é um **interagente**. Fatores de posicionamento devem ser mais fortes na perna short em ações de IO residual baixa.

**Evidência.** Nagel (2005, JFE): a rentabilidade de anomalias cross-section se concentra em ações de baixa propriedade institucional.

**Armadilhas.** IO e size são quase colineares — daí o resíduo com termo quadrático. Sem isso você está apenas fazendo um fator de tamanho.

---

#### #5 — BREADTH RESTRITA A SUBAMOSTRA INFORMADA ★★★

**Definição.** Idênticos a #1/#2, mas com `m ∈ M*` onde `M*` é um subconjunto de gestores selecionado ex-ante por: (a) classificação como hedge fund, (b) churn ratio alto (#20), (c) alpha passado no decil superior (#19), (d) tamanho pequeno.

**Hipótese.** Razão sinal-ruído. Se 4.000 dos 5.000 filers são veículos passivos ou quase-passivos, incluí-los adiciona variância sem adicionar informação — e pior, adiciona um componente mecânico de rebalanceamento de índice.

**Direção.** Positiva, e **materialmente mais forte** que #1.

**Evidência.** Antón, Cohen & Polk (2021) documentam que as *best ideas* de fundos **pequenos** superam as de fundos grandes em ~15% ao ano no universo de hedge funds — uma diferença enorme, que argumenta por ponderar por 1/AUM ou restringir a filers menores.

**Armadilhas.** A seleção de `M*` precisa ser point-in-time. Selecionar hedge funds por uma lista atual é lookahead (sobrevivência). Ver §5.4.

---

### FAMÍLIA B — Convicção / margem intensiva

---

#### #6 — BEST IDEAS / PESO DE CONVICÇÃO ★★★

**Definição.** Para cada gestor, mede o *tilt* relativo a um benchmark neutro:
```
tilt_{m,i,t} = w_{m,i,t} − w^mkt_{i,t}          (tilt aditivo)
   ou         w_{m,i,t} / w^mkt_{i,t}            (tilt multiplicativo)

BestIdea_{m,t} = argmax_i tilt_{m,i,t}
Signal_i = Σ_m 1{i é top-k tilt de m}  /  N_t
```

**Hipótese.** A carteira de um gestor não é uma expressão pura de crença: contém posições de diversificação, de tracking error, de restrição de mandato. A crença real está concentrada nas maiores apostas ativas. Extrair só essas remove o ruído estrutural da indústria.

**Direção.** Positiva.

**Evidência.** Antón, Cohen & Polk (2021): as *best ideas* de gestores ativos de fundos mútuos e de hedge funds superam o mercado — e as demais posições dos mesmos gestores — em ~2,8% a 4,5% ao ano, dependendo do benchmark. As demais posições em geral não superam nada. Versão original: Cohen, Polk & Silli (2010).

**Armadilhas.**
- Precisa de um benchmark por gestor. `w^mkt` global é grosseiro; o ideal é um benchmark de estilo, mas o 13F não diz o mandato. Alternativa defensável: usar o peso médio da ação entre todos os filers como benchmark implícito.
- Exclua gestores com < 20 posições (a medida vira degenerada).
- Correlação com size: tilts positivos grandes tendem a ser small caps por construção.

---

#### #7 — ACTIVE WEIGHT AGREGADO (overweight institucional) ★★★

**Definição**
```
AW_{i,t} = Σ_m a_{m,t} · (w_{m,i,t} − w^mkt_{i,t}),   a_{m,t} = AUM_m / Σ_n AUM_n
```

**Hipótese.** É a versão agregada e ponderada por capital de #6: quanto de capital ativo está posicionado acima do neutro nesta ação. É também a aproximação *tratável* da demanda latente de Koijen–Yogo (#26) — mesma intuição econômica, sem o sistema de demanda estrutural.

**Direção.** Positiva em horizonte curto; ver #14 para a inversão em horizonte longo.

**Evidência.** Ligada conceitualmente a Cremers & Petajisto (2009) sobre *active share* no nível do fundo, e ao arcabouço de demanda de Koijen & Yogo (2019, JPE).

**Armadilhas.** `a_m` deve ser o AUM 13F (soma dos valores reportados), não o AUM da empresa. Concentra desproporcionalmente nos maiores filers — considere `sqrt(AUM)` ou cap no peso máximo.

---

#### #8 — CONCENTRAÇÃO DA CARTEIRA DO GESTOR (filtro de qualidade) ★★

**Definição**
```
HHI_{m,t} = Σ_i w_{m,i,t}²        (ou: peso das top-10, ou # efetivo de posições = 1/HHI)
```
Não é sinal de ação — é atributo de gestor, usado para construir `M*` (#5) ou como peso em #18.

**Hipótese.** Concentração revela convicção e, sob a hipótese de habilidade limitada e escassa, também revela que o gestor está disposto a arcar com tracking error para expressá-la.

**Evidência.** Kacperczyk, Sialm & Zheng (2005, JF) para concentração setorial em fundos mútuos; Baks, Busse & Green sobre gestores focados.

**Ressalva importante.** A literatura de *best ideas* é frequentemente mal interpretada: mostra que as *maiores apostas* superam, **não** que carteiras concentradas geram alpha maior líquido. Não confunda os dois no memo — é exatamente o tipo de erro que o entrevistador vai testar.

---

#### #9 — ΔACTIVE WEIGHT COM CORREÇÃO DE DRIFT ★★★★

**Este é provavelmente o sinal com melhor relação valor/esforço do catálogo.**

**Definição.** Separe a mudança de peso em componente mecânico (preço) e componente deliberado (trade):
```
# peso que existiria sem nenhum trade
w_drift_{m,i,t} = w_{m,i,t−1}(1 + r_{i,t}) / Σ_j w_{m,j,t−1}(1 + r_{j,t})

# componente ativo
Δw_active_{m,i,t} = w_{m,i,t} − w_drift_{m,i,t}

Signal_i = Σ_m a_{m,t} · Δw_active_{m,i,t}
```
Equivalente e mais robusto no espaço de ações: `ΔS_{m,i,t} = S_{m,i,t} − S_{m,i,t−1}` com ajuste de split, escalado pelo tamanho do gestor.

**Hipótese.** Só o componente ativo é decisão. O componente de drift é aritmética de preço.

**Direção.** Positiva.

**Por que importa tanto.** Sem essa decomposição, um fator construído sobre Δpeso tem correlação fortemente positiva com o retorno do trimestre — ou seja, você construiu momentum de 3 meses e chamou de fator de posicionamento. Isso aparece como "alpha" no backtest e desaparece assim que você controla por MOM. **Fazer essa correção e mostrá-la no memo é um diferencial direto de avaliação.**

**Armadilhas.** `r_{i,t}` precisa ser retorno total ajustado por proventos e splits, medido entre os *report dates*, não entre filing dates.

---

#### #10 — HHI DE PROPRIEDADE (concentração de donos na ação) ★★

**Definição**
```
s_{m,i,t} = S_{m,i,t} / Σ_n S_{n,i,t}
OwnHHI_{i,t} = Σ_m s²_{m,i,t}
```

**Hipótese.** Duas leituras opostas, e é isso que o torna interessante: (a) propriedade concentrada = presença de blockholder monitorador = governança melhor; (b) propriedade concentrada = fragilidade, porque a saída de um único holder move o preço.

**Direção.** Ambígua como sinal direto. Use como **variável de risco / interação** — o crowding (#11) deve ser muito mais perigoso quando `OwnHHI` é alto.

**Evidência.** Conecta a Greenwood & Thesmar (2011) sobre fragilidade de preço (#15).

---

### FAMÍLIA C — Crowding, herding e fragilidade

---

#### #11 — CROWDEDNESS EM DIAS DE VOLUME (Days-ADV) ★★★★

**Definição**
```
Crowd_{i,t} = ( Σ_{m ∈ HF} S_{m,i,t} ) / ADV_{i,t}
```
onde `ADV` é o volume médio diário em ações no trimestre. Interpretação direta: **quantos dias de volume o conjunto de hedge funds levaria para sair.**

**Hipótese.** Crowding não é sobre quantos donos, é sobre a razão entre posição agregada e liquidez de saída. Uma posição detida por 50 fundos numa large cap líquida não é crowded; a mesma posição numa small cap é uma armadilha de liquidez. Isso captura risco de cauda e de desalavancagem forçada.

**Direção.** Positiva no horizonte de 1 trimestre (pressão de compra continua), **negativa em horizonte longo e severamente negativa em regimes de estresse.**

**Evidência.** Brown, Howard & Lundblad (2022, RFS): constroem exatamente essa medida a partir de holdings 13F de hedge funds; o spread de retorno entre carteiras de alto e baixo crowding é grande e distinto de fatores tradicionais; exposição a crowdedness explica drawdowns de cauda em períodos de estresse da indústria. Cerca de 26% do universo de hedge funds tem carga estatisticamente significativa nesse fator.

**Armadilhas.**
- Exige dados de volume (CRSP ou equivalente) além do 13F. É a única dependência externa pesada da Tier 1.
- Requer identificar hedge funds entre os filers — ver #20 para a versão point-in-time.
- Fortemente correlacionado com o inverso do size. Neutralize.

---

#### #12 — HERDING LSV (medida clássica) ★★

**Definição**
```
p_{i,t} = B_{i,t} / (B_{i,t} + S_{i,t})        # fração de gestores compradores
HM_{i,t} = | p_{i,t} − E[p_t] |  −  AF_{i,t}
AF_{i,t} = E[ | p_{i,t} − E[p_t] | ]           # fator de ajuste sob binomial
```
Decomponha em `BHM` (herding de compra, quando `p > E[p]`) e `SHM` (herding de venda).

**Hipótese.** Se gestores decidem independentemente, `p_i` deve ter dispersão binomial em torno da média do trimestre. Excesso de dispersão = correlação nas decisões = herding.

**Direção.** `BHM` positiva em horizonte curto; `SHM` negativa mas com reversão.

**Evidência.** Lakonishok, Shleifer & Vishny (1992, JFE) — medida original. Wermers (1999, JF) — herding em fundos mútuos e impacto em preços.

**Armadilhas.** `AF` depende do número de gestores ativos na ação; a medida é enviesada para cima em ações com poucos holders. Corrija ou exclua ações com < 10 holders.

---

#### #13 — HERDING DE SIAS (correlação intertemporal) ★★

**Definição.** Correlação cross-sectional entre `Δ(fração de instituições compradoras)` em trimestres adjacentes, decomposta em (a) instituições seguindo os próprios trades passados e (b) instituições seguindo os trades de *outras*.

**Hipótese.** A decomposição é o valor: só (b) é herding genuíno. (a) é apenas execução parcelada de uma decisão única — um fundo grande construindo posição ao longo de dois trimestres.

**Direção.** A componente (b) prevê continuação curta e reversão longa.

**Evidência.** Sias (2004, RFS).

**Armadilhas.** Mais caro de implementar que #12 e o incremento marginal sobre #12 + #14 é pequeno. Baixa prioridade para 48h.

---

#### #14 — PERSISTÊNCIA MULTI-TRIMESTRE (o contra-sinal) ★★★★

**Definição**
```
PERSIST_{i,t} = # de trimestres consecutivos, olhando k=2..8 para trás,
                em que  Signal_i  teve o mesmo sinal
```
Aplique sobre a demanda ativa (#9) ou sobre a fração de compradores (#12).

**Hipótese.** Herding de um único trimestre pode ser agregação de informação. Herding *persistente por vários trimestres* é comportamento de carreira/reputação — gestores imitando gestores — e empurra o preço para além do fundamental. O que sobe por conformismo volta.

**Direção.** **NEGATIVA em horizonte longo.** Ações persistentemente vendidas superam ações persistentemente compradas.

**Evidência.** Dasgupta, Prat & Verardo (2011, JF): trading institucional persistente prevê negativamente retornos de longo prazo; a reversão é robusta e não explicada pelos controles usuais. Contrasta diretamente com a literatura que encontra previsão positiva no horizonte de um trimestre.

**Por que este sinal é estrategicamente valioso no take-home.** O critério de avaliação diz explicitamente *"Did you consider alternatives?"*. Ter #9 (positivo, curto) e #14 (negativo, longo) no mesmo pipeline, com a curva de decaimento de alpha por horizonte plotada, demonstra que você entendeu que a direção do sinal é uma função do horizonte, não uma constante. É a coisa mais defensável que você pode mostrar numa sessão técnica de 60 minutos.

---

#### #15 — FRAGILIDADE DE PREÇO (G de Greenwood–Thesmar) ★★

**Definição**
```
G_{i,t} = (1/θ²_{i,t}) [ Σ_m θ²_{m,i,t} σ²_m  +  Σ_{m≠n} θ_{m,i,t} θ_{n,i,t} ρ_{mn} ]
```
onde `θ_{m,i}` é o valor detido por m em i, `θ_i = Σ_m θ_{m,i}`, `σ²_m` é a volatilidade de fluxo do gestor m e `ρ_{mn}` a correlação de fluxos entre gestores.

**Hipótese.** Uma ação é frágil quando é detida por poucos donos, ou por donos cujos fluxos são voláteis, ou por donos cujos fluxos são correlacionados entre si. Fragilidade prevê **volatilidade futura**, não retorno.

**Direção.** Overlay de risco. Use para (a) excluir da perna long as ações mais frágeis, (b) explicar drawdowns do fator no memo.

**Evidência.** Greenwood & Thesmar (2011, JFE).

**Armadilhas.** `σ_m` e `ρ_{mn}` exigem série histórica de fluxo por gestor. Com 13F puro você só tem ΔAUM, que mistura fluxo e retorno — aproxime como `ΔAUM_m − retorno da carteira replicada de m`.

---

#### #16 — CROWDING POR SIMILARIDADE DE CARTEIRA (rede de co-holdings) ★★

**Definição**
```
sim_{m,n,t} = cos( w_{m,·,t} , w_{n,·,t} )
NetCrowd_{i,t} = Σ_{m,n : m≠n} sim_{m,n,t} · 1{i ∈ m} · 1{i ∈ n}
```
Ou: componentes principais da matriz gestor × ação, e crowding = carga da ação no primeiro PC de posicionamento ativo.

**Hipótese.** Crowding real não é "muitos donos", é "muitos donos *parecidos*". Dez fundos com carteiras quase idênticas responderão ao mesmo choque da mesma forma; dez fundos descorrelacionados, não.

**Direção.** Negativa em horizonte longo; forte preditor de comovimento.

**Evidência.** Antón & Polk (2014, JF) sobre *connected stocks*: propriedade comum gera comovimento em excesso e previsibilidade de retorno explorável.

**Armadilhas.** Matriz esparsa e grande. Faça sobre pesos ativos, não pesos brutos, senão a similaridade é dominada pelo fato trivial de que todo mundo tem as mesmas mega caps.

---

#### #17 — PRESSÃO DE FLUXO ESPERADA (FIT / flow-induced trading) ★★

**Definição**
```
Pressure_{i,t} = Σ_m ( flow_{m,t} · w_{m,i,t−1} ) / (dollar volume de i)
```

**Hipótese.** Quando um fundo recebe resgates, ele vende suas posições proporcionalmente, independente de valor. Isso é uma perturbação de demanda **não-informacional e previsível** — o caso mais limpo de causalidade preço-fluxo em finanças empíricas.

**Direção.** Positiva no trimestre seguinte (continuação da pressão), com reversão em 2–4 trimestres.

**Evidência.** Coval & Stafford (2007, JFE) sobre fire sales; Lou (2012, RFS) sobre previsibilidade baseada em fluxo.

**Armadilha decisiva.** **O 13F não tem fluxo.** Você precisa de N-PORT / CRSP Mutual Fund para separar fluxo de retorno. Com 13F puro só existe a aproximação de #15. Documente isso como limitação explícita — é uma boa resposta para "o que você construiria a seguir".

---

### FAMÍLIA D — Seleção de gestor (smart money)

---

#### #18 — CONSENSO PONDERADO POR HABILIDADE ★★★

**Definição**
```
Signal_i = Σ_m ŵ_m · ( w_{m,i,t} − w^mkt_{i,t} )
ŵ_m = f( alpha passado de m ),  com shrinkage bayesiano
```

**Hipótese.** Nem todo filer merece o mesmo voto. Agregar holdings ponderando pela habilidade estimada domina a média simples — que é, por construção, o mercado.

**Direção.** Positiva.

**Evidência.** Wermers, Yao & Zhao (2012, RFS) propõem uma agregação eficiente de holdings de fundos ("generalized inverse alpha") que supera medidas ingênuas de consenso.

**Armadilhas.** Toda a dificuldade está em estimar `alpha_m` sem lookahead. Ver #19.

---

#### #19 — ALPHA HISTÓRICO DO FILER (carteira-papel replicada) ★★★

**Definição.** Para cada gestor, construa a carteira replicada a partir dos 13F (peso `w_{m,i,t}` mantido do filing date até o próximo), calcule retorno mensal, e estime alpha rolante contra FF5 + MOM sobre janela de 12–20 trimestres. Selecione o decil superior.

**Hipótese.** Habilidade em stock picking persiste o suficiente, no horizonte de anos, para servir de filtro.

**Direção.** Positiva, mas modesta — e este é um ponto honesto para o memo.

**Evidência mista, que é o ponto.** Griffin & Xu (2009, RFS) examinam holdings de ~1.500 hedge funds via 13F e encontram evidência **limitada** de habilidade superior em stock picking, uma vez controlados estilo e características. Contraste com Antón, Cohen & Polk (2021), que encontram alpha forte quando se olha só as *maiores* apostas. A reconciliação: habilidade existe mas é diluída pela carteira inteira. Isso argumenta por combinar #19 com #6, não por usar #19 sozinho.

**Armadilhas point-in-time (críticas).**
- O alpha deve ser estimado só com dados disponíveis até a data de formação.
- A carteira replicada tem que usar filing dates, não report dates — senão você estima alpha com lookahead e depois seleciona gestores com base nele. Duplo viés.
- Viés de sobrevivência: gestores que quebraram somem do EDGAR. Construa o universo de filers ativos *naquele trimestre*, a partir dos índices do EDGAR, nunca a partir de uma lista atual.

---

#### #20 — PARTIÇÃO POR HORIZONTE: CHURN RATIO / CLASSIFICAÇÃO BUSHEE ★★★

**Definição (churn ratio, versão implementável)**
```
CR_{m,t} = Σ_i | S_{m,i,t}·P_{i,t} − S_{m,i,t−1}·P_{i,t−1} |  /  ((V_{m,t} + V_{m,t−1})/2)
```
Média sobre 4 trimestres para suavizar. Classifique gestores em tercis: curto / médio / longo horizonte.

**Versão canônica.** Bushee (1998, 2001) classifica institucionais em **transient**, **dedicated** e **quasi-indexer** via análise fatorial + cluster sobre turnover, concentração e estabilidade de participação.

**Hipótese.** Instituições de horizonte curto negociam com base em informação e a exploram rapidamente; quasi-indexers rebalanceiam mecanicamente. Misturar as duas na mesma medida de consenso destrói o sinal.

**Direção.** Aplique **todos** os outros sinais dentro de cada partição. O spread entre a versão "short-horizon" e a "quasi-indexer" do mesmo sinal é, em si, um teste de que você está capturando informação e não fluxo passivo.

**Evidência.** Yan & Zhang (2009, RFS): o trading de instituições de horizonte curto prevê retornos futuros e surpresas de lucro; o de horizonte longo não prevê nem uma coisa nem outra. Bushee (1998) para a taxonomia.

**Nota prática.** Esta é a maior alavanca de qualidade do catálogo por unidade de esforço: é uma agregação sobre dados que você já tem, sem fonte externa, e transforma quase todo sinal em uma versão mais limpa de si mesmo.

---

#### #21 — REVELAÇÃO DE POSIÇÃO CONFIDENCIAL (CT unwind) ★★★

**Definição.** Evento. Detecte emendas `13F-HR/A` que (a) sejam do tipo *"adds new holdings entries"* e (b) tragam na capa a legenda de confidential treatment (o texto padrão referenciando o filing original e a data em que o CT foi negado, expirou ou foi retirado). As linhas dessas emendas são as posições que estavam escondidas.

**Hipótese.** Um gestor só arca com o custo administrativo de pedir sigilo à SEC quando acredita que a divulgação prejudicaria a construção da posição — ou seja, quando acredita ter informação privada de valor material. É uma revelação de preferência, não uma declaração.

**Direção.** Positiva, e forte.

**Evidência.** Agarwal, Jiang, Tang & Yang (2013, JF): posições confidenciais exibem desempenho superior por até doze meses; fundos que buscam sigilo com mais frequência são os que gerem carteiras grandes e arriscadas com estratégias não convencionais; as ações escondidas concentram-se desproporcionalmente em situações sensíveis a informação. A evidência aponta para informação privada, e não motivos administrativos, como razão dominante do sigilo. Ver também Aragon, Hertzel & Shi (2013, JFQA).

**Por que incluir mesmo sendo raro.** O enunciado do take-home lista *"treatment of confidential treatment requests"* como critério explícito de avaliação de engenharia de dados. Implementar #21 mata dois coelhos: é um sinal com alpha real documentado **e** é a prova de que você tratou CT corretamente. Mesmo que o resultado do backtest seja ruidoso por baixa contagem de eventos, a existência do handler vale mais que o t-stat.

---

#### #22 — RETURN GAP DE RESTATEMENT (emendas retificadoras) ★★

**Definição.** Compare holdings originais vs. restated em emendas `13F-HR/A` do tipo *restatement*. Meça o retorno das posições corrigidas entre o report date e a data da emenda.

**Hipótese.** Se o padrão de correções fosse erro operacional aleatório, o retorno das posições corrigidas seria zero em média. Não é. Alguns gestores reportam mal deliberadamente para esconder intenção de trade, e retificam depois.

**Direção.** Positiva; funciona também como métrica de qualidade do gestor.

**Evidência.** Chen et al., *Do Hedge Funds Strategically Misreport Their Holdings? Evidence from 13F Restatements* (Management Science, 2025): restatements são tão comuns quanto filings confidenciais mas afetam três vezes mais ações; holdings retificados estão associados a retornos anormais significativos; um *restatement return gap* positivo prevê desempenho futuro superior do fundo.

**Armadilhas.** Exige guardar o histórico completo de versões de cada filing (painel bitemporal). Se você já vai fazer isso para disciplina point-in-time (§5.2), o custo marginal deste sinal é quase zero — motivo pelo qual ele vale a pena apesar de nicho.

---

#### #23 — TIMING DO FILING (atraso e clustering) ★

**Definição.** `delay_{m,t} = filing_date − report_date − 45`. Filers que consistentemente entregam no último dia ou depois vs. os que entregam cedo.

**Hipótese.** Divulgar cedo é custoso se você ainda está construindo posição. Atraso sistemático é um sinal fraco de que o gestor tem algo a proteger.

**Direção.** Fraca e não estabelecida. Trate como exploratório.

**Evidência.** Christoffersen, Danesh & Musto, *Why Do Institutions Delay Reporting Their Shareholdings? Evidence from Form 13F*.

**Uso principal.** Independente do valor preditivo, você **precisa** calcular `delay` de qualquer forma para o painel point-in-time. Plotar a distribuição de `delay` no memo — mostrando a cauda de filers que entregam com 60, 90, 200 dias — é a demonstração mais direta de que o seu backtester trata lag corretamente.

---

#### #24 — CLONE DE 13F (replicação ingênua) — BASELINE ★

**Definição.** Carteira das maiores posições de um conjunto de gestores célebres, rebalanceada nos filing dates.

**Direção.** Positiva mas fraca, e é isso que o torna útil.

**Evidência.** Frank, Poterba, Shackelford & Shoven (2004, JLE) sobre *copycat funds*: replicar holdings divulgados captura parte do retorno, mas o atraso de divulgação corrói boa parte da vantagem.

**Uso.** Não é o seu fator. É o **benchmark ingênuo que o seu fator precisa superar**. Um memo que mostra "meu fator bate o clone ingênuo em X" é muito mais persuasivo que um que só mostra alpha vs. o S&P.

---

### FAMÍLIA E — Demanda e microestrutura de posicionamento

---

#### #25 — POSIÇÕES EM OPÇÕES REPORTADAS NO 13F ★★

**Definição.** A information table tem a coluna `putCall`. Filtre `putCall = "Put"` e agregue por ação:
```
PutRatio_{i,t} = Σ_m V^put_{m,i,t} / Σ_m V^{ações}_{m,i,t}
```

**Hipótese.** É a **única expressão bearish visível** no 13F. Um gestor que reporta puts está declarando visão negativa (ou hedge — e distinguir os dois é a dificuldade).

**Direção.** Negativa.

**Evidência.** Aragon & Martin (2012, JFE) analisam uso de derivativos por hedge funds a partir de 13F e encontram conteúdo informacional nas posições de opções.

**Armadilhas sérias.**
- Dados esparsos e reportagem inconsistente entre filers.
- Bases de dados comerciais padrão (Thomson s34) **historicamente omitem** as linhas de opções — motivo pelo qual esse sinal é subexplorado e motivo pelo qual você deve ir direto ao EDGAR. Isso é, por si só, um argumento de diferenciação para o memo.
- O valor reportado pode ser notional ou market value dependendo do filer. Sanitize agressivamente.
- **Nunca some linhas de opções às linhas de ações.** É o bug de parsing mais comum em pipelines 13F.

---

#### #26 — DEMANDA LATENTE (sistema de demanda Koijen–Yogo) ★★★ (mas caro)

**Definição.** Estime um sistema de demanda baseado em características: para cada investidor, regrida o peso de portfólio em características observáveis (log market equity, book-to-market, profitability, investment, beta) com variável instrumental para lidar com a endogeneidade entre demanda e preço. O resíduo é a **demanda latente** — a parte da posição não explicada por características.

```
w_{m,i,t} / w_{m,0,t} = exp( β_{0,m} log(me_i) + β'_m x_i ) · ε_{m,i,t}
Signal_i = Σ_m (AUM_m) · log ε_{m,i,t}
```

**Hipótese.** Se um gestor está sobrepesado numa ação além do que suas preferências por características explicam, isso é informação específica da ação — exatamente o que você quer isolar. Além disso, o arcabouço permite estimar **elasticidade de demanda**, e portanto traduzir um desequilíbrio de demanda em impacto de preço esperado.

**Direção.** Demanda latente agregada positiva → pressão de preço → retorno positivo de curto prazo, com reversão.

**Evidência.** Koijen & Yogo (2019, JPE) — o arcabouço, estimado sobre holdings 13(f) casados com CRSP por CUSIP. Koijen, Richmond & Yogo (2024, RES) mostram que investidores com maior demanda latente têm maior impacto sobre preços de ações. Gabaix & Koijen (2021) sobre mercados inelásticos dá a motivação macro.

**Veredito para 48 horas.** **Não implemente.** É o candidato número um para a lista "três coisas que eu construiria a seguir" do memo — bem justificado, mostra que você conhece a fronteira, e é honesto sobre escopo. Use #7 como aproximação tratável agora.

---

#### #27 — CHOQUE DE DEMANDA ESCALADO POR LIQUIDEZ ★★★

**Definição**
```
DemandShock_{i,t} = ( Σ_m ΔS_active_{m,i,t} · P_{i,t} ) / (dollar volume do trimestre)
```
A versão simples e defensável de #26: quanto de compra líquida institucional ativa ocorreu, medida em unidades da liquidez disponível para absorvê-la.

**Hipótese.** Mercados de ações são inelásticos. O que move o preço não é o valor absoluto comprado, mas a razão entre esse valor e a capacidade do mercado de absorver.

**Direção.** Positiva em 1–2 trimestres, com reversão parcial depois.

**Evidência.** Gabaix & Koijen (2021) sobre a hipótese de mercados inelásticos; mesma lógica de escalonamento de Brown, Howard & Lundblad (2022).

**Nota.** Este e #11 são a mesma ideia aplicada a estoque e a fluxo, respectivamente. Se você implementar os dois, teste se são redundantes — provavelmente têm correlação de 0,4–0,6.

---

#### #28 — DERIVA DE ESTILO AGREGADA (rotação institucional) ★

**Definição.** Calcule a exposição da carteira institucional agregada a fatores (value, momentum, quality, size) trimestre a trimestre; o Δ é a direção da rotação. No corte transversal, sinalize ações alinhadas com a direção da rotação.

**Direção.** Ambígua, e o problema é fundamental: você tem ~100 trimestres de observação no agregado. Graus de liberdade insuficientes para qualquer inferência séria.

**Veredito.** **Descarte** para o take-home. Mencione no memo como alternativa considerada e rejeitada por insuficiência de amostra — isso demonstra disciplina de escopo, que o enunciado pede explicitamente ("Trying to do everything is a failure mode").

---

### FAMÍLIA F — Meta-sinais

---

#### #29 — DETECÇÃO DE WINDOW DRESSING ★★

**Definição.** Sinalize gestores que, tendo desempenho ruim no trimestre, aparecem no snapshot de fim de trimestre carregados dos maiores ganhadores recentes que não detinham antes. Requer casar retorno da carteira replicada com o padrão de compras.

**Hipótese.** O 13F é um snapshot em uma data conhecida e antecipada. Isso cria incentivo para maquiar a foto. Essas posições não são convicção — são cosmética, e frequentemente são desfeitas em janeiro/abril.

**Direção.** Use para **limpar** o sinal: exclua as compras de gestores sinalizados antes de agregar. Alternativamente, é um sinal de fade.

**Evidência.** Agarwal, Gay & Ling (2014, RFS) sobre window dressing em fundos mútuos; Meier & Schaumburg sobre evidência nos EUA.

**Ganho esperado.** Modesto no nível agregado, mas é uma das poucas formas de melhorar a razão sinal-ruído sem adicionar dados externos.

---

#### #30 — FILERS NOVOS E PEQUENOS (emerging managers) ★★★

**Definição.** Restrinja `M*` a filers com AUM 13F abaixo da mediana, ou a filers que cruzaram o limiar de US$ 100M recentemente. Pondere por `1/AUM` ou `1/sqrt(AUM)`.

**Hipótese.** Capacidade. Um fundo de US$ 300M pode expressar convicção genuína em uma small cap; um de US$ 30bi não pode — as posições dele são necessariamente diluídas e restritas a nomes líquidos. Decrescimento de retorno com escala.

**Direção.** Positiva, potencialmente a partição mais forte do catálogo.

**Evidência.** Antón, Cohen & Polk (2021) documentam heterogeneidade impressionante por tamanho de fundo: as *best ideas* de hedge funds pequenos superam as de fundos grandes em cerca de 15 pontos percentuais ao ano.

**Armadilhas.** (a) Concentra em small caps → custo de transação e capacidade viram restrições reais, precisam entrar no backtest. (b) Filers pequenos têm dados mais sujos. (c) Viés de sobrevivência é pior aqui — fundos pequenos morrem mais.

---

#### #31 — INICIAÇÃO DE ALTA CONVICÇÃO (evento) ★★★

**Definição.** Evento conjunto, cruzando #2 e #6:
```
sinalize (m, i, t) se:   S_{m,i,t−1} = 0
                    e    S_{m,i,t} > 0
                    e    w_{m,i,t} ≥ percentil 90 dos pesos de m
                    e    m ∈ M* (subamostra ativa/pequena/hábil)
Signal_i = # de eventos em i no trimestre t, normalizado
```

**Hipótese.** É a intersecção de todos os filtros de convicção do catálogo: nova (máximo conteúdo informacional), grande (máxima convicção), de gestor selecionado (máxima habilidade esperada). Deve ser o sinal mais forte por observação — e o mais esparso.

**Direção.** Positiva, forte.

**Evidência.** Composição de Chen–Hong–Stein (2002) para a perna de iniciação e Antón–Cohen–Polk (2021) para a perna de convicção.

**Armadilhas.** Esparsidade. Em muitos trimestres, muitas ações terão zero eventos. Precisa de uma regra de construção de carteira que lide com isso (ex: carteira de eventos com holding period fixo de 2–4 trimestres e sobreposição, em vez de sort transversal).

---

## 4. Priorização — o que efetivamente construir

O enunciado diz explicitamente que tentar fazer tudo é modo de falha. A recomendação abaixo é uma partição defensável.

### Tier 1 — construa (núcleo do entregável)

| # | Sinal | Por quê |
|---|---|---|
| **#9** | ΔActive weight com correção de drift | Melhor valor/esforço. A correção de drift é a diferença entre um fator real e momentum disfarçado |
| **#1 / #5** | ΔBreadth na subamostra ativa | Ancoragem acadêmica mais sólida do catálogo (CHS 2002); trivial de computar |
| **#11** | Crowding em dias de ADV | Captura a dimensão que os outros ignoram (liquidez de saída); resultado forte e recente (BHL 2022) |
| **#20** | Partição por churn ratio | Multiplica a qualidade de #1, #9 e #11 sem dados novos |
| **#14** | Persistência multi-trimestre | O contra-sinal. Transforma "fiz um fator" em "entendi a estrutura de horizonte do fenômeno" |

Isso é **um fator composto com quatro componentes e um contra-sinal** — escopo honesto para 48 horas, com uma tese coerente: *demanda institucional ativa, medida entre gestores informados e escalada por liquidez, prevê retorno em 1–2 trimestres e reverte depois.*

### Tier 2 — construa se sobrar tempo

| # | Sinal | Por quê |
|---|---|---|
| **#21** | Revelação de posição confidencial | Critério de avaliação explícito do enunciado; alpha documentado |
| **#6** | Best ideas / peso de convicção | Alta base acadêmica; incremento sobre #9 provavelmente real |
| **#30** | Filers pequenos | Partição potencialmente mais forte que #20 |
| **#24** | Clone ingênuo | Como baseline de comparação, não como fator |
| **#22** | Restatement return gap | Custo marginal ~zero se o painel bitemporal já existe |

### Tier 3 — cite no memo como "o que eu construiria a seguir"

| # | Sinal | Justificativa para a lista de três |
|---|---|---|
| **#26** | Demanda latente (Koijen–Yogo) | Prioridade 1: generaliza todo o Tier 1 num arcabouço estrutural único e dá elasticidade de preço |
| **#17** | Pressão de fluxo (requer N-PORT) | Prioridade 2: identificação causal limpa; o 13F sozinho não consegue |
| **#16** | Crowding por similaridade de rede | Prioridade 3: mede crowding corretamente (donos *parecidos*, não donos *muitos*) |

### Descarte explicitamente (e diga por quê no memo)

- **#28** deriva de estilo agregada — ~100 observações no agregado, graus de liberdade insuficientes
- **#13** herding de Sias — incremento marginal pequeno sobre #12 + #14
- **#15** fragilidade G — exige série de fluxos que o 13F não tem; a aproximação é fraca demais
- Qualquer coisa que dependa de dados comerciais (Thomson s34, FactSet Ownership, Novus) — o exercício pede ingestão de EDGAR

---

## 5. Disciplina point-in-time — a seção que decide a avaliação

O enunciado lista point-in-time discipline como critério separado. Trate como tal.

### 5.1 A regra fundamental

**O painel deve ser indexado por `filing_date`, nunca por `report_date`.**

```python
# ERRADO — lookahead de 45+ dias
signal = holdings[holdings.report_date == quarter_end]

# CERTO
signal = holdings[holdings.filing_date <= rebalance_date] \
            .sort_values('filing_date') \
            .groupby(['cik','cusip']).last()
```

Consequência: em qualquer data de rebalanceamento `T`, você tem um painel *incompleto* do trimestre mais recente — alguns filers já entregaram, outros não. **Isso é a realidade, e simulá-la corretamente é o ponto.** Não espere todo mundo entregar.

### 5.2 Painel bitemporal (por causa das emendas)

Cada linha de holdings precisa de duas datas: quando a posição existiu (`report_date`) e quando você soube dela (`filing_date`). Emendas criam múltiplas versões da mesma `(cik, cusip, report_date)`:

- `13F-HR/A` tipo **restatement** → substitui tudo, mas só a partir da data da emenda
- `13F-HR/A` tipo **adds new holdings** → acrescenta linhas, também só a partir da data da emenda
- Pode haver múltiplas emendas por trimestre, numeradas sequencialmente

Implementação: nunca faça `UPDATE`. Sempre `INSERT` de uma nova versão, e resolva a "verdade conhecida em T" com um `as-of join`.

### 5.3 Correção de drift de preço (ver #9)

Reafirmando porque é o segundo erro mais comum: `Δw` entre dois trimestres é dominado pelo retorno do trimestre. Sempre decomponha antes de usar.

### 5.4 Universo point-in-time de filers

Construa a lista de filers ativos em cada trimestre a partir dos índices do EDGAR daquele trimestre, não de uma lista atual. Fundos que quebraram precisam estar no universo enquanto existiram. O mesmo vale para a classificação em `M*` (#5, #19, #20, #30).

### 5.5 Timing de rebalanceamento — três opções defensáveis

| Opção | Como | Prós / contras |
|---|---|---|
| **Trimestral em data fixa** | Rebalanceie em 15/fev, 15/mai, 15/ago, 15/nov (ou 1º dia útil seguinte) | Simples, replicável. Sofre de timing luck: 4 pontos de decisão por ano |
| **Mensal com sinal mais recente** | Rebalanceie todo mês usando o sinal disponível na data | Reduz timing luck; mais turnover; melhor uso da chegada escalonada de filings |
| **Carteiras sobrepostas** | 3 sub-carteiras defasadas em 1 mês, cada uma rebalanceada trimestralmente | Padrão Jegadeesh–Titman; melhor estimativa da média sem inflar turnover |

**Recomendação:** mensal com sobreposição. Mostre no memo que você testou a sensibilidade a essa escolha — a robustez do fator ao timing de rebalanceamento é uma pergunta óbvia de sessão técnica.

### 5.6 Execução

- Use preços do dia seguinte (`T+1`), não do dia do sinal
- Use retornos com ajuste de delisting (CRSP `DLRET`), senão você tem viés de sobrevivência dentro do próprio backtest
- Exclua microcaps abaixo do percentil 20 do NYSE, ou reporte os resultados com e sem

### 5.7 Custos de transação

Turnover de fator trimestral 13F é baixo (~30–60% ao ano), mas os sinais mais fortes (#30, #31) concentram em small caps. Modele:
```
custo_one_way = meio_spread + impacto
impacto ≈ λ · (tamanho_do_trade / ADV)^0.5
```
Reporte o **breakeven cost** — quantos bps de custo anulam o alpha. Isso é mais informativo que assumir um número e é mais difícil de contestar.

---

## 6. Engenharia de dados — checklist de armadilhas

O enunciado nomeia explicitamente CUSIP mapping, filer dedup, emendas e CT como "onde a desleixo aparece". Cada item abaixo é uma dessas.

### 6.1 Ingestão

- **Rota rápida:** os *Form 13F Data Sets* da SEC são TSVs estruturados e achatados, cobrindo de julho/2013 até o presente, atualizados trimestralmente. Se a sua janela começa em 2013Q3, você pula inteiramente o parsing de XML.
- **Rota completa:** EDGAR full-text. O formato de texto ASCII foi descontinuado em 20/mai/2013; de lá para cá todo filing tem `primary_doc.xml` (capa/sumário) + information table XML. Antes disso, parsing de tabelas de texto de largura fixa, mal formadas e heterogêneas. **Uma janela que começa em 2013Q3 é uma decisão de escopo perfeitamente defensável** — diga isso no memo em vez de tentar heroicamente parsear 1999.
- Rate limits do EDGAR: ~10 req/s, header `User-Agent` obrigatório com contato. Faça cache local agressivo.

### 6.2 A armadilha de unidades (silenciosa e letal)

Até 2/jan/2023, a coluna `value` era em **milhares de dólares**. A partir de 3/jan/2023, é em **dólares**. Filings anteriores nunca foram reexpressos. Uma série que atravessa a mudança sem tratamento tem todo o período pré-2023 subestimado por fator de 1.000, e **nada no XML sinaliza a unidade**.

Validação obrigatória:
```python
implied = value / (shares * price_at_quarter_end)
# deve ficar próximo de 1.0 (dólares) ou 0.001 (milhares)
# qualquer outra coisa = filing corrompido, sinalize e exclua
```
Note também que alguns filers erram a convenção nos dois sentidos, então a checagem por filing é necessária mesmo dentro de um mesmo regime.

### 6.3 CUSIP → identificador de segurança

- 13F reporta CUSIP de 9 caracteres, mas filers erram: 8 caracteres, zeros à esquerda perdidos por leitura como número, espaços, minúsculas.
- Normalize: `strip → upper → zfill(9)`, e valide o dígito verificador.
- Case por **`NCUSIP` histórico** do CRSP com intervalo de datas, **não** pelo campo `CUSIP` (que é o atual). Usar o CUSIP atual é lookahead: você está aplicando a identidade de hoje a um filing de 2015.
- CUSIPs mudam em reorganizações societárias. Mantenha uma tabela de mapeamento com validade temporal.
- Pós-2023 há coluna FIGI opcional — útil como desempate quando presente, mas não confie na cobertura.
- Meça e **reporte a taxa de casamento**. Casar 97% do valor em dólares é resultado bom; se você não sabe qual é a sua taxa, você não sabe o que está no seu painel.

### 6.4 Deduplicação de filers

- `CIK` é a chave, mas famílias filiam por múltiplos CIKs.
- **`13F-NT`** = notice: "minhas posições estão reportadas por outro gestor". Não contém holdings. Se você contar filers por número de filings, os NT inflam a contagem.
- **Combination reports** = parte aqui, parte lá.
- A capa e o sumário trazem `List of Other Included Managers` com números de arquivo 13F — use isso para construir o grafo de agregação e evitar dupla contagem.
- Dupla contagem também ocorre via colunas de **investment discretion** (`SOLE` / `DEFINED` / `OTHER`) e voting authority. Decida uma política explícita — sugestão: contar apenas `SOLE` para medidas de convicção, e o total para medidas de propriedade agregada — e documente.

### 6.5 Emendas

Já coberto em §5.2. Ponto adicional: o sumário de uma emenda reflete apenas o conteúdo *da emenda*, não o total consolidado. Não use como validação do total.

### 6.6 Confidential treatment

- A capa tem flag de CT; o preview HTML mostra aviso de que informação confidencial foi omitida.
- Consequência: um filing com CT tem um buraco de tamanho desconhecido. Não trate a ausência de uma posição como saída (#2).
- Ao expirar ou ser negado o sigilo, o gestor tem 6 dias úteis para divulgar, via novo 13F ou emenda do tipo *adds new holdings* — que é exatamente o gancho do sinal #21.

### 6.7 Limpeza da information table

- Coluna `SH/PRN`: `SH` = ações, `PRN` = valor de face (conversíveis). **Exclua `PRN`** dos cálculos baseados em ações.
- Coluna `putCall`: linhas de opções são separadas. **Nunca some com linhas de ações** (#25).
- Múltiplas linhas do mesmo CUSIP dentro de um filing (contas distintas): some — mas mantenha as linhas de opções separadas.
- Ajuste splits ao comparar `S_{m,i,t}` com `S_{m,i,t−1}` (fator cumulativo do CRSP). Sem isso, todo split vira um "trade" enorme e fantasma.
- Filtre o universo final para common stock (CRSP `SHRCD` 10/11) para o backtest, mesmo que a lista 13(f) inclua ETFs, ADRs e closed-end funds.

### 6.8 Validação (mínimo aceitável)

1. Total do information table vs. total do sumário, por filing
2. `value / (shares × preço)` dentro de tolerância (§6.2)
3. Taxa de casamento de CUSIP, por trimestre — se ela cair num trimestre, algo quebrou
4. Contagem de filers por trimestre — deve crescer suavemente; saltos = bug de dedup
5. IO agregada por ação ≤ 100% do float (violações apontam para dupla contagem)

---

## 7. Alternativas consideradas e descartadas (material direto para o memo)

O enunciado pede escopo deliberado e defesa das exclusões. Estas são exclusões com razão declarada:

| Excluído | Razão |
|---|---|
| Timing de mercado / rotação setorial a partir do agregado 13F | ~100 observações trimestrais no agregado; poder estatístico insuficiente para qualquer inferência |
| Formulários 13D/13G (ativismo) | Fonte, cadência e pipeline diferentes; é outro exercício. O evento tem alpha bem documentado (Brav et al. 2008), mas não é 13F |
| N-PORT (holdings mensais de fundos, com shorts e derivativos) | Estritamente superior em conteúdo, mas cobre só fundos registrados e é outra ingestão. Vai para a lista de "próximos passos" |
| Form SHO (posições short agregadas) | Compliance adiada para fev/2028 após remand do Fifth Circuit; não existem dados |
| Janela pré-2013 | Formato de texto ASCII, parsing heterogêneo. Custo de engenharia desproporcional ao ganho amostral em 48h |
| Bases comerciais de holdings (Thomson s34, FactSet, Novus) | O exercício pede ingestão do EDGAR. Além disso, s34 historicamente omite linhas de opções e posições confidenciais — as duas coisas que dão diferenciação a este trabalho |
| Universo internacional | 13F cobre 13(f) securities dos EUA. ADRs entram, ações locais estrangeiras não |
| Rebalanceamento diário | O sinal é trimestral com 45+ dias de lag. Rebalanceamento diário adiciona custo e nenhuma informação |

---

## 8. Bibliografia

**Breadth e propriedade institucional**
- Chen, J., Hong, H., & Stein, J. (2002). Breadth of ownership and stock returns. *JFE* 66(2–3), 171–205. http://www.columbia.edu/~hh2679/breadth-jfe.pdf
- Gompers, P., & Metrick, A. (2001). Institutional investors and equity prices. *QJE* 116(1).
- Nagel, S. (2005). Short sales, institutional investors and the cross-section of stock returns. *JFE* 78(2).
- Choi, J., Jin, L., & Yan, H. (2013). What does stock ownership breadth measure? https://pmc.ncbi.nlm.nih.gov/articles/PMC3992521/

**Convicção e concentração**
- Antón, M., Cohen, R., & Polk, C. (2021). Best Ideas. https://personal.lse.ac.uk/polk/research/bestideas.pdf
- Cohen, R., Polk, C., & Silli, B. (2010). Best Ideas. SSRN 1364827.
- Kacperczyk, M., Sialm, C., & Zheng, L. (2005). On the industry concentration of actively managed equity mutual funds. *JF* 60(4).
- Cremers, M., & Petajisto, A. (2009). How active is your fund manager? *RFS* 22(9).

**Crowding, herding, fragilidade**
- Brown, G., Howard, P., & Lundblad, C. (2022). Crowded Trades and Tail Risk. *RFS* 35(7), 3231–3271. https://doi.org/10.1093/rfs/hhab107
- Lakonishok, J., Shleifer, A., & Vishny, R. (1992). The impact of institutional trading on stock prices. *JFE* 32(1), 23–43.
- Wermers, R. (1999). Mutual fund herding and the impact on stock prices. *JF* 54(2).
- Sias, R. (2004). Institutional herding. *RFS* 17(1).
- Dasgupta, A., Prat, A., & Verardo, M. (2011). Institutional trade persistence and long-term equity returns. *JF* 66(2), 635–653. https://personal.lse.ac.uk/dasgupt2/dpv.pdf
- Greenwood, R., & Thesmar, D. (2011). Stock price fragility. *JFE* 102(3).
- Antón, M., & Polk, C. (2014). Connected stocks. *JF* 69(3).
- Coval, J., & Stafford, E. (2007). Asset fire sales (and purchases) in equity markets. *JFE* 86(2).
- Lou, D. (2012). A flow-based explanation for return predictability. *RFS* 25(12).

**Habilidade, horizonte e seleção de gestor**
- Yan, X., & Zhang, Z. (2009). Institutional investors and equity returns: are short-term institutions better informed? *RFS* 22(2), 893–924. https://www.lehigh.edu/~xuy219/research/horizon_RFS.pdf
- Bushee, B. (1998, 2001). Classificação transient / dedicated / quasi-indexer.
- Griffin, J., & Xu, J. (2009). How smart are the smart guys? A unique view from hedge fund stock holdings. *RFS* 22(7), 2531–2570.
- Wermers, R., Yao, T., & Zhao, J. (2012). Forecasting stock returns through an efficient aggregation of mutual fund holdings. *RFS* 25(12).
- Puckett, A., & Yan, X. (2011). The interim trading skills of institutional investors. *JF* 66(2).
- Frank, M., Poterba, J., Shackelford, D., & Shoven, J. (2004). Copycat funds. *Journal of Law & Economics* 47(2).

**Disclosure, sigilo e emendas**
- Agarwal, V., Jiang, W., Tang, Y., & Yang, B. (2013). Uncovering hedge fund skill from the portfolio holdings they hide. *JF* 68(2), 739–783. https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.12012
- Aragon, G., Hertzel, M., & Shi, Z. (2013). Why do hedge funds avoid disclosure? *JFQA* 48(5).
- *Do Hedge Funds Strategically Misreport Their Holdings? Evidence from 13F Restatements*. *Management Science* (2025). https://doi.org/10.1287/mnsc.2024.08833
- Christoffersen, S., Danesh, E., & Musto, D. Why do institutions delay reporting their shareholdings? Evidence from Form 13F.
- Aragon, G., & Martin, J. (2012). A unique view of hedge fund derivatives usage. *JFE* 105(2), 436–456.
- Agarwal, V., Gay, G., & Ling, L. (2014). Window dressing in mutual funds. *RFS* 27(11).
- Anderson, A. (2018). An examination of 13F filings. *Journal of Financial Research*. https://onlinelibrary.wiley.com/doi/10.1111/jfir.12150

**Sistemas de demanda**
- Koijen, R., & Yogo, M. (2019). A demand system approach to asset pricing. *JPE* 127(4), 1475–1515.
- Koijen, R., Richmond, R., & Yogo, M. (2024). Which investors matter for equity valuations and expected returns? *RES* 91(4), 2387–2424. https://www.nber.org/system/files/working_papers/w27402/w27402.pdf
- Gabaix, X., & Koijen, R. (2021). In search of the origins of financial fluctuations: the inelastic markets hypothesis.

**Fontes regulatórias**
- SEC — Frequently Asked Questions About Form 13F: https://www.sec.gov/rules-regulations/staff-guidance/division-investment-management-frequently-asked-questions/frequently-asked-questions-about-form-13f
- SEC — Form 13F Data Sets: https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets
- SEC — Section 13(f) Confidential Treatment Requests: https://www.sec.gov/investment/divisionsinvestmentguidance13fpt2htm
- SEC — Ordem de extensão Rule 13f-2 / Form SHO (3/dez/2025), Release 34-104303: https://www.sec.gov/files/rules/exorders/2025/34-104303.pdf
