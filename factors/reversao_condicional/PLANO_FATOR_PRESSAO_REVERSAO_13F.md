# Plano — Fator de reversão condicionada a pressão de fluxo institucional (13F)
### Revisão crítica da hipótese, correção do elo causal, protocolo PIT e desenho de backtest

---

## 0. Diagnóstico: o furo central, e por que ele te ajuda

### 0.1 Sua cadeia causal, como você a escreveu

1. Existe autocorrelação de resgate nos fundos.
2. Logo, o resgate persiste nas próximas janelas.
3. Logo, a venda forçada persiste.
4. **Logo, compro a reversão.**

**O passo 3 → 4 não se sustenta.** Se a venda forçada persiste, a pressão de preço persiste — o papel continua caindo. Reversão é o que acontece *depois que o choque se esgota*, não enquanto ele está rodando.

### 0.2 A evidência que resolve isso

Lou (2012, *RFS* 25(12):3457–3489) testou precisamente essa tensão. Na versão working paper (FMG DP643) ele é explícito:

> Como o flow-induced trading é altamente persistente, papéis que sofrem vendas induzidas por fluxo neste trimestre tendem a sofrer mais vendas induzidas por fluxo em seguida. **As duas forças trabalham uma contra a outra e o efeito líquido é insignificante na minha amostra.** Em contraste, o efeito de reversão domina na amostra de fluxos extremos analisada por Coval e Stafford (2007), por duas razões. Primeiro, fluxos extremos causam choques de demanda maiores e portanto uma reversão mais forte. Segundo, **fluxos de capital extremos têm menor probabilidade de se repetir**, e portanto o trading induzido por fluxo extremo corrente é um mau preditor [do trading futuro].

Leia a segunda razão duas vezes. Ela é o seu plano de pesquisa.

### 0.3 A hipótese reformulada

> **H1 (pressão).** Venda forçada por gestores sob choque de fluxo desloca o preço temporariamente na medida em que o volume forçado é grande relativamente à capacidade de absorção do papel.
>
> **H2 (transitoriedade — o elo corrigido).** A reversão dessa deslocação é **crescente na probabilidade de que o choque de fluxo se encerre**, não na probabilidade de que ele continue. Onde o choque é persistente, continuação e reversão se cancelam; onde é transitório, a reversão domina.
>
> **H3 (informação).** A parcela da venda que é discricionária e informada não reverte. Condicionar em um separador informação-vs-pressão deve concentrar o alfa.

Contribuição declarável: Lou identifica H2 como explicação para o seu próprio nulo, mas **não a operacionaliza como fator**. Você vai. Isso é defensável numa sessão técnica e é honesto — você não está reivindicando ineditismo do mecanismo, está reivindicando que mediu a condição que a literatura diz que importa.

### 0.4 O que mudou desde o plano anterior

No plano de fator anterior eu cortei a família Coval-Stafford / Lou por dois motivos: (i) exige TNA mensal por fundo (CRSP MF / Morningstar), que você não tem; (ii) Wardlaw (2020) mostrou que a medida padrão é mecanicamente função do retorno realizado.

**O que muda:** (i) some, porque você deriva o choque de exposição do *próprio 13F* — precedente publicado em Ben-David, Franzoni & Moussawi (2012, *RFS* 25(1):1–54), que infere desalavancagem forçada de hedge funds exatamente a partir de holdings 13F de ações long. (ii) **não some** — mas vira o eixo metodológico do memo em vez de um motivo de corte. Ver §3.

---

## 1. Mapa da literatura — o que cada paper faz com o seu plano

| Paper | Achado | Efeito sobre o seu plano |
|---|---|---|
| **Coval & Stafford (2007)**, *JFE* 86(2):479–512 | Fundos no decil inferior de fluxo têm ~2× mais probabilidade de reduzir ou eliminar posições. Vendas concentradas geram pressão de preço; preços revertem gradualmente. Chen-Hanson-Hong-Stein caracterizam a reversão como "aproximadamente 18 meses". | **Base.** Também te dá a fórmula de fluxo implícito e a evidência de que o ajuste é majoritariamente *escalar posições existentes*, não abrir/fechar. |
| **Lou (2012)**, *RFS* 25(12):3457–3489 | Fluxos são altamente previsíveis; E[FIT] prevê retorno positivamente no ano seguinte e reverte nos anos subsequentes. Persistência e reversão se cancelam. | **Quebra o seu passo 3→4 e fornece o conserto.** Vira H2. |
| **Dasgupta, Prat & Verardo (2011)**, *JF* 66(2):635–653 | Trading institucional persistente prevê retorno **negativamente** no longo prazo: papéis persistentemente vendidos superam os persistentemente comprados. Estratégia de persistência de 2 trimestres: 25–40 bps; de 4 trimestres: 41–50 bps, para holding de dois anos ou mais. | **Sustenta sua tese direcional, usando só 13F.** Mas: eles refazem a análise **excluindo instituições sujeitas a fluxo (fundos mútuos)** e o resultado não muda — ou seja, **rejeitam o mecanismo de fluxo** e preferem herding reputacional. Essa é a sua abertura: o corte deles é grosseiro; você tem medida explícita de choque. |
| **Wardlaw (2020)**, *JF* 75(6):3221–3243 | A medida padrão de pressão é *inadvertidamente função direta do retorno realizado do papel no trimestre de saída*. Removida a contaminação, o efeito vira uma queda desprezível **sem reversão subsequente**, e vários resultados estabelecidos deixam de valer. | **Quebra o seu indicador `financeiro/ADV`.** Ver §3, que é obrigatória. |
| **Huang, Ringgenberg & Zhang**, *The Information in Fire Sales* | Papéis de fire sale com short interest alto continuam caindo e **não revertem** — gestores têm habilidade de venda. Assimetria informacional impede o arbitrador de separar pressão de informação. | **Condiciona o sinal.** Vira H3 e o Bloco C. |
| **Sias (2004)**, *RFS* 17(1):165–206 | Demanda institucional por um papel é positivamente correlacionada com a demanda no trimestre anterior; e é mais fortemente ligada à demanda defasada do que ao retorno defasado. | **Sustenta a premissa de autocorrelação**, mas ao nível do *papel*, não do fundo. Distinção que você precisa fazer explicitamente. |
| **Chen, Hanson, Hong & Stein (2008)**, NBER WP 13786 | Hedge funds antecipam fire sales começando 3–6 meses **antes** do trimestre de venda. | **Alerta de crowding/decay.** O trade é conhecido desde 2008. Espere alfa pequeno. |
| **Ben-David, Franzoni & Moussawi (2012)**, *RFS* 25(1):1–54 | Infere desalavancagem forçada de hedge funds a partir de holdings 13F long na GFC. | **Precedente para a sua abordagem de dados.** Cite para justificar derivar o choque do 13F. |
| **Manconi, Massa & Yasuda (2012)**, *JFE* 104(3):491–518; **Ma, Xiao & Zeng (2022)**, *RFS* 35(10):4674–4711 | Sob estresse, fundos seguem *pecking order*: vendem o líquido primeiro. Em mercados tranquilos predomina o corte horizontal (pro-rata). | **Determina quais papéis apanham, e é estado-dependente.** Testável nos seus dados. Vira o Bloco A2. |
| **Frazzini & Lamont (2008)**, *JFE* 88(2):299–322 | "Dumb money": fluxo de varejo prevê retorno negativamente no longo prazo. | Sinal oposto em horizonte longo. Controle. |
| **Nagel (2012)**, *RFS* 25(7):2005–2039 | Reversão de curto prazo é remuneração por provisão de liquidez; varia com VIX. | **Seu overlay "live" é esse fator.** Ver §2.4 — ônus da prova. |
| **Harvey, Liu & Zhu (2016)**, *RFS* 29(1):5–68 | Multiple testing: t > 3.0 como barra em cross-section. | Reporte quantas especificações você rodou. |
| **Novy-Marx & Velikov (2016)**, *RFS* 29(1):104–147 | Taxonomia de custo de transação por anomalia. | Seu fator carrega em nomes ilíquidos por construção. Ver §5.3. |

---

## 2. O fator, módulo a módulo

Nome de trabalho: **TRP — Transitory Reversal Pressure.**

Estrutura: `Score = Agregação_j [ Pressão(i,j) × Transitoriedade(j) ] × Filtro_de_informação(i)`, com **uma única normalização cross-sectional no final**.

### 2.1 Bloco A — Pressão, em ações, à prova de Wardlaw

**A1. Choque de exposição implícito por gestor.** Aplique a fórmula de Coval-Stafford ao book 13F:

```
f[j,t] = ( V[j,t] − V[j,t−1] × (1 + rP[j,t]) ) / V[j,t−1]
```

onde `V` é o valor de mercado do book 13F e `rP[j,t]` é o retorno buy-and-hold do portfólio de `t−1` ao longo de `t`, calculado com os pesos de `t−1`.

**Nomeie isso honestamente.** Não é fluxo de investidor. É **variação de exposição líquida em ações (ΔEXP)**, que mistura: resgate/aplicação, mudança de alavancagem, rotação para fora do universo 13(f)-reportável, e artefato de reporte. Chamar de "fund flow" no memo é o tipo de coisa que morre em cinco segundos numa defesa técnica. Chamar de ΔEXP e listar os componentes te dá crédito.

Argumento de defesa que você deve preparar: para efeito de *impacto de preço*, ΔEXP é a variável certa — o que move o preço é o trade líquido do gestor, não a origem do dinheiro. A origem importa só para H3 (informado vs. forçado), e é lá que você a trata.

**A2. Trade forçado esperado, por posição, em ações.** Não assuma pro-rata. Estime:

```
Δq[i,j,t] / q[i,j,t−1] = α + β·f[j,t] + γ·( f[j,t] × Illiq[i,t−1] ) + controles + ε
```

- `β` mede a intensidade do corte horizontal (Coval-Stafford).
- `γ` mede o pecking order (Manconi-Massa-Yasuda; Ma-Xiao-Zeng): se `γ ≠ 0`, a resposta depende da liquidez do papel.
- Estime em **janela expansiva, só com dados anteriores à data de rebalance**. O trade previsto usa coeficientes estimados fora da amostra → sem lookahead.

Isso substitui o seu "score de persistência da posição na carteira" por uma função-resposta estimada com interpretação econômica e literatura por trás. É estritamente mais forte na defesa: você não precisa justificar a forma funcional de um sigmoide, precisa reportar dois coeficientes e o R².

**A3. Agregação e escala — a parte não negociável.**

```
Pressão[i,t] = Σ_j ( Δq_previsto[i,j,t] | f[j,t] < percentil_p ) / ShareADV[i, t−1]
```

Regras de higiene, a serem escritas como *assertions* no código:

1. Numerador em **ações**, derivado de holdings de `t−1`.
2. Denominador de `t−1`: volume médio diário **em ações** do trimestre anterior. Nunca volume financeiro, nunca do trimestre `t`.
3. **Nenhum preço do trimestre `t` entra no sinal.** Em lugar nenhum.
4. Alternativa de denominador: shares outstanding. Você só tem isso a partir de ~2015 via Yahoo e não é PIT — use como robustez, não como principal.

**Por que isso importa tanto:** `financeiro/ADV` tem preço no numerador (valor da posição) e preço no denominador (volume financeiro). Wardlaw mostra que essa construção é função direta do retorno realizado. É exatamente o indicador que você desenhou. Corrigido para ações/ações, o problema some.

### 2.2 Bloco B — Transitoriedade: o seu teste de autocorrelação, no papel certo

Este é o bloco onde a sua intuição vira contribuição. Ele tem duas metades: **medir** a persistência corretamente, e **usá-la com o sinal invertido**.

#### B1. Medir — bateria de testes

**(a) AR(1) em painel.**
```
f[j,t+1] = a + ρ·f[j,t] + X + u
```
Com efeito fixo de gestor há viés de Nickell, ≈ −(1+ρ)/(T−1). Com T ≈ 40 trimestres o viés é da ordem de 3 p.p. — tolerável, mas reporte Arellano-Bond como robustez. Erros-padrão clusterizados por gestor e por trimestre (two-way).

**(b) Correção do viés mecânico — faça isto, é o detalhe que separa o trabalho bom do trabalho profissional.**

`V[j,t]` entra positivamente no numerador de `f[j,t]` e negativamente no numerador de `f[j,t+1]`. Qualquer erro de medida em `V[j,t]` — parsing, mudança de unidade, filer entrando/saindo — induz **autocorrelação negativa espúria**. Ou seja: se você medir `ρ` e der baixo, pode ser artefato.

Conserto: estime também `ρ` pulando um trimestre,
```
f[j,t+1] = a + ρ*·f[j,t−1] + X + u
```
`f[j,t−1]` usa `V[j,t−1]` e `V[j,t−2]`; `f[j,t+1]` usa `V[j,t+1]` e `V[j,t]`. Sem termo compartilhado → imune ao erro de medida. **Reporte os dois.** A diferença entre `ρ` e `ρ*` é sua estimativa da contaminação.

**(c) O teste que realmente decide o plano — não-linearidade nas caudas.**

Estime `ρ` **por decil de |f|**, separadamente. A predição de Lou é que `ρ` é alto no miolo e **baixo nas caudas** (choques extremos revertem). Plote `ρ(decil)`.

- Se a curva tem forma de U invertido → sua tese tem base empírica e você tem a figura que vende o memo inteiro.
- Se `ρ` é plano ou crescente nas caudas → **H2 não tem suporte nos seus dados**; ver critérios de parada, §6.

**(d) Matriz de transição** entre quintis de `f`, trimestre a trimestre. Meia-vida do choque. Fração de gestores que permanecem no quintil inferior por 2, 3, 4 trimestres consecutivos.

**(e) Ljung-Box** no painel pooled; distribuição dos AR(1) individuais por gestor com contagem de significantes ao nível nominal vs. esperado sob o nulo.

**(f) Censura, não resgate.** Um gestor que cai abaixo de US$ 100 milhões em títulos 13(f) **para de arquivar**. Isso não é `f = −100%`, é observação censurada. Se você tratar como resgate total, o `ρ` das caudas vai para o lixo e o backtest fica com um viés grosseiro. Trate como censura, reporte quantos casos, e verifique se voltam a arquivar depois.

#### B2. Usar — com o sinal invertido

Ajuste, em janela expansiva PIT:
```
π[j,t] = P( |f[j,t+1]| ≥ limiar  e  mesmo sinal  |  f[j,t], decil, tipo de filer, f dos 4 trimestres anteriores, iliquidez do book )
```
`π` é a probabilidade de o choque **se repetir**. O peso de transitoriedade é `(1 − π[j,t])`.

**Não coloque sigmoide de z-score aqui.** Você tem uma probabilidade calibrada. Use direto, e reporte um *reliability diagram* (probabilidade prevista vs. frequência realizada, por bucket). Uma curva de calibração num apêndice compra credibilidade que nenhum hiperparâmetro de sigmoide compra.

### 2.3 Bloco C — Filtro de informação

Huang-Ringgenberg-Zhang: onde a venda é informada, não reverte. Duas implementações, em ordem de custo.

**C1 (grátis, e é a melhor ideia do plano) — dispersão de venda entre chocados e não chocados.**

Você observa *todos* os holders do papel, chocados e não chocados. Construa, ao nível do papel:

```
Discrição[i,t] = ( fração dos holders SEM choque que reduziram )
               − ( fração dos holders COM choque que reduziram )
```

Se os não chocados também estão despejando, é informação — o papel é ruim e a venda dos chocados não é notícia. Se os não chocados seguram ou aumentam enquanto os chocados vendem, é pressão pura. Isso é um **diff-in-diff ao nível do papel**, construível 100% dos dados que você já tem, e ataca exatamente o problema de identificação que o HRZ levanta. Use como gate multiplicativo ou como peso suave.

**C2 (se sobrar tempo) — short interest FINRA.** Bimensal, grátis, publicado com defasagem de poucos dias úteis (confirme a data exata de publicação para o PIT). Exclua ou desconte o quintil superior de short interest / days-to-cover entre os papéis pressionados. Reporte o fator **com e sem** o gate: se ajudar, você confirmou HRZ em amostra nova, o que é um resultado bom de ter no memo.

### 2.4 Overlay D — a parte "live", e o ônus da prova

Você quer somar `sigmoide(−z(retorno de 1 mês))`. Seja explícito: **isso é short-term reversal** (Jegadeesh 1990; Lehmann 1990; Nagel 2012). É um fator forte, conhecido, e com biblioteca pública de fatores.

O ônus da prova, portanto, é: **o bloco 13F adiciona alguma coisa em cima de STR?** Desenhe o teste antes de rodar:

1. Double-sort: STR × TRP, 5×5. Olhe se o spread de TRP sobrevive dentro de cada bucket de STR.
2. Fama-MacBeth com STR, momentum, tamanho e iliquidez como controles, erros-padrão Newey-West.
3. Regressão de spanning do portfólio combinado sobre um fator STR construído **no mesmo universo, com os mesmos custos**. A biblioteca do Ken French tem o fator de reversão de curto prazo em CSV grátis — use.

Se a resposta for "o bloco 13F não adiciona nada", **escreva isso no memo**. É um resultado, e é infinitamente melhor do que um positivo fabricado. O enunciado pede explicitamente "honest assessment of what worked, what didn't, where you have low confidence".

**Reformulação recomendada do overlay:** em vez de somar ao score como alfa, use-o como **regra de entrada**. Seu sinal é trimestral e chega em datas irregulares de arquivamento; o overlay decide *quando dentro da janela* entrar. Isso o transforma de fonte de alfa em execução, reduz a superfície de overfitting, e é mais fácil de defender.

### 2.5 Agregação — por que trocar a pilha de sigmoides

Seu desenho: soma sobre gestores de um produto de sigmoides. Três problemas:

1. **Parâmetros livres.** Cada sigmoide tem uma inclinação. Quatro sigmoides = quatro graus de liberdade não identificados. Numa defesa técnica, "por que essa inclinação?" não tem boa resposta.
2. **Multiplicar destrói a aditividade.** Impacto de preço é aditivo em ações negociadas. Somar contribuições em ações e normalizar uma vez preserva a economia; multiplicar scores bounded não.
3. **Normalizar antes de agregar destrói a escala.** Se você faz z-score por gestor antes de somar, um gestor de US$ 200 milhões pesa igual a um de US$ 20 bilhões.

Proposta:

```
Score[i,t] = ( Σ_j (1 − π[j,t]) · Δq_previsto[i,j,t] ) / ShareADV[i,t−1]
Score[i,t] ← Score[i,t] × Gate_informação[i,t]
Sinal[i,t] = normal_score( rank_cross_sectional( Score[i,t] ) )
```

Uma normalização, no fim. Se quiser manter o sigmoide, use-o só como squashing final com inclinação fixada por regra (unitária sobre o z-score) e apresente uma tabela de sensibilidade.

---

## 3. Protocolo de Wardlaw — a seção que o memo precisa ter

Wardlaw (2020) é a coisa mais provável de aparecer na defesa técnica, e a mais fácil de neutralizar se você se antecipar.

**Rode o placebo de Wardlaw e ponha o resultado no memo:**

```
r[i,t] = a + b · Pressão[i,t] + ε
```

onde `r[i,t]` é o retorno **contemporâneo** ao trimestre da pressão. Sob a medida contaminada, `b` é grande e significativo por construção mecânica. Sob a sua medida em ações/ações, `b` deve ser pequeno.

Reporte os dois: a medida ingênua (`financeiro/ADV`, como você havia desenhado) e a corrigida, lado a lado, com o `t` do placebo. Uma tabela de duas linhas que mostra "eu conhecia a armadilha, medi o tamanho dela, e a evitei" vale mais do que qualquer Sharpe.

**Critério de parada associado:** se o placebo na medida corrigida der |t| > 3, você ainda tem contaminação. Não reporte o fator como válido até achar a fonte.

---

## 4. Disciplina point-in-time — reaproveitando a infra que você já tem

Você já tem painel bitemporal com `filed_date` e timestamp de aceitação por versão, semântica RESTATEMENT/NEW HOLDINGS, e `snapshot_as_of()`. Reuse. Pontos específicos que um **fator de fluxo** exige e que um fator de holdings não exigia:

**4.1 Regra de as-of.** O sinal na data de rebalance `d` usa exclusivamente filings com timestamp de aceitação `≤ d`. Nunca D+45. Seu próprio resultado X3 (≈51% dos filings acumulados em D+45) é a evidência de que D+45 assume conhecimento de filings que ainda não existiam — e o viés não é aleatório, concentra-se nos gestores mais informativos. Isso é um parágrafo forte do memo e ele é seu.

**4.2 13F-NT é uma armadilha específica deste fator.** Um filer que arquiva 13F-NT (notice) declara que suas posições estão no filing de outro gestor. Se o seu parser trata NT como book vazio, `V[j,t] = 0` e você acabou de gerar um resgate de −100% fictício. Para um fator de holdings isso é ruído; para um fator de fluxo é veneno. Trate NT como observação ausente, não como zero. **Cheque isso primeiro** — é o bug mais provável do projeto inteiro.

**4.3 Mudança de unidade do campo `value`.** A SEC alterou o reporte de valor de milhares para dólares inteiros (a partir de 2023). Um parser ingênuo vê `V` saltar 1000× e registra um fluxo de +99.900%. Implemente um **teste de salto por filer**: sinalize qualquer `|f| > 5` e inspecione manualmente antes de aceitar. Reporte quantos casos foram unidade e quantos foram reais.

**4.4 Deduplicação de filers.** Os campos `otherManager` / `otherIncludedManagers` fazem a mesma posição aparecer no filing da matriz e do sub-adviser. Para um fator de fluxo, dupla contagem infla o tamanho do trade e portanto a pressão. Deduplique no nível (família de gestor, cusip, período) antes de agregar.

**4.5 Tratamento confidencial.** Posições sob CTR aparecem só num amendment posterior, às vezes com um ano de atraso. Entram no painel na **data de aceitação do amendment**, jamais retrodatadas. Agarwal, Jiang, Tang & Yang (2013, *JF*) mostram que holdings confidenciais performam acima da média — retrodatar não é só lookahead, é lookahead enviesado na direção que infla o resultado.

**4.6 Universo PIT sem survivorship.** Use a *Official List of Section 13(f) Securities* da SEC, publicada trimestralmente, como universo elegível contemporâneo. Ela inclui tudo que morreu depois. Onde o Yahoo não tiver preço, **reporte o tamanho do buraco** (quantos nomes, que fração do book agregado) e a direção provável do viés.

**4.7 Retorno de delisting.** Sem ajuste de delisting, papéis que quebraram somem da série e você superestima a reversão. Em large/mid cap a maioria dos desaparecimentos é M&A (retorno terminal positivo, viés *contra* você) — argumento defensável, mas declare-o.

---

## 5. Protocolo de backtest

### 5.1 Universo e janela
- Top ~1.000 por market cap, preço > US$ 5, sem ADR, elegibilidade pela lista 13(f) PIT.
- **2016Q1 – 2025Q4.** Justifique pelo dado (shares outstanding do Yahoo começa ~out/2015) em vez de fingir cobertura maior.
- Consequência a declarar: sua amostra não tem 2008. Você tem 2018Q4, 2020Q1 e 2022 como episódios de estresse. Reporte a performance **excluindo 2020Q1–Q2** — se o fator inteiro for março de 2020, você precisa saber antes de defender.

### 5.2 Calendário
- Rebalance **mensal**, primeiro pregão.
- Sinal em cada rebalance com `filed_date ≤ d`. O fator **evolui dentro do trimestre** conforme os filings chegam. Isso responde diretamente ao critério "how do you handle the quarterly signal in a daily or monthly return framework", e é mais realista do que congelar em D+45.
- Corolário que vale mencionar: o turnover não é 4×/ano nem 12×/ano — é endógeno ao calendário de arquivamento.

### 5.3 Construção de carteira
- Quintis long/short sobre o sinal normalizado.
- **Neutralize tamanho e beta no mínimo.** O fator carrega em ilíquido/small por construção; sem neutralização você vai reportar o prêmio de tamanho.
- Reporte **duas ponderações**: equal-weight (que vai parecer melhor e é inexecutável) e **liquidity-capped** (posição limitada a X% do ADV). A diferença entre as duas é a sua estimativa honesta de capacidade.

### 5.4 Custos — a seção que provavelmente mata a estratégia
Seu sinal seleciona, por construção, nomes com trade grande relativo ao ADV. É exatamente onde o custo come o alfa.

- Modele meio-spread + impacto raiz quadrada: `impacto ≈ σ · Y · √(Q/ADV)`.
- Reporte bruto, líquido a 10 / 25 / 50 bps round-trip.
- **Reporte o custo de break-even** — o nível de custo em que o Sharpe zera. É o número mais persuasivo do memo inteiro para um quant sênior, porque resume capacidade, turnover e alfa numa cifra.

### 5.5 Benchmark e spanning
- Benchmark: EW e CW do mesmo universo.
- Spanning: FF5 + MOM + **STR** (biblioteca do Ken French, CSVs grátis). O teste contra STR é obrigatório dado o Overlay D.
- Baseline interno obrigatório: ver §7.

### 5.6 Diagnósticos obrigatórios
1. Placebo de Wardlaw (§3), medida ingênua vs. corrigida.
2. Curva de decaimento: alfa por horizonte de holding em 1, 3, 6, 12, 18 meses. Coval-Stafford prevê reversão completa em ~18 meses — você deve ver uma corcova. Se não vir, seu sinal não é o que você acha que é.
3. Perna long e perna short **separadas**. A perna de inflow (short) é provavelmente inexecutável: borrow, squeeze, e o 13F não mostra shorts, então você não vê a cobertura.
4. Estabilidade por subperíodo (metades) e excluindo 2020Q1–Q2.
5. Turnover, holding period médio, concentração.
6. Contagem de especificações testadas + haircut de Harvey-Liu-Zhu.

---

## 6. Critérios de parada — escreva antes de olhar os resultados

Pré-registre. Isso transforma qualquer desfecho em memo defensável.

| # | Condição | Ação |
|---|---|---|
| 1 | `ρ` **não** é menor nas caudas do que no miolo (§B1c) | H2 sem suporte. Reporte a figura, e entregue o fator Coval-Stafford simples com correção de Wardlaw como deliverable principal. |
| 2 | Placebo de Wardlaw na medida corrigida com \|t\| > 3 | Medida ainda contaminada. Não reporte o fator como válido. |
| 3 | TRP não sobrevive ao spanning sobre STR | Reporte: "é STR disfarçado". Resultado legítimo. |
| 4 | Custo de break-even < 20 bps round-trip | Declare não-investável, e explique por quê (seleção adversa em iliquidez). |
| 5 | ≥ 5% dos `f` extremos rastreados a bug de unidade ou NT | Pare, conserte o parser, reestime tudo. |

O enunciado avalia "honest assessment of what worked, what didn't, where you have low confidence, and what you think is noise vs. signal". Uma tabela de critérios de parada escrita ex-ante é a prova documental de que você fez isso.

---

## 7. Recomendação estrutural — faça um baseline barato antes do fator caro

Este é o ponto mais importante de gestão de risco do projeto.

**Baseline (≈30 minutos de trabalho):** a medida de persistência de Dasgupta-Prat-Verardo — venda institucional líquida sustentada por 2 e por 4 trimestres consecutivos — é trivial de calcular no painel que você já tem, e é um resultado publicado no *Journal of Finance*. Rode como fator base.

**Tratamento:** TRP, o fator condicionado a fluxo/transitoriedade/informação.

Isso te dá a narrativa mais forte possível para o memo:

> Replicação do fenômeno estabelecido (DPV) → teste de mecanismo (DPV rejeitam fluxo com um corte grosseiro; eu tenho medida explícita) → o condicionamento adiciona valor?

E de-risca o projeto inteiro: **o baseline produz alguma coisa mesmo se o tratamento falhar.** Você nunca chega em 48h com uma tela em branco.

---

## 8. Corte de escopo — o que você deliberadamente não faz

O enunciado diz que tentar fazer tudo é failure mode. Liste explicitamente, com motivo:

| Cortado | Motivo |
|---|---|
| Posições em opções (campo `putCall`) | Delta desconhecido; sem delta, o valor nocional não é exposição. Não dá para tratar direito no orçamento de tempo. |
| Renda fixa, internacional, setores | Fora do escopo do 13F. |
| N-PORT, Form PF, 13D/G | Frequência/lag piores ou cobertura estreita. Vira "próximo passo". |
| ML / redes / grafos | Seu próprio X5 mostra que o melhor ML publicado ganha pouco de heurística simples. Gastar horas aqui é o failure mode nomeado no enunciado. |
| Reconstrução intra-trimestre de holdings | Você já testou o nowcast (X4) e mediu o nulo. Cite o nulo — é força, não fraqueza. |
| Perna short executável | Construída e reportada, mas declarada não-tradeável. |

---

## 9. Os três próximos passos (o enunciado pede isso explicitamente)

1. **N-PORT para separar fluxo de discricionário.** Mensal, para fundos registrados. Permite decompor `ΔEXP = fluxo + decisão` diretamente em vez de por proxy. É a maior melhoria de *medida* disponível, e ataca a fraqueza central do trabalho.
2. **Modelo de execução e curva de capacidade**, mais migração do rebalance mensal para **event-driven na chegada de cada filing** — infraestrutura que você já tem. Converte o corolário de turnover endógeno de observação em desenho.
3. **Contágio entre holders (fragilidade à Greenwood-Thesmar).** A pressão sobre o papel `i` depende da estrutura de correlação dos choques dos seus holders, não da soma dos choques individuais. Um papel com cinco holders correlacionados é mais frágil que um com cinco independentes de mesmo tamanho. É a generalização natural do Bloco A e tem literatura pronta.

---

## 10. Cronograma de 48h

| Bloco | Horas | Entrega |
|---|---|---|
| 0 | 2h | Auditoria do parser: 13F-NT, mudança de unidade, dedup de filers, censura de threshold. **Teste de salto em `f`.** Não avance sem isso. |
| 1 | 3h | Painel de `f[j,t]` + bateria de autocorrelação (§B1 a–f). Figura `ρ(decil)`. **Decisão de continuar ou cair no fallback.** |
| 2 | 2h | Baseline DPV rodando end-to-end com backtest. Rede de segurança pronta. |
| 3 | 4h | Bloco A (resposta estimada A2 + pressão A3) e placebo de Wardlaw. |
| 4 | 3h | Bloco B2 (modelo `π`) + calibração. |
| 5 | 2h | Bloco C1 (diff-in-diff de discrição). C2/FINRA só se sobrar. |
| 6 | 4h | Backtest completo, custos, break-even, diagnósticos §5.6. |
| 7 | 2h | Overlay D e testes de spanning contra STR. |
| 8 | **6h** | **Memo.** Reserve isso independentemente do resultado. |
| — | resto | README, reprodutibilidade a partir de clone limpo, seed, versões pinadas. |

Regra: o bloco 8 não é negociável. Um fator médio com memo excelente passa; um fator bom com memo apressado não.

---

## 11. Referências

Agarwal, V., Jiang, W., Tang, Y. & Yang, B. (2013). Uncovering hedge fund skill from the portfolio holdings they hide. *Journal of Finance* 68(2), 739–783.

Ben-David, I., Franzoni, F. & Moussawi, R. (2012). Hedge fund stock trading in the financial crisis of 2007–2009. *Review of Financial Studies* 25(1), 1–54.

Chen, J., Hanson, S., Hong, H. & Stein, J. (2008). Do hedge funds profit from mutual-fund distress? NBER WP 13786.

Chen, J., Hong, H. & Stein, J. (2002). Breadth of ownership and stock returns. *Journal of Financial Economics* 66(2–3), 171–205.

Coval, J. & Stafford, E. (2007). Asset fire sales (and purchases) in equity markets. *Journal of Financial Economics* 86(2), 479–512.

Dasgupta, A., Prat, A. & Verardo, M. (2011). Institutional trade persistence and long-term equity returns. *Journal of Finance* 66(2), 635–653.

Frazzini, A. & Lamont, O. (2008). Dumb money: Mutual fund flows and the cross-section of stock returns. *Journal of Financial Economics* 88(2), 299–322.

Harvey, C., Liu, Y. & Zhu, H. (2016). …and the cross-section of expected returns. *Review of Financial Studies* 29(1), 5–68.

Huang, S., Ringgenberg, M. & Zhang, Z. The information in fire sales.

Lou, D. (2012). A flow-based explanation for return predictability. *Review of Financial Studies* 25(12), 3457–3489. (Working paper: FMG DP643.)

Ma, Y., Xiao, K. & Zeng, Y. (2022). Mutual fund liquidity transformation and reverse flight to liquidity. *Review of Financial Studies* 35(10), 4674–4711.

Manconi, A., Massa, M. & Yasuda, A. (2012). The role of institutional investors in propagating the crisis of 2007–2008. *Journal of Financial Economics* 104(3), 491–518.

Nagel, S. (2012). Evaporating liquidity. *Review of Financial Studies* 25(7), 2005–2039.

Novy-Marx, R. & Velikov, M. (2016). A taxonomy of anomalies and their trading costs. *Review of Financial Studies* 29(1), 104–147.

Sias, R. (2004). Institutional herding. *Review of Financial Studies* 17(1), 165–206.

Wardlaw, M. (2020). Measuring mutual fund flow pressure as shock to stock returns. *Journal of Finance* 75(6), 3221–3243.

Yan, X. & Zhang, Z. (2009). Institutional investors and equity returns: Are short-term institutions better informed? *Review of Financial Studies* 22(2), 893–924.
