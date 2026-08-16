# copycat — Shadow AUM: o capital que segue cada guru, e o fluxo que ele prevê

`python run_copycat.py [--smoke]` → `results/`.

## Tese

Quando um filing 13F vira público, os copycats compram as posições novas do
gestor — fluxo **mecânico, com data marcada** (a publicação) e tamanho
proporcional ao **capital que segue aquele gestor específico**. O efeito médio
é documentado (Brown-Schwarz: volume anormal e retorno positivo pós-disclosure);
o que ninguém mediu é a **heterogeneidade**: qual gestor tem quanto capital
copiando. Nós estimamos o grafo seguidor→líder do próprio painel (lead-lag de
posições novas) e prevemos o drift pós-disclosure ponderado pelo "shadow AUM"
de cada líder. Isso dá o MECANISMO do nosso achado anterior (follow honesto em
large caps, t=+3,15): estávamos surfando fluxo de copycat — agora com o
tamanho da onda medido ex-ante.

## Construção (todas as datas por `filed_date`, PIT)

```
1. Líderes: top 300 books ativos elegíveis (15-500 posições, AUM>=250M)
2. Inovações de F no tri q: instrumentos no book de q ausentes no de q-1
3. Score de cópia do par (B segue A) no tri q:
   match = |novas(B,q) ∩ novas(A,q-1)| / |novas(B,q)|
   (B compra durante q o que A revelou ~45d após q-1 - o timing da cópia)
   excesso = match - média de match de B sobre TODOS os líderes no tri
   (remove "todo mundo comprou NVDA": só afinidade específica a A sobra)
4. Shadow AUM de A em t = Σ_B AUM_B × média dos excessos(B,A) nos 4 tri
   até t (trailing, só passado)
5. SINAL na decisão t+50: para cada ação j,
   flow(j) = Σ_A 1{j ∈ novas(A,t)} × shadowAUM_A / ADV_j
   = dias de volume de compra copycat esperada nas próximas semanas
6. Teorema do macaco: ADV no denominador → resíduo size/liquidez é headline
```

## Falsificação embutida

- **Placebo de shadow AUM**: o MESMO sinal construído com as posições novas
  dos líderes do tercil de MENOR shadow AUM (gurus sem seguidores). Novas
  posições sem capital seguidor = sem fluxo = sem drift. Se o placebo render
  igual, o efeito é "posições novas de gestor grande" genérico e a tese do
  fluxo cai;
- **Direção pré-registrada**: positiva no trimestre pós-disclosure (a onda
  comprando), sem reversão obrigatória (fluxo copycat é sticky — diferente de
  fire-sale);
- Estabilidade do grafo: shadow AUM de t vs t−1 (corr reportada).

## Linhagem citada e gap

Brown-Schwarz (2011) — o efeito médio pós-disclosure; Verbeek-Wang (2013) —
copycats lucram; Cziraki-Hankins et al. — evidência direta de cópia via
downloads do EDGAR; GURU/ALFA — a versão produto (e suas mortes). **Gap: o
grafo líder→seguidor estimado do painel e o drift previsto pelo capital
seguidor medido — não encontrado.**

## Limitações declaradas

Cópia inferida por coincidência de inovações (4 trimestres de trailing são
poucos para separar cópia de gosto comum — o de-mean por líder mitiga);
seguidores fora do 13F (varejo) invisíveis → shadow AUM é piso; ~45 eventos.
