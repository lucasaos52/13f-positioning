# Estratégias de posicionamento em ETFs via 13F

Implementação das cinco ideias de `13F_ETF_Positioning_Signals_5_Ideias.md` com o relógio
point-in-time preservado e backtest pelo mesmo `Indicator -> Portfolio -> Backtest` usado no
framework multifatorial do repositório.

## Universo

O universo primário **não** usa `instrument_class == fund` como sinônimo de ETF. Essa flag gera
16,8 mil candidatos e mistura ETFs, closed-end funds, BDCs, trusts e ruído de classificação.
A estratégia usa apenas CUSIPs/FIGIs com ticker e classe de ativo verificados no master oficial
reconstruído abaixo. Na construção até 2026Q1 são 4.421 produtos ETF, dos quais 2.208 são de
ações e 1.266 são passivos de ações; a presença de preço e liquidez é recalculada em cada evento
somente com história disponível até ali. Toda a cauda fica em
`data/universe_candidate_audit.csv`, com o motivo de exclusão explícito.

Os sinais que dependem de churn exigem também trimestre anterior elegível e pelo menos 50% do
livro anterior com retorno individual mapeado. O restante não recebe uma qualidade artificial;
continua contando em breadth/ownership, mas fica fora de `StickyDemand`, `DoubleDown` e do
numerador de fragilidade.

Essa escolha reduz o cross-section, sobretudo de ETFs temáticos, mas evita um erro de identidade
que invalidaria breadth, consenso e fragilidade. Gestores não são classificados como ativos ou
passivos a partir de ETF intensity: isso não é identificável pela 13F.

### Reconstrução oficial do universo

`build_etf_universe.py` substitui a triagem manual por uma cadeia auditável de identidade:

1. `instrument_id` de nove caracteres é consultado como CUSIP; IDs `BBG...` já presentes na
   13F são consultados como FIGI;
2. OpenFIGI faz somente a ponte para o composite dos EUA (`exchCode=US`);
3. a flag ETF é confirmada pelo campo explícito `ETF=Y` dos diretórios Nasdaq ou por `IS_ETF=Y`
   do Form N-CEN, mas apenas quando o identificador é um ETP no OpenFIGI;
4. `IS_INDEX` do N-CEN gera a flag passiva; Series/Class anual fornece a ponte regulatória para
   produtos históricos anteriores ao N-CEN;
5. nome e janela temporal vetam ticker reciclado; isso impede, por exemplo, que a classe antiga
   `IBIT` contamine o iShares Bitcoin Trust atual;
6. aliases CUSIP/FIGI do mesmo produto permanecem no mapa de instrumentos, mas a contagem do
   universo é feita por ticker único.

```powershell
C:\Users\lsilva\Documents\13f_v2\crowdflow\.venv\Scripts\python.exe factors/ETF_strat/build_etf_universe.py --through 2026q1
```

Os downloads brutos ficam em `data/reference_raw/`; os derivados regulatórios e o cache
retomável do OpenFIGI em `data/reference/`. A entrega principal é
`data/etf_universe_flags.csv`, com uma linha por identificador 13F, fontes, confiança, conflitos,
classe de ativo e as flags `is_etf`, `is_index_fund`, `is_equity_etf` e
`is_passive_equity_etf`. Nenhum match apenas textual recebe `is_etf=True`.

## Sinais

- `sticky_quality`: trade em peso contra o portfólio driftado, ponderado pela qualidade de churn;
- `double_down_specific`: compra de ETF específico depois de retorno residual negativo;
- `abnormal_adoption`: mudança no breadth residualizado por ownership e características públicas;
- `ccp`: conviction no ETF sleeve × qualidade × persistência;
- `fragility_stress` e `fragility_reversal`: duas previsões condicionais da quinta hipótese.

Cada ideia inclui ablações pré-definidas. Nenhum metasignal é criado automaticamente.

## Relógio

Emendas são resolvidas por CIK e só depois agregadas por família. O parquet preserva a data, não
o timestamp intradiário; por isso o livro selecionado de um gestor é liberado inteiro na sua
última data selecionada. Isso pode atrasar um original, mas nunca antecipa uma emenda. O target é
aplicado no primeiro pregão posterior ao filing, e o P&L compartilhado usa pesos defasados.

## Execução

```powershell
C:\Users\lsilva\Documents\13f_v2\crowdflow\.venv\Scripts\python.exe -m pytest -q factors/ETF_strat/tests
C:\Users\lsilva\Documents\13f_v2\crowdflow\.venv\Scripts\python.exe factors/ETF_strat/fetch_etf_prices.py --scope all
C:\Users\lsilva\Documents\13f_v2\crowdflow\.venv\Scripts\python.exe factors/ETF_strat/run_research.py --smoke
C:\Users\lsilva\Documents\13f_v2\crowdflow\.venv\Scripts\python.exe factors/ETF_strat/run_research.py
C:\Users\lsilva\Documents\13f_v2\crowdflow\.venv\Scripts\python.exe factors/ETF_strat/run_research.py --backtest-only
C:\Users\lsilva\Documents\13f_v2\crowdflow\.venv\Scripts\python.exe factors/ETF_strat/evaluate_candidates.py
```

O downloader usa cache retomável por ticker e materializa preços ajustados/raw, volume, splits,
manifesto e resumo de cobertura para os 4.421 produtos verificados. O smoke valida oito trimestres.
A execução cheia materializa a amostra completa, a escada de custos, ICs e `results/REPORT.md`;
`--backtest-only` reutiliza os eventos PIT. `evaluate_candidates.py` testa a família CCP contra o
consenso simples, universos específico/passivo e controles públicos, escrevendo a auditoria causal
em `results/candidate_diagnostics/REPORT.md`.
