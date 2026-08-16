# Nowcast generativo de holdings + fator de crowding
### Veredito de literatura e desenho proposto para o take-home 13F

---

## 0. Resumo executivo — leia só isto se for ler uma coisa

Três respostas às três perguntas.

**1. A ideia do GAN/diffusion sobre a distribuição condicional da carteira já existe?**
Sim, exatamente. Scholl, Mahfouz, Calinescu & Farmer (ICAIF '25, Oxford + JP Morgan AI Research) modelam literalmente `p(w_{i,t} | w_{i,t−1}, X, r, φ)` com WGAN-GP, latente de estratégia de 8 dimensões, 1.436 fundos mútuos americanos, ~120 mil observações de carteira, 2010–2024. **Diffusion sobre holdings não existe** — o survey de diffusion em finanças de 2026 cobre preços, LOB, séries de retorno e otimização de carteira; holdings não aparece como aplicação.

**2. Funciona?**
Para o que eles queriam, sim. Para *nowcast*, o resultado que decide está na Tabela 1 do próprio paper:

| Modelo | L_replication | L_count | L_concentration | L_turnover |
|---|---|---|---|---|
| Zero-Trade (`ŵ_t = w_{t−1}`) | 0,063 | 23 | 0,0072 | **0,1716** |
| GAN completo | **0,061** | **15** | **0,0047** | 0,5451 |

O GAN ganha em realismo estrutural (número de posições, concentração, universo sintético). Na perda de replicação ele bate "não fazer nada" por **3,2%**. E no **erro de turnover — que é exatamente a quantidade que um nowcast precisa acertar, porque nowcast é prever a *mudança* — o GAN é 3× pior que o baseline trivial.**

Os autores não reivindicam retorno em lugar nenhum. As três aplicações declaradas são strategy discovery, behavioral cloning para stress test, e agent-based modeling. Nenhum backtest, nenhum alfa.

**3. E o "short o que está crowded"?**
Está com o sinal errado na forma incondicional. Brown, Howard & Lundblad (RFS 2022), que é *o* paper de crowding com 13F, encontram que as carteiras **mais crowded têm os maiores retornos médios**. Crowding é um prêmio de risco de cauda: você é pago para carregá-lo em tempo normal e é destruído em distress. Shortar isso incondicionalmente é vender um prêmio e comprar um bilhete de loteria que sangra. E Barroso, Edelen & Karehnke (JFQA 2022) vão além e acham relação *negativa* entre proxies de crowding construídos com holdings institucionais e crash risk esperado — ou seja, a literatura está genuinamente em disputa.

**O que sobra, e que é defensável:** a única versão publicada e robusta de "fade o crowd" é condicional em **persistência multi-trimestral**, não em nível. Dasgupta, Prat & Verardo (JF 2011): ações persistentemente vendidas por instituições ao longo de três a cinco trimestres superam as persistentemente compradas, num horizonte de cerca de dois anos. O mecanismo é career concerns (DPV, RFS 2011): gestores com preocupação reputacional imitam trades passados, isso empurra o preço além do fundamento, e reverte.

**Conclusão operacional.** Não construa o GAN como fator. Construa **um estimador bayesiano da distribuição condicional de demanda** — que é o membro identificado e barato da mesma família — e use-o para o que ele realmente resolve: **corrigir o viés de seleção do filing season**. O generativo deixa de ser o alfa e vira o *estimador que torna o fator disponível mais cedo sem lookahead*. Isso usa exatamente o ativo que você tem e ninguém mais tem (painel bitemporal com timestamp por versão), e o GAN/diffusion vira o item nº 1 da seção "three things I would build next" — onde ele vale pontos em vez de custar.

---

## 1. O paper que é a sua ideia

**Scholl, M., Mahfouz, M., Calinescu, A., Farmer, J.D. (2025).** *Learning to Manage Investment Portfolios beyond Simple Utility Functions.* ICAIF '25, Singapura. arXiv:2510.26165.

### 1.1 O que eles fazem

Formulação idêntica à sua intuição:

```
p_M( w_{i,t} | w_{i,t−1}, X_{i,t−1}, r_{i,t−T…t−1}, φ_{a,t} )
```

onde `w ∈ R^N` são pesos de carteira, `X ∈ R^{N×K}` características dos ativos, `r` histórico de retornos, e `φ_a ∈ R^8` o latente que codifica a estratégia do gestor `a`.

Arquitetura: cGAN com Wasserstein + gradient penalty. Três componentes que valem entender porque cada um é uma dor que você também teria:

- **Gerador de universo sintético (VAE com Carhart-4 embutido).** Eles precisaram disso porque *"experimentos iniciais mostraram que modelos treinados apenas no universo real tinham desempenho ruim out-of-sample"*. Traduzindo: overfitting severo mesmo com 120 mil observações mensais. Você teria ~1/4 disso em frequência trimestral, e mais esparso.
- **Encoder de estratégia em três pistas** (características×pesos → tilt fatorial; retornos×pesos → performance; Δpesos → turnover). Interpretabilidade forçada por arquitetura.
- **Discriminador sobre distribuições completas** `(w'X, w'r, w_t, w_{t−1}, φ)`.

Dados: CRSP Survivor-Bias-Free Mutual Fund, **holdings mensais**, 2010–2024, N=500 maiores ações, filtros de ≥12 meses de histórico e ≥75% do book reportado e dentro do universo.

### 1.2 Os resultados que importam para a sua decisão

**(a) O baseline trivial é competitivo na métrica de nowcast.** Reproduzo a leitura: `L_replication` mede reconstrução da carteira dado o estado de mercado real. Zero-Trade = 0,063; GAN = 0,061. Os próprios autores registram que o Zero-Trade tem desempenho surpreendentemente bom, e atribuem isso ao giro lento de holdings de fundos.

**(b) O GAN perde feio justamente no turnover.** 0,5451 contra 0,1716. Isto é decisivo e é o ponto que você deve saber articular numa defesa técnica: *reconstruir uma carteira* e *prever a variação de uma carteira* são problemas diferentes, e o adversarial training otimiza o primeiro. Nowcast é o segundo.

**(c) Onde o GAN realmente ganha é em realismo estrutural e no universo sintético.** `L_synthetic` cai de 0,830 para 0,236; erro de contagem de posições de 23 para 15. Isso serve simulação, stress test e ABM — as três aplicações que eles declaram. Não serve fator.

**(d) O latente funciona como taxonomia.** SVM linear sobre `φ` recupera classificação Lipper com recall macro de 77%, subindo a ~95% com kernel não-linear. Ou seja: **o valor descritivo é real.** Isso é interessante e é uma alternativa legítima ao seu clustering de Bushee — mas é caro demais para o que entrega, dado que churn ratio + HHI + holding period te dão a mesma partição em vinte linhas de pandas.

**(e) Limitações que eles próprios listam e que são piores no seu caso.** Poucos dados de holdings públicos; mudanças de regime tornando estacionariedade problemática; snapshot mensal insuficiente para estratégias de alta frequência; janela pós-2010 sem crise de 2008.

### 1.3 Diffusion sobre holdings

Não existe. O survey *Diffusion Models in Finance* (arXiv:2608.12583, 2026) cataloga a área e as aplicações são: geração de séries de retorno (CoFinDiff, Diffusion Factor Models), simulação e forecasting de limit order book, otimização de carteira condicional (Factor-Based Conditional Diffusion, arXiv:2509.22088), pricing risk-neutral, e imputação genérica de séries temporais (CSDI, SSSD).

A ferramenta que *seria* a certa se você fosse fazer isso é **CSDI** (Tashiro et al., NeurIPS 2021) — conditional score-based diffusion para imputação probabilística — porque nowcast de holdings é formalmente um problema de imputação com máscara, não de geração. Guarde essa referência: ela é a resposta correta se o entrevistador perguntar "e se você tivesse seis meses?".

### 1.4 Veredito

Existe um paper de um grupo forte (Doyne Farmer + JPM AI) que fez exatamente isso, com dados melhores que os seus (mensal vs. trimestral), publicado numa conferência de AI em finanças, e **o resultado honesto é que o "não fazer nada" empata na métrica de reconstrução e ganha na de variação.** Construir isso num take-home de 48h, onde os critérios de avaliação são *point-in-time discipline*, *data engineering care* e *backtest methodology*, é gastar o orçamento de tempo na dimensão que não é avaliada e adicionar superfície de ataque na defesa técnica.

**Mas o instinto não está errado — está mal alocado.** Vá para a Seção 3.

---

## 2. Por que "short o que está crowded" precisa de conserto

### 2.1 O achado que inverte o sinal

**Brown, Howard & Lundblad (2022), *Crowded Trades and Tail Risk*, RFS 35(7):3231–3271.**

Eles medem crowdedness ao nível de security usando holdings 13F de hedge funds, 2004–2016, ~6.000 papéis, excluindo os 20% menores. Ordenam em quintis. O achado: **as carteiras mais crowded têm os maiores retornos; as menos crowded, os menores.** A diferença é econômica e estatisticamente distinta dos fatores tradicionais. O que crowding faz é explicar **tail risk**: papéis com maior exposição sofrem drawdowns relativamente maiores em períodos de distress, e essa exposição explica por que certos hedge funds quebram juntos.

Ou seja, crowding se comporta como um **prêmio de risco com skew negativo**. Shortar crowding incondicionalmente = vender vol. Sangra devagar, morre rápido, e o backtest vai parecer bom até o pedaço de amostra que contém o stress.

A medida preferida deles é **days-ADV**: holdings agregados de hedge funds divididos pelo volume médio diário. Subiu de ~18 dias em 2004 para ~26 em 2016. Guarde isso — Seção 4.3 explica por que essa normalização resolve de graça um bug do seu pipeline.

### 2.2 O contraditório

**Barroso, Edelen & Karehnke (2022), *Crowding and Tail Risk in Momentum Returns*, JFQA 57(4):1313–1342.**

Modelam crowding em momentum e mostram que crowding só gera tail risk se os arbitradores **ignoram** o efeito de feedback; se eles condicionam racionalmente, não gera. Empiricamente encontram relação **negativa** entre proxies de crowding construídos com holdings institucionais e crash risk esperado. Concluem lançando dúvida teórica e empírica sobre crowding como fonte autônoma de tail risk.

Isto não é ruído bibliográfico — é uma disputa aberta entre dois papers top-3 sobre exatamente a sua pergunta. **Você não pode ancorar a tese do case em "crowding é ruim" e depois ser perguntado sobre BEK.** Pode, e deve, citar a disputa como evidência de que você leu.

### 2.3 O que a literatura sustenta de fato

**Dasgupta, Prat & Verardo (2011), *Institutional Trade Persistence and Long-term Equity Returns*, JF 66(2):635–653.**

A distinção que resolve tudo: **herding de um trimestre prevê retorno positivo no curto prazo; persistência multi-trimestral prevê retorno negativo no longo prazo.** Ações persistentemente vendidas ao longo de três a cinco trimestres superam as persistentemente compradas, com o efeito aparecendo depois de cerca de dois anos. O efeito não é subsumido por retornos passados nem por outras características, concentra-se em papéis menores, e é **mais forte onde a propriedade institucional é maior**.

O companion teórico — **DPV (2011), *The Price Impact of Institutional Herding*, RFS 24:892–925** — dá o mecanismo: gestores com career concerns imitam trades passados endogenamente, interagindo com prop traders e dealers com poder de mercado; a imitação empurra preço, e a reversão vem depois.

Isso é o que você quer: **um mecanismo econômico nomeado, uma direção assinada, um horizonte especificado, e uma condição de ativação (persistência, não nível).**

### 2.4 A tensão que vira o gráfico central do memo

Junte três resultados:

| fonte | horizonte | sinal | condicionante |
|---|---|---|---|
| Sias (2004), Yan & Zhang (2009) | 1 trimestre | **+** | demanda de instituições de horizonte curto |
| Edelen, Ince & Kadlec (2016, JFE) | ~1 ano | **−** | demanda institucional agregada vs. anomalias |
| Dasgupta, Prat & Verardo (2011) | ~2 anos | **−** | persistência de 3–5 trimestres |
| Brown, Howard & Lundblad (2022) | incondicional | **+** (prêmio) | nível de crowding, com cauda esquerda |

O fator não é um número — é uma **estrutura a termo de posicionamento**. Fluxo no curto prazo, estoque acumulado no longo prazo, e um ponto de cruzamento que você estima. Isso responde diretamente ao critério de avaliação *"Is there a coherent story for why this signal should carry information? Did you consider alternatives?"* — e é honesto, porque a troca de sinal está prevista **antes** de você rodar.

---

## 3. A reformulação: o generativo é o estimador, não o alfa

### 3.1 O problema real que você tem, e que a literatura mal trata

No dia de decisão `d` dentro do filing season, você observa um **subconjunto** de filers, e a seleção **não é aleatória**. Christoffersen, Danesh & Musto documentam atraso estratégico: quem tem algo a proteger entrega tarde. Sua própria curva X3 mede isso — R² acumulado 0,5% → 3,4% → 51% → 63% em D+15/30/45/60.

Consequência: usar apenas o que chegou é PIT-correto mas **enviesado por seleção**. Usar tudo é lookahead. Nenhuma das duas está certa.

**A terceira via é a distribuição condicional.** Para cada filer `m` que ainda não entregou, você tem uma distribuição preditiva do que ele está segurando, condicionada em (i) o histórico dele, (ii) a deriva passiva de preços desde o report date, e (iii) **o que os filers parecidos com ele que já entregaram fizeram neste trimestre**. O item (iii) é o que transforma extrapolação em nowcast genuíno, e é exatamente o objeto que o GAN estimaria.

Isso não é decoração. É a correção de um viés real, mensurável, e que ninguém mais no processo seletivo vai ter identificado.

### 3.2 A âncora econômica: latent demand com mean reversion

**Koijen & Yogo (2019), *A Demand System Approach to Asset Pricing*, JPE 127(4):1475–1515.**

O objeto central deles é a *latent demand*: a parte da posição de um investidor num papel que não é explicada por preço e características. Dois fatos empíricos deles são a espinha dorsal do que você vai construir:

1. **Latent demand é persistente mas reverte à média**, com velocidade **específica por investidor**.
2. Estimando a velocidade de reversão por investidor e agregando entre investidores, você obtém uma **previsão de quanto a demanda por um papel vai mudar no próximo trimestre** — e isso **gera variação previsível no cross-section de retornos**.

Traduzindo para engenharia: um AR(1) hierárquico com `ρ_m` por filer e shrinkage para a média do pool. Estimação em forma fechada. Trinta linhas de código. É o membro identificado, com microfundamento e amostra suficiente, da mesma família de modelos que o GAN.

**Koijen, Richmond & Yogo (2024), *Which Investors Matter for Equity Valuations and Expected Returns?*, ReStud 91(4):2387–2424**, adiciona duas coisas que você usa direto:

- **Quem importa.** Os 30 maiores institucionais administram cerca de um terço do mercado americano e explicam **4%** da variância cross-seccional de retornos. Grandes institucionais são buy-and-hold e não giram entre papéis em stress. Households e institucionais **menores** explicam mais. Isto é validação independente do seu filtro `M*` de gestores pequenos/ativos, e é uma frase que vale ouro numa defesa técnica.
- **Como encolher.** Eles usam penalidade `λ_{i,t} = λ|N_{i,t}|^{−ξ}` com cross-validation: o shrinkage **cai** quando o investidor tem mais posições. Copie essa forma funcional. Filer com 30 papéis é encolhido muito; filer com 900, quase nada.

### 3.3 A segunda métrica que sai de graça: a variância

Quando você tem a distribuição preditiva da demanda por papel, tem **duas** quantidades, não uma:

- **média** → sinal direcional (a previsão de demanda de Koijen-Yogo)
- **variância** → **fragilidade**

**Greenwood & Thesmar (2011), *Stock price fragility*, JFE 102(3):471–490.** Um ativo é frágil quando seus donos coletivamente precisam comprar ou vender ao mesmo tempo. A fragilidade depende de três coisas: **concentração da propriedade, volatilidade dos choques de liquidez dos donos, e correlação entre eles**. Formalmente, é a variância da demanda não-fundamental agregada. Eles mostram que **fragilidade prevê volatilidade futura com força, acima dos determinantes conhecidos**, e que a volatilidade é proporcional à raiz quadrada da fragilidade. Co-fragilidade prevê comovimento cross-stock.

Note a elegância: **fragilidade é literalmente a variância da sua distribuição preditiva agregada.** Você não estima duas coisas — estima uma e lê dois momentos. Isso é a versão honesta de "modelar a distribuição condicional da carteira", e tem paper em JFE desde 2011.

Cuidado com o que ela **não** faz: G&T prevê **volatilidade**, não retorno. Use fragilidade para dimensionar, neutralizar e condicionar — nunca como perna direcional sozinha.

---

## 4. O fator proposto

### 4.1 Notação

Para filer `m`, papel `i`, trimestre `t`:

- `s_{m,i,t}` = shares detidas. Filtro obrigatório: `putCall IS NULL` e `sshPrnamtType = 'SH'`.
- `ADV_{i,t}` = volume médio diário em dólares nos 60 pregões anteriores ao report date (Yahoo).
- `M*` = subconjunto de gestores selecionado endogenamente: churn ratio alto ∩ HHI alto ∩ AUM 13F abaixo da mediana. Justificativa: Yan & Zhang (2009), Antón-Cohen-Polk (2021), e o resultado de KRY de que os 30 maiores explicam 4% da variância.

### 4.2 As duas pernas

**Perna A — FLUXO (horizonte curto, sinal positivo)**

```
F_{i,t} = Σ_{m ∈ M*} ( s_{m,i,t} − s_{m,i,t−1} ) · P_{i,t} / ADV_{i,t}
```

"Dias de volume comprados líquido pelos gestores selecionados neste trimestre." Previsão: positivo em h = 1–3 meses. Suporte: Sias (2004), Yan & Zhang (2009), Wermers (1999).

**Perna B — ESTOQUE × PERSISTÊNCIA (horizonte longo, sinal negativo)**

```
C_{i,t} = Σ_{m ∈ M*} s_{m,i,t} · P_{i,t} / ADV_{i,t}          (days-ADV, à la BHL)
K_{i,t} = # trimestres consecutivos com F_{i,·} > 0            (persistência, à la DPV)

B_{i,t} = C_{i,t} · 1{ K_{i,t} ≥ 3 }
```

Previsão: **negativo** em h = 12–24 meses, e **apenas** quando `K ≥ 3`. Suporte: DPV (JF 2011) para a direção e o corte de 3–5 trimestres; BHL (RFS 2022) para a normalização por liquidez; DPV (RFS 2011) para o mecanismo.

O `1{K ≥ 3}` é o que separa o seu fator de "short crowded incondicional", que a Seção 2.1 mostrou estar do lado errado do prêmio. **Declare isso explicitamente no memo.** É o seu melhor parágrafo.

**Fator combinado.** Não force uma combinação linear. Rode as duas pernas separadas e **o gráfico central do memo é IC(h) para h = 1…24 meses, mostrando o cruzamento de sinal.** Isso é uma previsão falsificável registrada antes do teste; Edelen-Ince-Kadlec (2016) prevê o mesmo cruzamento por outro caminho. Você ganha nos dois cenários: se cruza, confirmação; se não cruza, você mediu algo que a literatura diz que deveria acontecer e não aconteceu, o que é resultado.

### 4.3 Por que a normalização por ADV é um ganho de engenharia, não só de teoria

Você teve o problema de `IO > 150%` e o culpou de shares outstanding. Normalizar por **ADV em vez de shares outstanding elimina a dependência de SO inteiramente**:

- Yahoo só tem SO confiável a partir de ~out/2015, e não é point-in-time.
- SO tem o problema de dual class, que é parte do seu bug.
- ADV vem de preço × volume, que você já tem, é PIT por construção, e é diário.
- E, de quebra, é **a medida que BHL declaram como a melhor** entre as que testaram, porque combina tamanho da posição com liquidez do papel.

Isso troca um problema de dado por um ganho de fidelidade à literatura. Faça a troca.

Cuidado único: use volume **ajustado** para splits, consistente com o preço ajustado, e prefira volume em dólares a volume em shares.

### 4.4 A camada de nowcast, definida operacionalmente

Na data de decisão `d`, para o trimestre `t`:

- `O(d)` = filers com `accepted_date ≤ d`. `U(d)` = os que faltam.
- Para `m ∈ U(d)`, decomponha a variação em **deriva passiva** (mecânica, dada por preços — nada a estimar) e **trade ativo** `a_{m,i,t}`.
- Modele o trade ativo com AR(1) hierárquico e um termo de peer:

```
â_{m,i,t} = ρ̂_m · a_{m,i,t−1} + λ̂_m · PeerFlow_{g(m),i,t}(d)
```

onde `g(m)` é o cluster de estilo de `m` (do seu clustering tipo Bushee) e `PeerFlow(d)` usa **só** os filers de `O(d)`. Coeficientes com shrinkage no formato KRY: `ρ̂_m = (n_m ρ̂^OLS_m + κ|N_m|^{−ξ} ρ̄)/(n_m + κ|N_m|^{−ξ})`.

- Variância preditiva por filer + correlação cross-filer dos resíduos ⇒ **Var(F_{i,t} | info(d))** = a sua fragilidade à la G&T.

Tudo com estimação em forma fechada, tudo auditável linha a linha numa defesa técnica de 60 minutos.

### 4.5 Como avaliar o nowcast — três testes, todos PIT

1. **Acurácia bruta vs. o baseline que importa.** Compare contra **duas** referências: zero-trade (`a = 0`) e deriva passiva pura. Métrica: rank IC entre `â` imputado e o realizado quando o filing chega. **Se você não bater zero-trade com folga, reporte isso.** Você estará replicando a Tabela 1 de Scholl et al. com dados trimestrais, o que é um resultado nulo bem medido e um parágrafo forte no memo — do mesmo tipo do seu X4.

2. **Valor marginal em dias.** IC e alfa do fator como função de `d ∈ {D+15, …, D+90}`, com e sem imputação. A métrica de sucesso não é "o modelo é bom", é **"quantos dias antes eu atinjo 90% do IC terminal"**. Ninguém mais no processo consegue produzir esse gráfico, porque exige timestamp por versão.

3. **Teste de seleção.** Os `ΔF` dos early filers são estatisticamente diferentes dos late filers? Se sim, a imputação corrige um viés real e você tem que dizer qual. Se não, a imputação é irrelevante e você tem que dizer isso também.

### 4.6 Critérios de kill, registrados antes

Escreva isto no README **antes** de rodar. É o que separa pesquisa de data mining, e o entrevistador vai reconhecer.

- Melhora de RMSE da imputação sobre zero-trade `< 5%` ⇒ camada de nowcast sai do headline e vira resultado nulo reportado.
- Perna A com `|t| < 2` sobre FF6 em h=1 ⇒ perna A cai.
- Cruzamento de sinal em h não aparece ⇒ reporta, não reespecifica.
- Alfa que desaparece com custo de 20 bps one-way ⇒ reporta o break-even em bps e para de defender o número bruto.
- Amostra efetiva: ~40 trimestres independentes. Aplique o corte de Harvey-Liu-Zhu: `|t| > 3` para reivindicar descoberta, não 2.

---

## 5. Alternativas consideradas e rejeitadas — material direto para o memo

O enunciado avalia explicitamente *"Did you consider alternatives?"*. Esta tabela é a resposta.

| alternativa | por que fora |
|---|---|
| **GAN/diffusion sobre `p(w_t \| ·)`** | Existe (Scholl et al., ICAIF '25). Zero-Trade empata em replicação e **ganha 3× no erro de turnover**, que é a métrica de nowcast. Os autores não reivindicam retorno. Custo de 20h num take-home de 48h com critérios em PIT e data engineering. → vai para "next steps", com protocolo de avaliação. |
| **Short crowding incondicional** | BHL (RFS 2022): crowded tem os **maiores** retornos médios. Shortar = vender prêmio de cauda. E BEK (JFQA 2022) contradiz até o canal de tail risk. Insustentável como tese. |
| **Fragilidade G&T como perna direcional** | G&T prevê **volatilidade**, não retorno. Entra como variância, sizing e neutralização — nunca como sinal de direção. |
| **Demand system completo de Koijen-Yogo** | Precisa de IV com universo de investimento exógeno por mandato, e a identificação está em disputa ativa (Fuchs-Fukuda-Neuhann 2025 vs. Koijen-Yogo 2025). Entrar nessa briga num take-home é escolher um flanco. Uso apenas os dois fatos empíricos robustos: persistência com mean reversion, e quem importa. |
| **Copycat / clone de 13F** | Frank-Poterba-Shackelford-Shoven (2004): o lag corrói a maior parte da vantagem. Serve de baseline, não de fator. |
| **Comomentum (Lou & Polk)** | Mede crowding por correlação de retornos, não por holdings. Fora do escopo "13F factor". |
| **Fire sales / flow-induced trading (Coval-Stafford; Lou)** | Exige TNA mensal por fundo. E Wardlaw (2020, JF) mostrou que a medida padrão é mecanicamente função do retorno realizado. Cortado por dado **e** por metodologia. |
| **Nowcast do ΔIO agregado como fator** | Testado e rejeitado por você mesmo (X4). Lewellen (2011): instituições em agregado *são* o mercado; ΔIO agregado é ruído por construção. Isso é força do memo, não fraqueza. |

---

## 6. As três coisas que eu construiria em seguida (rascunho da seção do memo)

**1. Nowcast generativo condicional via score-based diffusion com máscara.**
Não GAN — **CSDI** (Tashiro et al., NeurIPS 2021), porque nowcast de holdings é imputação com padrão de missingness observado, não geração livre. Condicionamento natural: o subconjunto de filers já entregue, a deriva passiva, e o cluster de estilo. Protocolo de avaliação declarado ex-ante: CRPS contra o filing realizado, com zero-trade e deriva passiva como pisos, e o critério de sucesso sendo **dias ganhos de disponibilidade do fator**, não acurácia. Justificativa para não ter feito agora: a Tabela 1 de Scholl et al. estabelece que o ganho sobre o baseline trivial é da ordem de 3% na métrica de replicação e negativo na de turnover, com dados mensais e 120k observações — não é onde o retorno marginal de 48h está.

**2. Retorno de deslistagem para matar o survivorship do painel Yahoo.**
Sua maior vulnerabilidade técnica declarada. A Official List of Section 13(f) Securities da SEC te dá universo PIT e permite **medir** o buraco, mas não te dá preço de nome morto. O próximo passo é CRSP delisting returns ou uma reconstrução via 25-NSE/Form 25 + último preço negociado.

**3. Perna short observável, via short interest da FINRA.**
Jiao, Massa & Zhang (2016, JFE): cruzar Δholdings de hedge funds com Δshort interest separa demanda informada de hedge; long informado − short informado ≈ 10% a.a., e prevê fundamentos. Ambos os inputs são grátis. É a única forma de o 13F, que é long-only por construção, ganhar um lado bearish direto.

---

## 7. Bibliografia

**Generativo sobre holdings**
- Scholl, Mahfouz, Calinescu & Farmer (2025), *Learning to Manage Investment Portfolios beyond Simple Utility Functions*, ICAIF '25, arXiv:2510.26165.
- Tashiro, Song, Song & Ermon (2021), *CSDI: Conditional Score-based Diffusion Models for Probabilistic Time Series Imputation*, NeurIPS 34.
- *Diffusion Models in Finance: A Survey* (2026), arXiv:2608.12583.
- Wiese, Knobloch, Korn & Kretschmer (2020), *Quant GANs*, Quantitative Finance 20(9).

**Crowding**
- Brown, Howard & Lundblad (2022), *Crowded Trades and Tail Risk*, RFS 35(7):3231–3271.
- Barroso, Edelen & Karehnke (2022), *Crowding and Tail Risk in Momentum Returns*, JFQA 57(4):1313–1342.
- Sias, Turtle & Zykaj (2016), *Hedge Fund Crowds and Mispricing*, Management Science 62(3):764–784.
- Greenwood & Thesmar (2011), *Stock price fragility*, JFE 102(3):471–490.

**Persistência, herding e reversão**
- Dasgupta, Prat & Verardo (2011), *Institutional Trade Persistence and Long-term Equity Returns*, JF 66(2):635–653.
- Dasgupta, Prat & Verardo (2011), *The Price Impact of Institutional Herding*, RFS 24(3):892–925.
- Edelen, Ince & Kadlec (2016), *Institutional investors and stock return anomalies*, JFE 119(3):472–488.
- Lakonishok, Shleifer & Vishny (1992), *The impact of institutional trading on stock prices*, JFE 32(1):23–43.

**Demanda, elasticidade e quem importa**
- Koijen & Yogo (2019), *A Demand System Approach to Asset Pricing*, JPE 127(4):1475–1515.
- Koijen, Richmond & Yogo (2024), *Which Investors Matter for Equity Valuations and Expected Returns?*, ReStud 91(4):2387–2424.
- Gabaix & Koijen (2021), *In Search of the Origins of Financial Fluctuations: The Inelastic Markets Hypothesis*, NBER WP 28967.
- Fuchs, Fukuda & Neuhann (2025) e Koijen & Yogo (2025) — a disputa sobre identificação do estimador cross-seccional.

**Seleção de gestor**
- Yan & Zhang (2009), *Institutional Investors and Equity Returns: Are Short-term Institutions Better Informed?*, RFS 22(2):893–924.
- Antón, Cohen & Polk (2021) / Cohen, Polk & Silli (2010), *Best Ideas*.
- Bushee (1998, 2001) — taxonomia transient / dedicated / quasi-indexer.
- Gaspar, Massa & Matos (2005) — churn ratio.

**Ceticismo obrigatório**
- Lewellen (2011), *Institutional investors and the limits of arbitrage*, JFE 102(1):62–80.
- Wardlaw (2020), *Measuring Mutual Fund Flow Pressure as Shock to Stock Returns*, JF 75(6):3221–3243.
- Harvey, Liu & Zhu (2016), *…and the Cross-Section of Expected Returns*, RFS 29(1):5–68.
- Frank, Poterba, Shackelford & Shoven (2004) — copycat funds e a corrosão pelo lag.

**Disclosure e timing**
- Agarwal, Jiang, Tang & Yang (2013), *Uncovering Hedge Fund Skill from the Portfolio Holdings They Hide*, JF 68(2):739–783.
- Christoffersen, Danesh & Musto — atraso estratégico no 13F.
- Jiao, Massa & Zhang (2016), *Short selling meets hedge fund 13F*, JFE 122(3):544–567.

---

## 8. Uma frase para levar

> O generativo não é o fator. O fator é a estrutura a termo do posicionamento — fluxo positivo no curto prazo, estoque persistente negativo no longo, com a condição de ativação em persistência e não em nível. O generativo é o estimador que corrige o viés de seleção do filing season e torna esse fator utilizável semanas antes, e o valor dele se mede em **dias ganhos**, não em acurácia.
