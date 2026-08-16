# original_methods — brainstorm vetado contra a literatura

Regra do brainstorm: só valem ideias que (a) têm mecanismo econômico enunciável
em duas frases, (b) foram vetadas contra a literatura (linhagem citada, gap
identificado), e (c) exploram algo que **só a nossa base faz** — timestamps e
versões reais por filing, sucessão de CIKs, borda irregular validada (âncora:
51% do ΔIO em D+45), decomposição trading × composição do universo. Originalidade
aqui = recombinação com gap documentado, nunca "achei que inventei" (a lição da
"periferia de rede" (Pozzi-Di Matteo-Aste 2013 + Mantegna 1999),
não citados).

---

## ★1. Death Supply — a pressão de liquidação dos gestores que morrem

**Mecanismo.** Quando um gestor deixa de existir, o book dele **tem** que ser
liquidado — não é decisão de alocação, é oferta forçada e inelástica, espalhada
pelos meses seguintes à última fotografia 13F. Prevê: pressão negativa nos
nomes onde o morto era relevante vs a liquidez (days-ADV do morto), com
**reversão** depois — a assinatura Coval-Stafford, mas com morte de gestor no
lugar de resgate de fundo.

**Linhagem.** Coval & Stafford (2007) — fire sales por FLUXO de mutual funds
(exige dados de fluxo); Edmans-Goldstein-Jiang e a demolição de Wardlaw (2020)
sobre a medida; anedotas de liquidações de hedge funds. **Gap**: ninguém
sistematizou a *cessação de filing 13F* como evento de oferta — provavelmente
porque implementar isso ingenuamente é um desastre: a maioria dos "mortos" são
**renomeações e reorganizações** (Priceline→Booking do lado dos filers), que
geram falsas mortes.

**Por que só nós**: a máquina de sucessão de CIKs do crowdflow (spans HR-only,
Jaccard de books, famílias) separa morte verdadeira de renomeação — o
falso-positivo que mataria o sinal em qualquer implementação naive. E a data da
ÚLTIMA aceitação é conhecida com timestamp real.

**Construção.**
```
morte(i) = último 13F-HR do filer i (sem sucessor detectado, sem família ativa)
oferta_forçada(j, t) = Σ_{i mortos em [t-2q, t]} shares_ij(último book) / ADV_j
sinal: short/underweight os altos por 1-2 tri; long na reversão depois
falsificação: placebo com renomeados (sucessor detectado) → deve dar ZERO
```
**Modo de falha**: morte é endógena (gestores morrem APÓS books ruins —
condicionar na performance do book antes); amostra de mortes ~centenas.

---

## ★2. Delay Surprise — a demanda de quem atrasou fora do padrão

**Mecanismo.** Christoffersen-Danesh-Musto: o atraso de filing é **escolha
estratégica** para proteger trades futuros — não incapacidade operacional. Logo
o atraso *anômalo* (vs o histórico do próprio filer) é um sinal de que o book
corrente contém algo que vale esconder. As posições **novas/aumentadas** de um
gestor que sempre arquiva em D+30 e desta vez arquivou em D+45 devem carregar
mais informação que as do mesmo gestor em trimestre normal.

**Linhagem.** Christoffersen et al. (2018) documentam o comportamento;
Agarwal et al. (2013) o extremo dele (confidential treatment paga ~12m); a
nossa busca não encontrou **nenhum sinal cross-sectional de atraso-surpresa**.
Gap limpo.

**Por que só nós**: exige a distribuição histórica de atrasos POR FILER com
datas reais — o dado que bases comerciais descartam e que a nossa carrega por
construção.

**Construção.**
```
surpresa_i,t = (delay_i,t − mediana_delay_i,[t-8q,t-1]) / IQR_i   [PIT: só passado]
sinal(j,t) = Σ_i 1{surpresa_i,t > 1} · Δshares_ij,t / SO_j        [demanda dos suspeitos]
controle: mesma soma para surpresa < 0 (adiantados) → deve ser mais fraca
```
**Modo de falha**: atrasos anômalos coletivos (mudança de regra, feriado) —
de-mediana por trimestre; teste do vazamento pela borda (§6.3 do plano II):
usar só o histórico, nunca o atraso corrente de outros como feature do próprio.

---

## ★3. Filing-Season Surprise — o SUE do 13F

**Mecanismo.** O anúncio de earnings tem o SUE (realizado − esperado). O filing
season do 13F não tem um "esperado" na literatura — mas **nós temos**: a âncora
da borda irregular nowcasta o ΔIO final a partir dos filers já revelados (51%
do ΔIO em D+45). Sinal = **ΔIO realizado pelos atrasados − o que os adiantados
implicavam**. Se os hedge funds (que chegam por último) surpreendem comprando o
que os passivos não compraram, essa surpresa é a componente informada da
demanda — negociável em D+46, 100% PIT.

**Linhagem.** PEAD/SUE (Bernard-Thomas) como molde; Campbell-Ramadorai-Schwartz
usam 13F como alvo supervisionado (espírito parecido, dado morto); nosso X3/X4
já mediu as peças. **Gap**: surpresa-vs-nowcast dentro do filing season não
existe publicada.

**Construção.**
```
esperado(j)  = Δ_rev_early(j, D+40) / cobertura_early     [o nowcast, PIT]
realizado(j) = ΔIO_final(j, D+50)
SUE13F(j)    = (realizado − esperado) / dispersão_cross-section
trade em D+50→D+110; falsificação: SUE13F de trimestres SEM atrasados ≈ 0
```
**Nota honesta**: X4 mostrou que o ΔIO revelado *cedo* não prevê retorno — este
sinal aposta na componente ORTOGONAL (a surpresa dos atrasados), que o X4 não
testou. Pode dar nulo; o nulo seria publicável no memo.

---

## ★4. Birth Demand — onde entra o dólar institucional marginal

**Mecanismo.** Nossa descoberta da noite: metade do "sinal de volume" do paper
da Miori era **fluxo de composição** — books inteiros de filers novos entrando
no universo (~6%/ano de crescimento). Todo mundo trata isso como ruído a
filtrar. Invertendo: os filers NOVOS são os gestores que acabaram de cruzar
$100M — os de crescimento mais rápido, o **dólar marginal da indústria**. O
portfólio agregado deles é um censo de para onde a nova geração de gestores
está indo, invisível em qualquer medida de trading.

**Linhagem.** Ninguém encontrado; o mais próximo é literatura de fund inception
(fundos novos de famílias grandes têm alfa incubado — Evans 2010, viés de
incubação). **Gap**: books de FILERS estreantes como sinal cross-sectional.

**Construção.**
```
BIRTH(j,t) = Σ_{i estreantes em t} w_ij / n_estreantes  −  w_mercado_j
(peso médio dos estreantes vs mercado: onde eles CONCENTRAM além do normal)
```
**Modo de falha**: estreantes incluem spin-offs de gestores velhos (usar
sucessão/famílias pra excluir); books pequenos = ruído (piso de AUM).

---

## ★5. Doubling-Down — convicção contra a fita

**Mecanismo.** Um gestor concentrado que AUMENTA ≥25% as shares numa posição
que CAIU ≥15% no trimestre está pagando pra discordar do mercado — a expressão
mais cara de informação privada que o 13F consegue mostrar. Distinto de "buy
the dip" agregado: exige interação posição×preço×gestor-ativo.

**Linhagem.** Akepanidtaworn et al. ("Selling Fast and Buying Slow") — decisões
de COMPRA institucionais carregam skill; disposition effect (a versão burra do
mesmo comportamento — separar via universo endógeno: concentrados ativos vs
resto). **Gap**: doubling-down como sinal cross-sectional de 13F não achado.

**Construção.**
```
DD(j,t) = Σ_{i elegíveis} 1{Δshares_ij ≥ +25% · shares_prev  E  ret_j,q ≤ −15%} · conv_i
teste-espelho: mesma conta para gestores NÃO-elegíveis (quasi-indexers
rebalanceando) → deve ser mais fraca; se igual, é rebalanceamento mecânico
```

---

## Menções honrosas (e por que não subiram)

| ideia | por quê ficou de fora |
|---|---|
| Restatement flow (posições reveladas só no diff original→restatement) | **já reivindicada**: [Da et al., ~3,6bps/dia](https://www3.nd.edu/~zda/Restatement.pdf) — vale implementar citando, não vale como "original" |
| Rank migration (posição subindo no ranking ordinal do book) | boa, flow-robusta, mas é variação de best ideas — incremental |
| Detector de splits pelo átomo modal | original de verdade, mas é método de DADOS, não sinal de retorno — já está no analysis_v1 e vale meia página de memo |
| Hora do aceite (filings 23h59 da deadline) | too cute; colinear com delay surprise |
| Exit após ganho vs após perda | boa, mas precisa de custo médio estimado — ruído alto |

## Ordem de implementação sugerida (retorno/esforço)

1. **Delay Surprise** — tudo pronto (meta de filings + snapshots); ~meio dia;
2. **Birth Demand** — subproduto direto da decomposição all-filers; ~2h;
3. **Doubling-Down** — snapshots + painel de preços; ~meio dia;
4. **Death Supply** — precisa acoplar a sucessão do crowdflow; ~1 dia, e é o
   de maior potencial de memo ("o sinal que só existe com a máquina de
   sucessão");
5. **SUE-13F** — usa a âncora do nowcasting; ~1 dia, risco de nulo (declarado).

Protocolo de avaliação: o mesmo dos 17 (`general_predictive_signals`) — teste
do teorema por sinal, quintis EW/VW, NW, escada FF6 pros sobreviventes, e a
contagem de especificações no memo.
