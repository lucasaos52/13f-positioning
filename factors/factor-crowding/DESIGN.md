# factor-crowding — do posicionamento por ação ao posicionamento por FATOR

**Nota de desenho estruturada** — organizando as ideias brutas em um programa de
pesquisa com camadas, sinais pré-registrados, literatura e critérios de morte.
Construído sobre a infraestrutura e as lições do projeto 13F (agosto/2026).

---

## 0. O programa em uma figura

```
CAMADA 1 — CENSO (13F, trimestral, filed_date)
  exposição fatorial agregada dos gestores → quão crowded está cada FATOR
       │
CAMADA 2 — NOWCAST (retornos diários, entre divulgações)
  correlação intra-fator (comomentum) → o crowding "ao vivo", calibrado no censo
       │
CAMADA 3 — SINAIS (4, cada um com direção pré-registrada)
  S1 nível de crowding → retorno/cauda do fator
  S2 Δcrowding (fluxo PARA o fator) → continuação
  S3 gatilho de unwinding (evento) → de-risk/short do fator
  S4 dispersão de correlação dentro do fator → seleção intra-perna
```

A resposta ao problema central levantado ("não consigo inferir nada entre duas
divulgações"): **o censo dá o nível verdadeiro trimestral; a correlação de
retornos dá o pulso diário; a calibração de um contra o outro é exatamente a
máquina da âncora do nowcasting (X3), aplicada a fatores.**

---

## 1. Por que este projeto é viável AGORA (o que já existe)

| peça necessária | onde já está | status |
|---|---|---|
| Exposições fatoriais por ação (matriz B) | `drift_fluxo_rotacao` (size, mom, beta, vol — PIT, trailing) | ✅ rodando |
| Decomposição do book do gestor em fator vs nome (BΓ vs Δ⊥) | DFR, projeção por gestor | ✅ validada |
| Fatores-portfólio canônicos com retornos diários | `factors/run_demo` (mom, low-vol, reversal) + extensões | ✅ motor pronto |
| Capacidade de cesta (days-ADV de um portfólio) | máquina do NMF (`basket_adv`) | ✅ |
| Fluxo implícito por gestor (estresse) | `fire_calendar` (validado t=+13,8) | ✅ |
| Relógio PIT por filed_date + borda irregular | base curada + âncora X3 | ✅ |
| Motor de backtest com rebal em datas ARBITRÁRIAS | `Portfolio.rebalance(idxs)` aceita qualquer vetor de índices — **o receio de "não dar pra usar a estrutura" é infundado**: entradas event-driven = passar os índices dos dias de gatilho | ✅ |
| Painel de correlação intra-cesta | trivial com os retornos diários já cacheados | 1 dia |

O que NÃO existe e é premissa: **B/M e quality com história longa** (fundamentals
grátis ≈ 2019+). Decisão: começar com as variáveis canônicas disponíveis
(size, momentum, beta, low-vol, liquidez) — 5 fatores testáveis com 12 anos —
e declarar value/quality como extensão 2019+ (EDGAR companyfacts).

---

## 2. Literatura — o que já está reivindicado e o que está aberto

| trabalho | o que fizeram | relação com as ideias |
|---|---|---|
| **Lou & Polk — Comomentum (RFS 2022)** | correlação parcial entre ações da perna de momentum como proxy de arbitragem crowded; alta → retorno futuro de momentum baixo e cauda pior | é EXATAMENTE a ideia 3/4 (monitorar correlação entre divulgações). Publicada — vira a nossa Camada 2, citada, não "inventada" |
| **MSCI Integrated Factor Crowding Model (2018+)** | produto comercial: spread de valuation, correlação par-a-par, short interest, holdings — placar diário de crowding por fator | prova que o programa inteiro tem demanda; a versão nossa é a reprodução com censo 13F próprio (que eles não abrem) |
| **Barroso, Edelen & Karhunen (2017+)** | com 13F: instituições REDUZEM loading em momentum antes de crashes | valida a ideia 1 (loadings fatoriais agregados de 13F carregam informação) e dá a direção do S2 |
| **EFMA 2022 "Following the crowd"** | crowding de ANOMALIAS via 13F (estratégias pré-definidas) | vizinho do censo; nosso diferencial: PIT por filed_date + capacidade (days-ADV da cesta) + universo de medição escolhido |
| **Khandani & Lo (2007)** | o quant quake como unwinding coordenado | o mecanismo do S3 |
| **Ehsani & Linnainmaa (factor momentum)** | fatores têm momentum próprio | confound OBRIGATÓRIO: qualquer sinal de crowding precisa sobreviver ao controle de retorno passado do próprio fator |
| **Arnott et al. vs Asness et al. (timing de fatores)** | timing por valuation funciona (Arnott) vs é fraco/raro (Asness) | calibra a expectativa: timing de fator é difícil; ~50 trimestres × 5 fatores = pouquíssima amostra na dimensão tempo |
| Nossos resultados | NMF: estratégias lotadas = defensivas; DFR: rotação = 2% da variância; lição "estado sem seta" | ver §5 e §7 |

**O que parece genuinamente aberto**: o censo de crowding fatorial construído
com (i) relógio PIT real, (ii) painel de gestores escolhido por QUALIDADE DE
MEDIÇÃO (não por esperteza), (iii) capacidade em days-ADV da cesta, e (iv) o
nowcast calibrado contra o censo — o pacote, não as peças.

---

## 3. Camada 1 — o censo de posicionamento fatorial

### 3.1 A exposição de cada gestor

Para cada gestor i com book w_i (pesos), na data de decisão:

```
x_i = B' w_i^a          (k×1: exposição ATIVA do gestor a cada fator)
```

com B = [size, mom 12-1, beta, vol, iliquidez] padronizada cross-section
(ranks), w_i^a = peso ativo (w − w_mkt). Nada novo: é a projeção do DFR.

### 3.2 A ideia 1, reformulada com a lição do projeto

A proposta original: "filtrar 20% dos fundos com pouca (ou muita?) posição
idiossincrática". O projeto já provou que filtrar eleitorado por ESPERTEZA
destrói sinal (3 experimentos). Mas aqui o filtro tem outra função — é filtro
de **qualidade de medição**, não de skill:

- **Painel A — alocadores de fator** (baixa fração idiossincrática: var(BΓ)/var(book)
  alta, computável pela decomposição do DFR): os books DELES são apostas de
  fator quase puras → o censo lido neles tem pouco ruído de stock-picking;
- **Painel B — stock pickers** (alta fração idio): a exposição fatorial deles é
  SUBPRODUTO não-intencional → um crowding que aparece nos DOIS painéis é
  estrutural; um que só aparece no A é alocação deliberada.

**Pré-registro**: reportar o censo nos dois painéis + todos os filers. A
divergência entre painéis é informação (deliberado vs acidental), não escolha
de qual número mostrar.

### 3.3 As quatro métricas de crowding por fator (por trimestre)

```
C1 nível:      tilt agregado = Σ_i AUM_i · x_i,f  / Σ AUM      (o censo)
C2 fluxo:      ΔC1 entre trimestres                            (quem está entrando)
C3 capacidade: days-ADV da cesta do fator ponderada pelo tilt   (teorema do macaco:
               ADV no denominador → comparar SEMPRE vs a própria história, não
               cross-fator cru)
C4 concentração: HHI de quem carrega a aposta (poucos gestores grandes = frágil)
```

Tudo em datas de decisão D+50 por filed_date; séries 2013→2026 (~50 pontos por
fator — a limitação de amostra é ESTRUTURAL e vai escrita em todo resultado).

---

## 4. Camada 2 — o nowcast entre divulgações (a solução do problema central)

O insight da ideia 3 é publicável e publicado (Lou-Polk): **a correlação
intra-perna do fator é observável DIARIAMENTE e proxy de crowding**. O nosso
upgrade é a calibração:

```
comovimento_f(t) = correlação média par-a-par (janela 63d) das ações da perna
                   long do fator f, PARCIAL ao mercado (removê-lo primeiro —
                   senão mede beta, não crowding)
nowcast: regressão expansiva  C1_f(próximo censo) ~ comovimento_f(hoje)
         — a mesma estrutura da âncora X3, com o censo como verdade trimestral
```

Bônus da borda irregular: entre D+0 e D+50 o censo PARCIAL dos filers já
revelados atualiza o nowcast filing a filing (máquina X3 pronta).

---

## 5. Camada 3 — os quatro sinais (com as lições já pagas)

**Aviso estrutural (lição "estado sem seta")**: crowding NÍVEL não tem direção
own — o projeto provou isso 3×. Cada sinal abaixo declara sua seta ANTES, e a
S1 é primariamente uma previsão de RISCO, não de retorno.

### S1 — Nível de crowding → cauda do fator (defensivo)
- **Tese**: fator crowded (C1 alto vs própria história + C3 apertado + C4
  concentrado) tem cauda esquerda pior — não necessariamente retorno médio
  menor (Lou-Polk acham retorno menor para momentum; Barroso acham redução
  defensiva das instituições).
- **Pré-registro**: vol e drawdown do fator sobem com crowding defasado;
  retorno médio = sem previsão forte (teste duplo, honesto).
- **Uso**: overlay de risco no combo existente (de-risk da perna exposta ao
  fator crowded), não aposta direcional.
- **Mata-se**: se nem a cauda responder, o censo não informa risco e S1 morre.

### S2 — ΔCrowding (fluxo PARA o fator) → continuação
- **Tese**: a lei empírica do projeto inteiro — fluxo prevê continuação, nível
  não. Capital entrando no fator (C2>0) → retorno do fator continua no
  trimestre seguinte (e é o lado que Barroso documentam ao contrário: saída
  institucional antecipa crash de momentum).
- **Confound obrigatório**: factor momentum (Ehsani-Linnainmaa) — C2 correlaciona
  com retorno passado do fator; a regressão de controle decide se há conteúdo
  além.
- **Mata-se**: se C2 não sobreviver ao controle de retorno passado do fator,
  é factor momentum requentado — escrito com esse nome.

### S3 — Gatilho de unwinding (event-driven) — a ideia 2
- **Tese**: comovimento (Camada 2) saltando >2σ vs própria história EM fator
  com censo crowded = desmonte em curso (Khandani-Lo) → sair/short do fator
  por N semanas, hedge no índice.
- **Desenho**: event-driven de verdade — os dias de gatilho viram os índices
  de rebal do motor existente (`rebalance(idxs)` aceita); N fixado a priori
  (ex.: 8 semanas), sem otimização.
- **Assimetria pré-registrada**: gatilho só VENDE exposição (de-risk). A versão
  "compra o fator mais esticado" fica proibida na v1 — é a que exige acertar
  reversão, e o projeto já mediu como reversão é rara/lenta.
- **Mata-se**: contagem esperada de gatilhos ~5-10 em 12 anos → qualquer
  resultado é anedótico por construção; reporta-se como estudo de eventos
  com IC largo, nunca como Sharpe.

### S4 — Dispersão de correlação intra-fator → seleção de nomes (a ideia 4)
- **Tese**: dentro da perna do fator, os nomes mais correlacionados ao núcleo
  são os detidos "por arbitragem" (saem juntos no desmonte); os menos
  correlacionados são detidos por razões próprias → **short os mais correl,
  long os menos, DENTRO da perna** — cross-section, onde temos largura
  estatística (centenas de nomes × 50 tri, não 5 fatores × 50).
- É o único dos quatro com breadth de verdade → o único com chance de Sharpe
  próprio. Roda no protocolo padrão dos 17 (quintis, NW, teorema do macaco:
  correlação com beta/size é mecânica → residualizar).
- **Mata-se**: pipeline padrão, delta pareado contra o fator puro.

---

## 6. Plano de execução (fases, esforço, entregável)

| fase | o quê | esforço | entregável |
|---|---|---|---|
| F1 | Censo: x_i por gestor, painéis A/B, C1-C4 por fator, 2013-2026 | 1 dia | série histórica + o gráfico "quão crowded está cada fator hoje" (valor de memo mesmo sem alfa) |
| F2 | Nowcast: comovimento parcial diário + calibração vs censo (R² estilo X3) | 1 dia | curva de acumulação fator-nível |
| F3 | S2 e S4 no protocolo padrão (os dois com largura estatística) | 1 dia | tabelas com NW + confound de factor momentum |
| F4 | S1 como overlay de risco no combo 0,80 (delta pareado) | ½ dia | melhora ou não, com número |
| F5 | S3 estudo de eventos (contagem, CI largo, sem Sharpe) | ½ dia | anedotário honesto |

Ordem deliberada: medir → nowcastar → cross-section → overlay → eventos.
O valor mínimo garantido é F1+F2 (o placar de crowding com nowcast diário — a
versão gratuita e auditável do produto da MSCI); os sinais são upside.

---

## 7. Riscos e lições aplicadas (pré-pagas pelo projeto)

1. **Amostra na dimensão tempo**: 5 fatores × 50 trimestres. S1/S2/S3 são
   inferência pobre por construção; só S4 tem breadth. Dito em toda tabela.
2. **Estado sem seta**: S1 é risco, não retorno — aprendido 3× (M1, sig_share,
   SSI).
3. **Factor momentum é o confound de tudo**: C2 e comovimento correlacionam
   com o retorno do próprio fator; controle obrigatório em todos os sinais.
4. **Teorema do macaco nas métricas**: C3 (days-ADV) é mecânico → só vs
   própria história; correlação intra-perna carrega beta → parcial ao mercado.
5. **Filtro de gestores**: só como lente de medição (painéis A/B reportados
   juntos), nunca como seleção de espertos — 3 reprovações já pagas.
6. **Timing de fatores é um cemitério famoso** (Asness): a barra de ceticismo
   é mais alta que a dos sinais cross-section; por isso S4 é a aposta
   principal e S1-S3 são secundários.
7. **B sem value/quality longos**: fatores testados = size, mom, beta, vol,
   iliquidez; value/quality 2019+ como extensão declarada.

## 8. Critérios de morte globais

- F1: se C1 dos painéis A/B divergirem sem estrutura (corr ~0 entre painéis),
  o censo não mede um objeto estável — parar e reportar;
- F2: se o comovimento não previr o censo seguinte (R² ~0), a Camada 2 cai e
  os sinais diários morrem juntos;
- S1-S4: cada um com o kill listado; nenhum sobrevive por "quase".
```
