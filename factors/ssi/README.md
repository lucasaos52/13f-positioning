# ssi — Shadow Short Interest: o lado short censurado do 13F

`python run_ssi.py [--smoke]`. Saídas em `results/`.

## Tese (Miller 1977, formalizado em vez de proxiado)

Gestor long-only que odeia uma ação expressa no máximo POSIÇÃO ZERO — a
cross-section de tilts ativos observada é uma distribuição **censurada** no
ponto `c_j = −w_mkt_j` (deter zero = underweight máximo possível). A largura
do lado positivo visível identifica a cauda negativa escondida (Tobit, 1958):

```
latente:    tilt desejado τ ~ N(μ_j, σ_j²) entre os gestores ativos
observado:  max(τ, c_j)  — ponto de massa em c_j (não-detentores)
identificação por 2 momentos (forma fechada, sem MLE):
    p0 = fração censurada          → α = Φ⁻¹(p0)
    m1 = média dos tilts visíveis  → σ = (m1 − c)/(λ(α) − α),  μ = c − ασ
    onde λ(α) = φ(α)/(1−Φ(α)) (média da normal truncada)
SSI_j = E[(c − τ)⁺] = σ·[α·Φ(α) + φ(α)]  — a venda que não pôde existir
```

Predição PRÉ-REGISTRADA: SSI alto = pessimistas fora do preço = sobrepreço de
Miller = **retorno futuro negativo** (spread Q5−Q1 esperado < 0).

## Premissas

1. **Universo de gestores**: ativos com 15-500 posições e book ≥ $250M — a
   censura só é informativa em quem ESCOLHE posições (quasi-indexer não
   expressa opinião ao deter zero de uma small cap);
2. **Normalidade do latente** — a hipótese forte, declarada; a inversão usa
   só p0 e m1 (robusta a cauda no lado visível via winsor dos tilts);
3. **Guardas de inversão**: ≥10 holders elegíveis e p0 ≤ 0,995 (α explode na
   censura total); λ(α) − α tem piso numérico;
4. **Teorema do macaco**: dardos value-weighted não-detêm small caps por
   construção → p0 correlaciona com tamanho mecanicamente → **resíduo
   size/liquidez é headline**, cru reportado;
5. **PIT**: snapshots em p+45d por `filed_date`; w_mkt do painel de mktcap na
   data de decisão (fallback peso agregado 13F, fração logada).

## Os três testes (nesta ordem de importância)

1. **Aplicação ao fator (o que importa)**: o new_conviction condicionado por
   SSI — quintis de convicção DENTRO de terços de SSI. Predição: a compra
   informada paga onde NÃO há ursos represados (SSI baixo) e falha/inverte
   onde o preço já só ouve os bulls (SSI alto). E o teste de melhoria: perna
   long do new_conviction excluindo o terço de SSI alto vs original;
2. **Standalone**: quintis do SSI, direção negativa pré-registrada;
3. **Validação externa (a joia)**: corr cross-section do SSI com o short
   interest REAL (yfinance shortPercentOfFloat, snapshot corrente) — uma
   previsão de short interest feita sem nunca olhar short interest. Roda na
   última data apenas (histórico de short interest grátis é o próximo passo
   via FINRA).

## Linhagem e gap

Miller (1977); Tobin (1958); Chen-Hong-Stein (2002) — breadth como proxy
tosco da mesma censura que aqui é estimada; Asquith-Pathak-Ritter (2005) —
constraints via IO/short. Gap verificado por busca: estimar a distribuição
latente censurada de demanda por ação a partir do 13F — não encontrado.
