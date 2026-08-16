# Contratos de dados para liberar as estratégias completas

## `etf_reference`

Chave única `(period_end, etf_id)`:

- `shares_outstanding`: shares do ETF naquele quarter-end;
- `aum`: NAV assets point-in-time;
- `ticker`, `asset_class`, `etf_style`, `specialized_score`;
- `source`, `effective_date`, `retrieved_at` para auditoria.

Sem shares outstanding, #9 não é ownership. Sem AUM, #1 não tem escala econômica comparável.

## `historical_baskets`

Chave única `(period_end, etf_id, instrument_id)`:

- `basket_weight`, somando aproximadamente 1 por ETF/data;
- `effective_date <= period_end`;
- CUSIP/FIGI point-in-time do constituinte;
- cash/derivativos separados das ações;
- arquivo-fonte e checksum.

O pipeline rejeita chave duplicada e `effective_date` futura. Cesta atual nunca deve ser
backfilled. Fontes aceitáveis incluem arquivos históricos do emissor ou bases institucionais
com versionamento; scraping do holdings atual não é aceitável.

## `etf_flows`

Chave `(date, etf_id)`:

- `creation_units`, `redemption_units`, `net_shares_created` e/ou `dollar_flow`;
- timestamp e convenção de NAV;
- ajuste explícito de splits.

Uma mudança trimestral 13F pode entrar como coluna separada (`d_own_13f`), nunca renomeada para
`dollar_flow`. A réplica próxima de fragilidade exige fluxo primário.

## `stock_reference`

Chave `(period_end, instrument_id)`:

- `market_cap`, `shares_outstanding`, preço e liquidez PIT;
- setor/indústria PIT;
- beta, size, momentum e short-term reversal para neutralização;
- delisting return quando aplicável.

## Gates antes do backtest #1–#7

1. cobertura de AUM e shares outstanding > 90% do notional verificado;
2. peso de basket entre 0,98 e 1,02 ou reconciliação documentada;
3. nenhum `effective_date > signal_period`;
4. nenhum ticker/CUSIP resolvido com informação posterior ao evento;
5. fluxo primário e demanda 13F em colunas e resultados distintos;
6. contribuição por ETF preservada para ablações broad/sector/thematic;
7. IC em retorno residual e custos/liquidez além de retorno bruto.

