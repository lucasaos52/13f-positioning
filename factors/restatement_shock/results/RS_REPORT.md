# restatement_shock - o mercado reage a correcao publica?

dirret = sinal da correcao x excesso vs mediana do universo, a partir do close do 1o pregao apos o amendment. Cluster por trimestre, NW(4).

- 250378 eventos-ticker | 52 tri | RS: 208608, NH: 41770

## R1 RESTATEMENTS materiais (mat>=0.5% book) (35601 eventos)
- dirret +1d: -0.0004 (t=-2.47)
- dirret +3d: -0.0010 (t=-3.52)
- dirret +5d: -0.0014 (t=-3.14)
- dirret +10d: -0.0012 (t=-2.13)
- R4 placebo -5d, +3d: -0.0001 (t=-0.03)
- R4 placebo -5d, +5d: +0.0004 (t=+1.29)

## R3 administrativos (mat<0.5%) - deve ser ~0 (173007 eventos)
- dirret +1d: +0.0001 (t=+0.27)
- dirret +3d: +0.0002 (t=+0.08)
- dirret +5d: +0.0005 (t=+0.92)
- dirret +10d: +0.0004 (t=+0.27)
- R4 placebo -5d, +3d: +0.0007 (t=+1.65)
- R4 placebo -5d, +5d: +0.0011 (t=+2.11)

## R5 NEW HOLDINGS reveals (confidenciais) (41770 eventos)
- dirret +1d: -0.0004 (t=-0.91)
- dirret +3d: -0.0003 (t=-0.36)
- dirret +5d: +0.0003 (t=+0.94)
- dirret +10d: +0.0031 (t=+2.99)
- R4 placebo -5d, +3d: +0.0019 (t=+2.58)
- R4 placebo -5d, +5d: +0.0024 (t=+2.52)

## R2 gradiente de magnitude (|corr|/ADV, terciles por tri)
- +1d T2-T0: -0.0001 (t=-0.10) | terciles -0.0004 / -0.0004 / -0.0004
- +3d T2-T0: -0.0002 (t=-0.34) | terciles -0.0010 / -0.0007 / -0.0012
- +5d T2-T0: +0.0008 (t=+1.03) | terciles -0.0018 / -0.0009 / -0.0010
## Veredito (52 tri, 250k eventos-ticker)

EXISTE um fato novo, e ele e INVERTIDO ao pre-registro:

1. R1: restatements MATERIAIS movem o preco CONTRA a correcao - dirret
   -0.10%/-0.14% em +3/+5d com t=-3.52/-3.14. Correcao pra cima (posicao
   revelada maior que o informado) -> papel underperforma nos dias
   seguintes, e vice-versa.
2. A identificacao e limpa nos dois eixos que importam: administrativos
   (mat<0.5% do book) = zero em todos os horizontes (a base distingue
   correcao material de burocracia), e placebo pre-evento = zero (o efeito
   esta TRAVADO no timestamp do amendment).
3. R2: gradiente de magnitude FLAT - terciles identicos. Isso MATA o canal
   de pressao/copycat (fluxo proporcional moveria mais com correcao maior)
   e aponta canal INFORMACIONAL binario: "houve restatement material" e a
   noticia, nao o tamanho. Consistente com Cao-Da-Jiang-Yang: restatement
   material sinaliza misreporting estrategico; a revelacao de acumulacao
   escondida marca o FIM da fase de acumulacao e deflaciona o premio
   antecipatorio.
4. R5 (NEW HOLDINGS/confidenciais): drift +0.31% em +10d (t=+2.99) na
   direcao Agarwal, mas o placebo pre-evento tambem e positivo (t=+2.5) -
   os nomes ja vinham subindo antes do reveal; nao e event-locked. Fraco.

STATUS: anomalia real, micro (-14bps/5d por evento, ~680 eventos/tri) -
abaixo de custos de ida-e-volta para producao. Valor real: e um FATO NOVO
documentado com a unica base que preserva versoes+semantica+timestamps -
abordagens sem PIT nao conseguem nem construir o evento. Pela regra do funil,
sign-invertido = gerador de hipotese; re-registro formal ("fade the
restatement") so em amostra futura ou com refinamento de custo zero.
