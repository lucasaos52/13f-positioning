# ETF positioning strategies — implementação Codex

Implementação reproduzível das nove hipóteses do `13F_ETF_Strategy_Blueprint.pdf`, separando
rigorosamente **replicação**, **adaptação 13F** e **extensão original**. O pacote está funcional,
os painéis point-in-time foram materializados para 2013Q2–2026Q1 e o baseline possível com os
dados atuais foi backtestado. O resultado honesto é: **a mudança bruta de posições 13F em ETFs
não é um alpha aprovado**. Isso é coerente com a função de baseline fraco que o blueprint lhe dá.

## Decisão de universo

Foi adotado um desenho híbrido, e não um novo rol fixo de “fundos passivos”:

1. **Filers:** todos os gestores visíveis na data são preservados. Cada gestor-trimestre recebe
   `ETFIntensity`, turnover, concentração, `manager_style` e flag transitória. `passive_manager`
   fica propositalmente nulo: intensidade de ETF não prova status jurídico ativo/passivo.
2. **Triagem de instrumentos:** `instrument_class == fund` é um diagnóstico de alta cobertura.
   Na amostra há 16.853 candidatos; a categoria mistura ETFs, closed-end funds, bond funds,
   commodity trusts e identificadores não-CUSIP.
3. **Sinal negociável/look-through:** somente o master verificado por CUSIP, ticker e classe de
   ativo entra. O seed atual tem 51 produtos observados (41 de ações) e cobre 54,7% do valor
   histórico da triagem `fund`. A cauda fica em quarentena, não é promovida por regex.

Essa escolha preserva informação sobre **quem detém ETFs** sem survivorship de uma lista manual
de gestores. Também evita o erro conceitual de chamar um hedge fund macro que usa SPY de
“passivo”, ou a Vanguard de “ativa” só porque reporta ações diretamente.

## Resultado medido

O teste disponível usa mudanças split-adjusted nas ações de ETFs reportadas em 13F, entrada em
`period_end + 70 dias`, 40 nomes medianos por evento, quintis, preços ajustados e 10 bps por
operação one-way. Ele é explicitamente uma **adaptação**: faltam shares outstanding históricos
para `dOwn`, e posição institucional não é criação/resgate primário.

| teste full sample | IC médio | t-NW do IC | spread líquido médio | t-NW spread | veredito |
|---|---:|---:|---:|---:|---|
| reversão bruta, 63d | 0,0385 | 1,49 | 0,09% | 0,22 | fraco |
| reversão bruta, 126d | 0,0600 | 1,94 | 0,63% | 1,04 | sugestivo, não aprovado |
| quality tilt, 63d | 0,0400 | 1,45 | 0,22% | 0,56 | não melhora robustamente |

O aparente efeito pré-2022 desaparece pós-2021, quando os spreads líquidos são negativos ou
estatisticamente indistinguíveis de zero. Não houve seleção de sinal/horizonte pelo melhor
resultado. Veja [RESEARCH_REPORT.md](results/RESEARCH_REPORT.md) e `results/summary.csv`.

## O que está implementado

| # | hipótese | implementação | estado empírico |
|---:|---|---|---|
| 1 | demanda ETF → reversão do basket | `lookthrough_pressure` | bloqueada sem baskets históricos + AUM/SO |
| 2 | pressão × fragilidade | covariância encolhida, forma quadrática exata | bloqueada sem fluxo primário e baskets |
| 3 | pressão especializada | contribuição auditável × score | bloqueada sem baskets históricos |
| 4 | holder run-prone | turnover apenas passado + share transitória | componente ETF testado; look-through pendente |
| 5 | direto vs ETF | projeção de sleeve e residual por gestor | código/testes prontos; baskets pendentes |
| 6 | rede de overlap | `sum(min(w_ei,w_fi))` e choque de pares | código/testes prontos; baskets pendentes |
| 7 | ETF footprint × reversão | gatilho rápido × estado lento | código pronto; footprint histórico pendente |
| 8 | ETF intensity | pesos neutral/tilt/especialista, sempre defasados | testado como ablação no baseline |
| 9 | mudança bruta de ownership | versão exata aceita shares outstanding | proxy 13F testado e reprovado |

Também há `filing_time_demand_nowcast`, que libera contribuições no timestamp real. O backtest
materializado usa o corte conservador D+70 para comparabilidade com a análise exploratória do
repositório; o próximo estudo de produção deve construir o nowcast filing-by-filing.

## Como reproduzir

No diretório deste projeto:

```powershell
python -m pytest -q
python scripts/build_panels.py
python scripts/fetch_etf_prices.py
python scripts/run_baselines.py
python scripts/write_research_report.py
```

O primeiro script consome os parquets point-in-time de `factors/general_plan/data/quarters` e
não duplica os 58 milhões de registros brutos. O fetch de preços é o único passo com rede.

## Estrutura

- `src/etf_positioning/`: universo, relógio PIT, nove sinais e avaliação.
- `reference/etf_master_seed.csv`: CUSIP/ticker/classe/estilo e fonte de verificação.
- `data/`: painéis derivados e preços pinados.
- `results/`: eventos, resumo e relatório numérico.
- `docs/METHODOLOGY.md`: fórmulas, correspondência com os papers e limites.
- `docs/DATA_CONTRACTS.md`: schemas necessários para liberar #1–#7 sem atalhos.
- `tests/`: invariantes de lookahead, emendas, fórmulas, splits e timing.

## O que não deve ser afirmado

- posição 13F em ETF **não** é fluxo de criação/resgate;
- `fund` **não** equivale a ETF;
- ETF intensity **não** identifica legalmente um gestor passivo;
- cesta atual **não** pode preencher o passado;
- o baseline medido **não** sobreviveu como alpha fora do período inicial.

