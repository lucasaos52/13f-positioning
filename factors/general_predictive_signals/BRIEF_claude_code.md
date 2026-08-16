# Brief de implementação — pipeline 13F (para Claude Code)

Documento de referência dos sinais: `13F_sinais_posicionamento_revisao.md`. Leia-o antes de escrever código; este brief é só o recorte executável.

---

## Escopo travado

| Decisão | Valor | Justificativa |
|---|---|---|
| Janela | 2013Q3 → trimestre mais recente | XML estruturado a partir de mai/2013; evita parsing de ASCII legado |
| Universo de filers | Todos os 13F-HR, particionados por churn ratio | Partição point-in-time, sem lista externa |
| Universo de ações | CRSP common stock (SHRCD 10, 11), acima do percentil 20 do NYSE | Exclui ETF/ADR/CEF e microcaps |
| Fator | Composto de 4 componentes + 1 contra-sinal | Ver Tier 1 do doc de referência |
| Rebalanceamento | Mensal, 3 carteiras sobrepostas | Reduz timing luck |
| Benchmark | FF5 + MOM; equal-weight e cap-weight | Reportar os dois |

---

## Estrutura de módulos

```
src/
  ingest/
    edgar_client.py      # rate limit 10 req/s, User-Agent obrigatório, cache em disco
    parse_13f.py         # primary_doc.xml + informationTable.xml
    sec_datasets.py      # alternativa: TSVs trimestrais da SEC (mais rápido)
  clean/
    normalize_cusip.py   # strip/upper/zfill(9) + dígito verificador
    units.py             # detecção milhares vs. dólares (ver §6.2 do doc)
    dedup_filers.py      # grafo CIK ↔ Other Included Managers; 13F-NT
    amendments.py        # restatement vs. adds-new-holdings; versionamento
  panel/
    bitemporal.py        # (report_date, filing_date) → as-of join
    universe.py          # filers ativos e ações elegíveis por trimestre
  factors/
    drift.py             # decomposição peso ativo vs. drift de preço  [SINAL #9]
    breadth.py           # ΔBreadth, IN/OUT                            [#1, #2, #5]
    crowding.py          # posição agregada HF / ADV                   [#11]
    horizon.py           # churn ratio → partição de gestores          [#20]
    persistence.py       # persistência multi-trimestre                [#14]
    composite.py         # z-score, winsorize, combinação
  backtest/
    engine.py            # carteiras sobrepostas, T+1, delisting returns
    costs.py             # spread + impacto raiz quadrada; breakeven cost
    report.py            # IC, decis, alpha FF5+MOM, turnover, drawdown
tests/
  test_lookahead.py      # ASSERT: nenhuma linha usada antes do filing_date
  test_units.py
  test_amendments.py
```

---

## Contrato de dados do painel principal

```python
holdings_panel: pd.DataFrame
# chave lógica: (cik, cusip9, report_date, version)
{
  'cik': str,               # zero-padded 10
  'filer_name': str,
  'report_date': 'datetime64[ns]',   # fim do trimestre — NUNCA usar para filtrar disponibilidade
  'filing_date': 'datetime64[ns]',   # data real do accession — usar SEMPRE
  'accession': str,
  'form_type': str,         # 13F-HR | 13F-HR/A | 13F-NT
  'amendment_type': str,    # None | 'RESTATEMENT' | 'NEW_HOLDINGS'
  'amendment_no': 'Int64',
  'is_confidential': bool,  # flag de CT na capa
  'ct_reveal': bool,        # emenda NEW_HOLDINGS com legenda de CT  → SINAL #21
  'cusip9': str,
  'permno': 'Int64',
  'value_usd': float,       # já normalizado para dólares
  'shares': float,          # já ajustado por split
  'sh_prn': str,            # 'SH' | 'PRN'  → filtrar PRN
  'put_call': str,          # None | 'Put' | 'Call'  → nunca somar com ações
  'discretion': str,        # 'SOLE' | 'DEFINED' | 'OTHER'
}
```

**Invariante inegociável:** nenhuma função de fator recebe `report_date` como argumento de disponibilidade. A única porta de entrada é:

```python
def as_of(panel, asof_date):
    """Retorna a melhor visão conhecida do mundo em asof_date."""
    v = panel[panel.filing_date <= asof_date].copy()
    # resolve emendas: restatement substitui, new_holdings acrescenta
    ...
    return v
```

---

## Ordem de construção sugerida

1. **Ingestão + parsing** de 2 trimestres, dois ou três filers conhecidos. Valide manualmente contra o filing no site da SEC antes de escalar.
2. **Validações** (§6.8 do doc) rodando como testes. Especialmente a checagem de unidades.
3. **Painel bitemporal** + `as_of()`. Escreva `test_lookahead.py` **antes** de qualquer fator.
4. **Casamento CUSIP → PERMNO** com NCUSIP histórico. Reporte a taxa de casamento por trimestre; ela é um número que vai para o memo.
5. **Sinal #9** (drift-corrected active weight) sozinho. Rode o backtest. Compare com e sem correção de drift — a diferença é a prova de que a correção importa.
6. **#20** (churn) e reaplique #9 dentro das partições.
7. **#1/#5** e **#11**.
8. **#14** como contra-sinal; plote a curva de alpha por horizonte (1, 2, 4, 8 trimestres).
9. **Composto** + relatório.

---

## Saídas obrigatórias do relatório

- IC (Spearman) por trimestre, média e t-stat
- Retorno por decil, equal e cap-weighted
- Alpha e cargas contra FF5 + MOM
- Curva de decaimento: alpha em h = 1, 2, 3, 6, 12 meses após formação
- Turnover anualizado e breakeven cost em bps
- Drawdown máximo e comportamento em 2020Q1, 2022 e no episódio de deleveraging de jan/2021
- Sensibilidade ao timing de rebalanceamento (trimestral fixo vs. mensal sobreposto)
- Taxa de casamento CUSIP e contagem de filings descartados, por trimestre

---

## Armadilhas para verificar explicitamente no código

- [ ] `value` em milhares pré-2023-01-03, dólares depois — e filers que erram nos dois sentidos
- [ ] Linhas `PRN` excluídas; linhas de opções separadas das de ações
- [ ] Splits ajustados antes de comparar trimestres consecutivos
- [ ] `13F-NT` não conta como holding nem infla contagem de filers
- [ ] Emendas versionadas, nunca sobrescritas
- [ ] CT: ausência de posição ≠ saída de posição
- [ ] `NCUSIP` histórico, não `CUSIP` atual do CRSP
- [ ] Retornos de delisting incluídos
- [ ] Drift de preço removido de qualquer Δpeso
- [ ] Universo de filers reconstruído por trimestre, não a partir de lista atual
