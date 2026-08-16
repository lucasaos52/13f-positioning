# Metodologia e relação com a literatura

Esta implementação segue as hipóteses e referências do memo local, mas separa explicitamente
evidência publicada de adaptação ao dataset 13F.

## Relógio de informação

O período econômico é o quarter-end; a informação só entra quando o filing selecionado é
público. Restatements substituem a tabela do CIK e `NEW HOLDINGS` posterior é aditivo. CIKs
irmãos são resolvidos separadamente antes da agregação por família. Como o parquet guarda dia,
não hora de aceitação, todo o livro selecionado do gestor é liberado na última data selecionada.
O target é colocado no primeiro pregão posterior e o motor compartilhado ganha retorno apenas
depois desse target.

## Universo e mensuração

`instrument_class == fund` é apenas uma triagem de alto recall. O backtest usa 41 ETFs de ações
com CUSIP, ticker, classe e fonte oficial no master verificado. O restante fica em quarentena.
Identidade estática não cria elegibilidade retroativa: preço, história e ADV são avaliados no
evento. Isso reduz temas/indústrias, mas evita misturar CEFs e ações com ETFs.

Trade e churn usam pesos contra o livro anterior driftado por total return. Gestores precisam
ter livro elegível no trimestre anterior e cobertura individual de retorno de ao menos 50%.
Retornos ausentes recebem SPY apenas no denominador do drift; o relatório mostra a cobertura e
a sensibilidade de 40% a 80%.

## Cinco hipóteses

1. **Sticky demand.** `0.5 * sum(abs(w_current - w_drift))`, suavizado por até quatro trimestres;
   quality é um menos o percentil cross-sectional. O score soma `quality * ETF_trade`. É uma
   adaptação de horizonte/conviction de Angelini, Iqbal e Jivraj, não uma réplica literal.
2. **Doubling down.** Betas são estimados nos 252 pregões anteriores ao trimestre. O retorno
   residual usa SPY, `IWM-SPY` e `QQQ-SPY`; somente compras após residual negativo contam. O
   teste primário exclui broad ETFs, seguindo a ressalva de cash management. É a transposição
   para ETFs da hipótese de Rhinesmith.
3. **Abnormal adoption.** A cada filing, OLS cross-sectional residualiza log breadth por valor
   institucional divulgado, momentum, volatilidade, beta, ADV, preço, idade e estilo. O sinal é
   a mudança do residual contra o trimestre anterior. Como não há shares outstanding/AUM
   históricos completos, isto é abnormal disclosed breadth — uma adaptação da variável de Kirk.
4. **Conviction × consensus × persistence.** Conviction é o percentile rank do peso dentro do
   ETF sleeve; persistence é a sequência de holdings truncada em quatro trimestres; quality é a
   mesma medida ex ante do sinal 1. A construção combina Angelini–Iqbal–Jivraj com a lógica de
   *Best Ideas* de Antón, Cohen e Polk.
5. **Transient-holder fragility × shock.** Fragility é a média de churn ponderada pela fatia do
   ownership 13F observável. O estado é carregado diariamente. Stress abre proteção de um dia
   apenas no decil inferior histórico do retorno de cinco dias do SPY. Reversal combina
   fragilidade com choque residual negativo e mantém coortes sobrepostas por 21 pregões. Isso
   implementa a previsão condicional de Cella, Ellul e Giannetti; não trata fragilidade como
   alpha universal.

## Avaliação pré-especificada

- HML equal-weight pelo `Portfolio` compartilhado, com filtros antes do score;
- 20% em cada cauda (11 ETFs específicos no teste de doubling down);
- custos one-way de 0/5/10/20 bps, com 10 bps principal;
- IC Spearman em 5/21/63 pregões e t Newey–West;
- estabilidade full, pré-2022 e pós-2021;
- ablações raw/quality/specificity, all-vs-specific, level-vs-change, consensus e fragility sem shock.

Um resultado só é aprovado se tiver direção correta, retorno líquido, estabilidade temporal e
turnover plausível. IC isolado é rotulado como sugestivo.

## Referências do memo

- Angelini, Iqbal & Jivraj (2019), *Systematic 13F Hedge Fund Alpha*, SSRN 3459526.
- Rhinesmith, *Doubling Down*, SSRN 2491636.
- Khomyn (2024), *The Value of ETF Liquidity*, RFS 37(10).
- Kirk (2025/2026), *Abnormal Institutional Ownership and Expected Returns*.
- Cella, Ellul & Giannetti (2013), *Investors' Horizons and the Amplification of Market Shocks*, RFS 26(7).
- Antón, Cohen & Polk, *Best Ideas*, SSRN 1364827.
- U.S. SEC, Form 13F guidance.
