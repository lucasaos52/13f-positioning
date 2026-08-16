# ica_demand — separação cega de fontes de demanda institucional (M4)

`python run_ica.py` (full) / `--smoke`. Saídas em `results/`.

## Tese

O fluxo institucional observado em cada ação é a SOMA de fontes de demanda
independentes e não observáveis (de-grossing, realocação passiva, rotação
discricionária). ICA des-mistura o painel de fluxos; a teoria carimba a
direção de cada fonte ANTES do backtest: **fonte de cauda pesada = fluxo
forçado = pressão que reverte** (Coval-Stafford 2007); **fonte persistente e
quase-gaussiana = acumulação informada = continua** (Lou 2012). A hipótese de
identificação estatística do ICA (não-gaussianidade) é a própria hipótese
econômica — o método e o mecanismo travam um no outro.

## Premissas, uma a uma, com justificativa

**P1 — Unidade do painel: taxa de crescimento das shares institucionais**
`f_j(p) = (sh_j(p) − sh_j(p−1)·split_fac) / sh_j(p−1)`, winsorizada 1/99.
*Por quê*: quantidade, nunca valor (valor mistura preço — plano II §2); a taxa
é unit-free e comparável entre ações; split-ajustada pelo átomo modal
(validado: NVDA 10,000 exato); dispensa shares outstanding → painel completo
2013–2026 (51 tri) em vez de 2016+ (o expanding window come 20 trimestres, o
resto é avaliação — sem os 3 anos extras sobrariam ~16 eventos).

**P2 — All-filers com de-mean cross-sectional por trimestre**
*Por quê*: all-filers porque fluxo forçado inclui mortes/nascimentos de filers
(é demanda real de mercado); o de-mean por data remove o componente comum —
inclusive o crescimento de composição do universo (~6%/ano de filers novos,
a lição do flip do VI) — senão a "fonte 1" seria o censo, não demanda.

**P3 — PIT em dois níveis**
Cada linha p do painel é computada com snapshots em p+45d (`filed_date` reais)
e NUNCA revisada — como um sistema real teria gravado. A ICA em cada data de
decisão t usa exclusivamente as colunas ≤ t (expanding window, primeira
janela = 20 trimestres). Nenhum parâmetro vê o futuro.

**P4 — K = 6, fixado a priori**
*Por quê*: com ≤51 observações temporais por fonte, K grande fabrica fontes de
ruído; 6 é o teto do que a janela inicial estima com estabilidade. Sem seleção
por retorno; sensibilidade K=4/8 reportada como robustez, não escolhida.

**P5 — Classificação das fontes por regra a priori, re-feita a cada t só com
o passado**: dentro das K fontes, as 2 de MAIOR curtose = forçadas; entre as
restantes, as 2 de maior |AR(1)| = informadas. *Por quê*: ranks internos em
vez de limiares absolutos (curtose amostral com T pequeno é ruidosa em nível,
mais estável em ordem); 2+2 fixo evita graus de liberdade.

**P6 — Direções carimbadas antes do teste**
`REV_j = −Σ_{k forçadas} β_jk·s_k(t)` (fade da pressão do trimestre corrente);
`CONT_j = +Σ_{k informadas} β_jk·s_k(t)`. Sinal combinado = média dos ranks.
Nenhuma direção é escolhida olhando retorno.

**P7 — Teste do teorema (neutralização)**: no mundo dos macacos
(books value-weighted aleatórios), a taxa de crescimento é igual pra toda
ação → sem vínculo mecânico com size/liquidez → **cru é headline**; resíduo
contra log(mktcap)+log(ADV) reportado como alternativa.

**P8 — Ações elegíveis por janela**: ≥10 holders no trimestre corrente,
≥80% das colunas da janela com fluxo observável (buracos = 0 após de-mean,
declarado); ticker mapeado, preço ≥ $1 na decisão.
*Viés declarado*: o fit usa ações vivas ao longo da janela (survivorship no
ESTIMADOR das fontes); o sinal só é aplicado a ações vivas na decisão (sem
lookahead adicional).

## Falsificação embutida (roda junto)

1. **Placebo de rotação (o teste decisivo)**: mesmo pipeline com PCA no lugar
   de ICA (mesma variância explicada, base cega a rotação). Se o placebo
   render igual, a não-gaussianidade não identificou nada e a tese CAI —
   reportado lado a lado, passe ou falhe;
2. **Validação externa das fontes forçadas**: datas dos maiores |s_k| das
   fontes de curtose alta impressas contra os trimestres de stress conhecidos
   (2015Q3, 2018Q4, 2020Q1, 2022);
3. **Estabilidade da classificação**: fração de trimestres em que uma fonte
   classificada como forçada em t mantém a classe em t+1 (fontes têm que ser
   objetos estáveis ou não são objetos).

## Limitações vivas

~30 eventos de avaliação; fontes ICA são padrões temporais independentes, não
agentes nomeados (a narrativa exige inspecionar loadings); fluxo trimestral
apaga o trading intra-trimestre (Puckett-Yan); sobreviventes Yahoo no painel
de retornos. Linhagem: Coval-Stafford 2007, Lou 2012, Back-Weigend 1997 (ICA
em retornos — gap: em fluxos de ownership, inédito por busca), Kritzman 2011.
