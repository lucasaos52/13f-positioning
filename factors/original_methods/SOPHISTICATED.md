# Métodos sofisticados — três desenhos com matemática de verdade e gap confirmado

Complemento ao IDEAS.md: aqui são MÉTODOS, não contagens espertas. Critério
mantido: mecanismo enunciável, linhagem citada, gap verificado por busca, e
complexidade **paramétrica** compatível com ~50 trimestres — sofisticação na
estrutura, não no número de parâmetros. (O veredito sobre GNN está no fim.)

---

## M1. Crowding no espaço de ESTRATÉGIAS — NMF sobre a matriz de holdings

**A ideia em uma frase.** Contágio de fire-sale acontece no nível da
*estratégia*, não da ação (quant quake de 2007: quem sangrou junto não
compartilhava ações — compartilhava a *receita*); então o crowding deve ser
medido em cima de estratégias latentes extraídas da matriz gestor×ação, e cada
ação herda o crowding das estratégias a que pertence.

**Construção.**
```
W (gestores × ações, pesos de book, universo endógeno, PIT por trimestre)
NMF:  W ≈ A · S      A = gestor × K (mix de estratégias, ≥0)
                     S = K × ações (cada estratégia É um portfólio, ≥0)
crowd_k(t)   = capital em k  ×  concentração de A_·k  ÷  liquidez do basket S_k
                (o denominador é o days-ADV DO BASKET — capacidade da estratégia)
sinal_j(t)   = Σ_k  S_kj_normalizado · crowd_k(t)
                "quanto desta ação está detida por estratégias lotadas"
rastreio no tempo: matching húngaro entre os S_k de t e t−1 (overlap dos
baskets) → estratégias têm identidade e o Δcrowd_k vira sinal também
```

**Por que NMF e não PCA.** Não-negatividade: cada componente
é um **portfólio de verdade** (pesos ≥0, interpretável — "small-cap biotech
concentrado", "quality megacap"), enquanto componentes de PCA têm pesos
negativos e não são carteiras de ninguém. E o crowding por estratégia com
capacidade (days-ADV do basket) é a pergunta certa: a de 2007 não era "quantos
têm IBM" — era "quantos rodam o mesmo screen".

**Linhagem (citável) e gap.** Khandani-Lo (2007) — o mecanismo;
[Cont-Schaanning](https://mfm.uchicago.edu/wp-content/uploads/2017/06/Cont_Schaanning_Fire-Sales-Indirect-Contagion-and-Systemic-Stress-Testing-2017.pdf)
e Girardi et al. — overlap de portfólio → vendas comuns; Lou-Polk
(comomentum) — crowding de estratégia inferido de RETORNOS;
[EFMA 2022 "Following the crowd"](https://www.efmaefm.org/0efmameetings/efma%20annual%20meetings/2022-rome/papers/efma%202022_stage-3032_question-full%20paper_id-176.pdf)
— crowding de anomalias via 13F com estratégias PRÉ-DEFINIDAS. **Gap
confirmado**: estratégias LATENTES (aprendidas da matriz, não impostas) com
crowding-capacidade por estratégia — não encontrado.

**Disciplina.** K escolhido por reconstrução held-out (gestores fora da
amostra), não por retorno; estabilidade por bootstrap de gestores; predição
dupla: prêmio incondicional (crowding-como-risco) + cauda condicional a stress
(a tabela 5×3 do plano I). Parâmetros efetivos: K (~8-15) e nada mais.

---

## M2. Campo de rotação institucional — optimal transport no espaço de características

**A ideia em uma frase.** Entre dois trimestres, o agregado institucional
redistribui massa sobre o espaço de características (size × book/market-proxy ×
vol × momentum); o **plano de transporte ótimo** entre as duas distribuições é
o mapa de menor custo consistente com os dois censos — um *campo vetorial* de
para onde o capital está rodando em style-space — e cada ação recebe o fluxo
líquido da sua vizinhança.

**Construção.**
```
1. Book agregado (universo endógeno) → distribuição μ_t sobre uma grade de
   características (4 dims × quintis = 625 células), APÓS correção de drift
   (a máquina do ΔACWB: sem isso, preço movendo célula = falsa rotação)
2. OT entrópico (Sinkhorn):  T* = argmin ⟨T, C⟩ + ε·H(T)
   s.a. marginais μ_{t-1}, μ_t   [C = distância na grade; ε por estabilidade]
3. campo(c) = Σ_c' T*(c',c) − T*(c,c')   [fluxo líquido chegando à célula c]
4. sinal_j = campo(célula de j) − componente já explicada por ΔIO_j próprio
   (a rotação da VIZINHANÇA, não o fluxo do próprio nome)
```

**Mecanismo.** Style investing (Barberis-Shleifer): capital se move por
categorias e a pressão da categoria vaza pros membros — comprar a ação *parada
no caminho* do fluxo de estilo antes do fluxo chegar nela. Teo-Woo documentam
efeitos de estilo; ninguém mede a rotação como transporte.

**Gap confirmado.** OT em finanças = robust optimization em bolas de
Wasserstein e martingale OT para derivativos
([SIAM](https://doi.org/10.1137/22m1496803), arXiv) — **medição de rotação de
holdings via plano de transporte: não encontrado.**

**Disciplina.** O plano de transporte não é único → regularização entrópica
com ε escolhido por estabilidade do campo (não por retorno); variante barata
como null-model: Δmassa por célula SEM transporte (só o censo) — o OT só se
justifica se o *direcional* (quem foi para onde) adicionar sobre o censo.
Parâmetros: ε e a grade. Nada aprendido de retornos.

---

## M3. Propagação de choques no grafo de co-ownership — difusão, não GNN

**A ideia em uma frase.** Os choques observáveis do IDEAS.md (Death Supply,
Delay Surprise, fluxo forçado) não param na ação atingida: propagam pelos
donos comuns (Antón-Polk) — um operador de difusão de UM parâmetro transforma
o vetor de choques diretos em pressão prevista de segunda ordem.

**Construção.**
```
G_jk = Σ_i  min(valor_ij, valor_ik) / (ADV_j + ADV_k)   [co-ownership × iliquidez]
P    = G normalizado por linha (operador de difusão)
pressão = (I + θ·P) · choque_direto        [θ único, estimado uma vez]
sinal_j = pressão_j − choque_direto_j       [só o spillover — o que ninguém vê]
```

**Linhagem e gap.** Antón-Polk (2014) — conectividade por donos comuns gera
co-movimento e reversão cruzada (~9%/ano); Greenwood-Thesmar (2011) —
fragilidade; a nossa base já computa a G no crowdflow. **Gap**: compor a rede
com choques *observáveis do próprio 13F* (mortes, atrasos-surpresa) em vez dos
fluxos de mutual fund que todo mundo usa — e negociar só o termo de spillover.

---

## O veredito sobre GNN — e a resposta de senior

**Não, e com número**: o benchmark publicado (NAVIS/TGB 2026) mostra o melhor
modelo de grafo temporal batendo a persistência por **2,4 pontos de NDCG**
(0,913 vs 0,889), com features de domínio adicionando <1,2% — no problema em
que grafos deveriam brilhar. Com ~50 trimestres de alvo, uma GNN tem mais
parâmetros que observações independentes por ordens de magnitude; o que ela
aprenderia é a amostra.

Os três métodos acima são a versão adulta da mesma intuição: **M3 é uma GNN de
uma camada com pesos fixados pela economia** (a adjacência é co-ownership real,
não aprendida; θ é o único parâmetro); **M1 é representation learning com
identificabilidade** (NMF = a camada de embedding, mas convexa por blocos,
interpretável e estável); **M2 é geometric deep learning sem o deep** (o campo
vetorial que uma GNN tentaria aprender, obtido por um programa convexo com
solução única dado ε). Estrutura de grafo/geometria: sim. Gradiente descendente
em 50 pontos: não.

## Ordem de ataque

1. **M1 (NMF)** — infra pronta (matriz W já existe no X5 do nowcasting), ~1
   dia; maior potencial de memo ("crowding onde o contágio mora");
2. **M3 (difusão)** — depende do Death Supply/Delay Surprise do IDEAS.md;
   ~1 dia depois deles;
3. **M2 (OT)** — o mais original e o mais caro de validar; fazer por último,
   com o null-model do censo primeiro.
