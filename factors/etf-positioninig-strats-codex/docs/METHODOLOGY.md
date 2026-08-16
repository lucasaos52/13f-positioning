# Metodologia e consistência com a literatura

## Relógio e unidade de medida

Cada fato tem `period_end` (tempo econômico) e `available_ts` (tempo de conhecimento). Emendas
`NEW HOLDINGS` são aditivas; restatements substituem o estado anterior, sempre por CIK, não por
família econômica. O código oferece dois relógios:

- `snapshot_as_of`: corte conservador usado na primeira avaliação (`q + 70 dias`);
- `filing_time_demand_nowcast`: acumulação evento a evento no timestamp público real.

Mudanças são calculadas em **shares split-adjusted**, nunca por diferença de `value_usd`. Opções
não são misturadas a ações. Entrada no event study é o primeiro close estritamente posterior à
data disponível.

## Fórmulas e status científico

### 1. Demanda e pressão

`dOwn[e,q] = Own13F[e,q] - Own13F[e,q-1]`, com
`Own13F = shares13F / ETF shares outstanding`.

`Pressure[i,q] = Σe w[e,i,q] dOwn[e,q] AUM[e,q] / MCap[i,q]` e
`alpha = -z(Pressure)`.

Brown, Davies e Ringgenberg usam fluxo primário para identificar choque não fundamental e
reversão. Substituir esse fluxo por mudança 13F é uma adaptação, não réplica. O risco econômico
central é o efeito diário já ter revertido antes da divulgação trimestral.

### 2. Fragilidade

`Fragility[i,t] = W[i,t] Ωflow[t] W[i,t]' / MCap[i,t]^2`.

`etf_fragility` estima Ω somente com observações até `t`, usa shrinkage diagonal e garante matriz
semidefinida positiva. A fórmula corresponde à forma de Greenwood–Thesmar e à especialização
ETF de Galindo Gil–Lazo-Paz. O paper prevê principalmente risco/volatilidade; só a interação com
pressão define direção de alpha.

### 3–4. Especialização e holder run-prone

As contribuições por ETF são preservadas para permitir `SpecializedScore` e `RunProne` sem
recalcular o look-through. O score tem bucket simples no seed, mas produção deve usar
concentração, distância do benchmark e turnover. `transient` compara o turnover atual apenas
contra a história estritamente anterior do próprio gestor.

### 5. Convicção direto-vs-ETF

`ETFExposure[m,i,q] = Σe PositionValue[m,e,q] w[e,i,q]`.

`IdioConviction = DirectPosition - kappa * ETFExposure`. Por padrão, `kappa` é a projeção
não-negativa por gestor-trimestre; `kappa=1` reproduz a versão simples. O residual é padronizado
dentro do gestor antes da agregação. Essa é uma extensão original do blueprint, não uma réplica
de paper.

### 6–7. Rede e footprint

Overlap é `Σi min(w[e,i],w[f,i])`, com diagonal removida. O conditioner é
`-ShortTermReturn × max(z(ETFOwn),0)`. A evidência de Ben-David, Franzoni e Moussawi sustenta ETF
ownership como estado de volatilidade/turnover, não como direção autônoma.

### 8–9. Qualidade e baseline

`ETFIntensity = verified ETF value / total 13F value`. Os pesos usam intensidade defasada:

- neutral: 1 para gestor elegível;
- direct tilt: `1 - lag(ETFIntensity)`;
- direct specialist: 1 se `lag(ETFIntensity) ≤ 5%`.

O baseline exato #9 exige shares outstanding históricos. O resultado presente usa mudança
normalizada das shares institucionais e é rotulado como proxy. O sinal fraco e instável medido é
compatível com a motivação do blueprint para não parar no ownership bruto.

## Avaliação

- IC Spearman e t Newey–West;
- spread equal-weight top-minus-bottom quintil;
- 5/21/63/126 pregões;
- 10 bps one-way, descontando entrada/saída de ambas as pernas;
- ablações neutral, direct tilt, direct specialist e run-prone;
- estabilidade pré-2022/pós-2021, definida antes da leitura dos resultados.

Uma estratégia só seria aprovada com sinal economicamente correto, t razoável, spread líquido,
estabilidade temporal e insensibilidade ao universo. Nenhum baseline disponível passou esse
conjunto.

## Referências primárias

- [Brown, Davies & Ringgenberg (2021)](https://doi.org/10.1093/rof/rfaa027)
- [Greenwood & Thesmar (2011)](https://doi.org/10.1016/j.jfineco.2011.06.003)
- [Galindo Gil & Lazo-Paz (2025)](https://doi.org/10.1016/j.finmar.2024.100946)
- [Ben-David, Franzoni & Moussawi (2018)](https://www.nber.org/papers/w20071)
- [Ben-David, Franzoni, Kim & Moussawi (2023)](https://doi.org/10.1093/rfs/hhac048)
- [Easley et al. (2021)](https://doi.org/10.1093/rof/rfab021)
- [Dekker, Molestina Vivar & Weistroffer (2024)](https://www.ecb.europa.eu/pub/pdf/scpwps/ecb.wp2963~3048370971.en.pdf)
- [Sherrill, Shirley & Stark (2017)](https://doi.org/10.1016/j.jbankfin.2016.11.008)

