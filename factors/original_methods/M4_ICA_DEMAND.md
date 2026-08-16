# M4 — Separação de fontes de demanda: ICA sobre o painel de fluxos institucionais

## A ideia em uma frase

O ΔIO que observamos em cada ação é a **soma cega de várias fontes de demanda
independentes** (realocação de target-date funds, de-grossing de hedge funds,
rebalanceamento quant, rotação setorial discricionária); ICA des-mistura essas
fontes — e a teoria diz **de antemão qual fonte negociar e em que direção**:
fluxo forçado é estatisticamente pesado-de-cauda e reverte; fluxo
discricionário é suave e continua.

## O problema do cocktail party, versão mercado

N microfones num salão gravam a soma de várias conversas; ICA recupera cada
voz porque vozes independentes são não-gaussianas. Aqui: cada **ação** é um
microfone; o ΔIO trimestral dela grava a soma das forças de demanda que a
tocam. Ninguém observa as forças diretamente (fluxos de hedge fund não são
públicos — a limitação estrutural do plano II). Mas a MISTURA é observável em
milhares de microfones simultâneos — exatamente o setup em que separação cega
de fontes funciona.

## Por que ICA e não PCA — e aqui mora a elegância

PCA só **descorrelaciona**, e é cega a rotações: qualquer rotação dos
componentes explica a mesma variância, então "PC2" não é um objeto econômico —
é uma escolha arbitrária de base (parte do porquê de fatores de PCA em
holdings não renderem: são modos, não agentes). ICA **identifica** as fontes
(a menos de escala/permutação) usando não-gaussianidade — e a economia fornece
exatamente essa assinatura:

| fonte de demanda | processo | assinatura estatística |
|---|---|---|
| forçada (resgates, margin calls, de-grossing, mortes de gestor) | bursty, em cascata | **cauda pesada, curtose alta** |
| discricionária/informada (acumulação paciente) | suave, persistente | ~gaussiana, autocorrelacionada |
| mecânica (indexação, target-date) | constante | quase determinística |

**A hipótese de identificação do método É a hipótese econômica.** Não há
palpite de direção depois — a direção vem da teoria ANTES da estimação:

- exposição a fontes de **curtose alta** → pressão não-fundamental →
  **reversão** (Coval-Stafford);
- exposição a fontes **persistentes de curtose baixa** → informação sendo
  incorporada → **continuação** (Lou 2012; Yan-Zhang).

É a resposta estrutural à crítica "estado sem seta": cada componente vem com a
seta carimbada pela sua própria distribuição.

## Construção (PIT estrito)

```
1. Painel X = ΔIO split-safe (ações × trimestres), da máquina existente
   (SO contemporâneo, all-filers, D+45 por filed_date)
2. Em cada data de decisão t (a partir do trimestre ~24):
   FastICA em X[:, 1..t]  (expanding window - só passado)
   → K fontes s_k(τ) (séries no tempo) + exposições β_jk (por ação)
   K ~ 5-8, fixado por não-gaussianidade held-out na janela inicial
3. Classificação a priori das fontes EM t (só com dados ≤ t):
   kurt_k = curtose de s_k | persist_k = AR(1) de s_k
   forçada: kurt alta & persist baixa | informada: kurt baixa & persist alta
4. Sinais (dois, com direções opostas por teoria):
   REV(j,t)  = − Σ_{k forçadas}  β_jk · s_k(t)   [fade a pressão recente]
   CONT(j,t) = + Σ_{k informadas} β_jk · s_k(t)   [siga a acumulação]
5. Pipeline padrão: teste do teorema (β são de ΔIO ratio - sem mecânica de
   size óbvia; verificar), quintis EW/VW, NW, escada FF6
```

## Falsificação embutida

- **Placebo de rotação**: substituir ICA por PCA (mesma variância, base
  arbitrária) → os sinais devem DEGRADAR; se PCA rende igual, a
  não-gaussianidade não estava identificando nada e a tese cai;
- **Validação externa das fontes forçadas**: os spikes de s_k(forçada) devem
  coincidir com trimestres de stress conhecidos (2015Q3, 2018Q4, 2020Q1,
  2022) e com as mortes de gestor do Death Supply — duas máquinas nossas se
  validando mutuamente;
- **Curtose fora da amostra**: a classificação forçada/informada feita até t
  deve persistir em t+1 (fontes são objetos estáveis ou não são objetos).

## Linhagem citada e gap

Coval-Stafford (2007) e Lou (2012) — a economia das duas direções;
Back-Weigend (1997) — ICA em finanças, mas sobre RETORNOS; Kritzman et al.
(2011) — espectral sobre retornos como risco sistêmico; Gabaix (granularidade)
— choques idiossincráticos grandes não se diversificam. **Gap verificado por
busca: ICA sobre painéis de fluxo de ownership para separar demanda forçada de
discricionária — não encontrado.**

## Limitações declaradas

- T curto: expanding window começa com ~24 trimestres → avaliação em ~26
  eventos; K pequeno obrigatório;
- fontes podem misturar agentes (uma "fonte" ICA é um padrão temporal
  independente, não um nome próprio — a narrativa exige inspecionar os
  loadings);
- ΔIO trimestral agrega o trading intra-trimestre (Puckett-Yan) — as fontes
  recuperadas são as de baixa frequência.
