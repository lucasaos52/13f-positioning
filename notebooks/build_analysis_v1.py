"""Builds analysis_v1.ipynb (cells only; run prep_analysis_v1.py first).

The notebook reads the small CSVs from notebooks/data/ and stays light, so
it re-executes in seconds — same build-script pattern the reference project
uses to keep notebooks reproducible.
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def md(src: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": src}


def code(src: str) -> dict:
    return {"cell_type": "code", "metadata": {}, "source": src,
            "outputs": [], "execution_count": None}


CELLS = [
    md("""# 13F — análise exploratória v1

Base: `crowdflow/data/20_curated` — **58,0M posições, 397.833 filings, 16.327 filers, 2013Q2→2026Q1**,
validada em `crowdflow/docs/BASE_VALIDATION.md` (22/22).

**Disciplina point-in-time desta análise**: cada trimestre foi materializado via
`store.as_of(p, p + 70 dias)` — o que era público 70 dias após o fim do trimestre
(~95% dos originais). Exploração ≈ formação de portfólio; a esteira de produção usa o
calendário de ativação por cobertura. Nada aqui enxerga além do vantage.

Preparado por `prep_analysis_v1.py`; este notebook só lê os agregados e plota."""),

    code("""import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick

DATA = "data"
plt.rcParams.update({"figure.figsize": (11, 4.5), "axes.grid": True,
                     "grid.alpha": 0.3, "axes.spines.top": False,
                     "axes.spines.right": False})

funds = pd.read_csv(f"{DATA}/funds_per_quarter.csv", parse_dates=["period_end"])
aum = pd.read_csv(f"{DATA}/aum_per_quarter.csv", parse_dates=["period_end"])
elig = pd.read_csv(f"{DATA}/eligibility_per_quarter.csv", parse_dates=["period_end"])
panel = pd.read_csv(f"{DATA}/imbalance_panel.csv.gz", parse_dates=["period_end"])
agg = pd.read_csv(f"{DATA}/imbalance_agg.csv", parse_dates=["period_end"])
splits = pd.read_csv(f"{DATA}/split_adjustments.csv", parse_dates=["period_end"])
print(f"{len(funds)} trimestres | painel de imbalance: {len(panel):,} stock-quarters")"""),

    md("""## 1. Quantidade de fundos ao longo do tempo

Dois cortes: quantos **arquivaram** um 13F-HR original para o trimestre, e quantos
estavam **visíveis no vantage** (filaram até p+70d). A distância entre as linhas são
os atrasados crônicos. O crescimento secular vem do threshold de $100M nunca ter
sido indexado à inflação — o universo de filers cresce mecanicamente."""),

    code("""fig, ax = plt.subplots()
ax.plot(funds.period_end, funds.originals_filed, label="13F-HR originais no trimestre", lw=2)
ax.plot(funds.period_end, funds.filers_visible, label="visíveis no vantage (p+70d)", lw=2)
ax.set_title("Fundos 13F por trimestre")
ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f"{x:,.0f}"))
ax.legend()
plt.tight_layout(); plt.show()
print(funds.tail(4).to_string(index=False))"""),

    md("""## 2. "AUM" agregado ao longo do tempo

Aspas obrigatórias: 13F reporta só o **book long de equities/opções dos filers** —
sem shorts, sem bonds, sem caixa, sem posições < de minimis. É a melhor proxy pública
de capital institucional em equities US, não AUM de verdade."""),

    code("""fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
axes[0].plot(aum.period_end, aum.total_book_usd / 1e12, lw=2)
axes[0].set_title("Book 13F agregado (US$ tri)")
axes[0].set_ylabel("US$ trilhões")
axes[1].plot(aum.period_end, aum.top10_share * 100, lw=2, color="darkred")
axes[1].set_title("Concentração: share dos 10 maiores filers (%)")
axes[1].yaxis.set_major_formatter(mtick.PercentFormatter())
plt.tight_layout(); plt.show()
print(f"book total {aum.period_end.iloc[-1].date()}: "
      f"US$ {aum.total_book_usd.iloc[-1]/1e12:.1f} tri | "
      f"top-10 share: {aum.top10_share.iloc[-1]:.0%}")"""),

    md("""## 3. Universo dinâmico de fundos — a parte independente de preço

O universo do crowdflow filtra por elegibilidade e ranqueia por
impacto/centralidade/turnover. Impacto e centralidade precisam do painel de preços
(ADV, vol) — ainda pendente. O funil de **elegibilidade** já é computável só com a
base 13F: book ≥ $500M → ≥15 posições → top1 ≤ 60% → ≥4 trimestres de histórico."""),

    code("""fig, ax = plt.subplots()
for col, lbl in [("all_filers", "todos os filers"),
                 ("book_ge_500m", "book ≥ $500M"),
                 ("and_ge_15_pos", "+ ≥15 posições"),
                 ("and_top1_le_60", "+ top1 ≤ 60%"),
                 ("and_hist_ge_4q", "+ ≥4 tri de histórico (= elegíveis)")]:
    ax.plot(elig.period_end, elig[col], label=lbl, lw=2)
ax.set_title("Funil de elegibilidade do universo de gestores")
ax.set_yscale("log")
ax.legend(fontsize=8)
plt.tight_layout(); plt.show()
print(elig.tail(3).to_string(index=False))"""),

    md("""## 4. O sinal do paper — imbalances de Miori & Cucuringu (2022)

Por ação e trimestre, sobre o Δshares dos gestores presentes em **ambos** os
trimestres (senão o delta mede churn de filing, não trading):

- **TI** (trade-count) = (n_compras − n_vendas) / n_ativos — o herding puro;
- **VI** (volume) = (Σcompras − Σ|vendas|) / (Σcompras + Σ|vendas|);
- filtro de **≥10 gestores ativos** (o m do paper — TI=+1 com 1 fundo não é crowding);
- o paper opera **contra** o imbalance extremo (reversal de pressão de preço),
  melhor em 21–42 dias úteis, retorno relativo ao SPY, equal-weight nos top-quantis.

### Eventos corporativos: por que "normaliza, então tanto faz" está errado

13F reporta shares **as-filed**. Um split 4:1 multiplica o count de *todos* os
holders por 4 ao mesmo tempo → todo mundo vira "comprador" → TI → +1. A
normalização remove magnitude, **não um sinal compartilhado** — o split fabrica
consenso de compra perfeito. E shares outstanding do Yahoo não resolve: só existe o
valor corrente, não o histórico não-ajustado do dia.

A saída usada aqui (sem vendor): **os próprios holders são o detector, via átomo
modal**. A posição não-tocada tem ratio shares_t/shares_{t-1} = *exatamente* o fator
do split; quem também negociou se espalha ao redor. No 4:1 da AAPL (2.745 holders
comuns) o IQR dos ratios é 10% — qualquer teste de dispersão falha — mas 16,6% dos
holders caem em exatamente 4,00: um átomo que trading comum não produz, porque
centenas de gestores independentes nunca pousam no mesmo ratio exato ≠1 por escolha.
Regra (calibrada nos splits famosos, medidos): ratio modal (2 casas) fora de
[0,83; 1,2], aceito por **massa** (≥10% dos holders) *ou* por **dominância** (≥30
holders no átomo e ≥2,5× o segundo átomo) — necessária porque em mega-held names a
maioria dos holders negocia todo trimestre e a massa do átomo cai a 5-9% (AAPL 4:1:
167 de 2.745 holders em exatamente 4,00, contra 52 do vizinho). Abordagens sem tratamento de split
contornou o problema usando medidas por valor/contagem em nível; para Δshares o
ajuste é obrigatório."""),

    code("""fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
axes[0].hist(panel.ti.dropna(), bins=41, edgecolor="white")
axes[0].set_title(f"Distribuição de TI (todas as {len(panel):,} stock-quarters, n_ativos ≥ 10)")
axes[0].set_xlabel("trade-count imbalance")
axes[1].plot(agg.period_end, agg.ti_mean, label="TI médio", lw=2)
axes[1].plot(agg.period_end, agg.vi_mean, label="VI médio", lw=2)
axes[1].plot(agg.period_end, agg.pct_ti_extreme, label="% |TI| ≥ 0.5", lw=2)
axes[1].axhline(0, color="k", lw=0.5)
axes[1].set_title("Imbalance agregado ao longo do tempo")
axes[1].legend()
plt.tight_layout(); plt.show()
print(agg.tail(4).round(3).to_string(index=False))"""),

    md("""O TI médio positivo é estrutural (instituições acumulam equities em agregado);
o sinal do paper é o **cross-section** — quem está no extremo relativo aos demais.
Os picos de dispersão marcam os trimestres de stress (2020Q1, 2022)."""),

    code("""# diagnóstico do detector de eventos corporativos
per_q = splits.groupby(splits.period_end.dt.to_period("Q")).size()
fig, ax = plt.subplots()
per_q.plot(kind="bar", ax=ax, width=0.85)
ax.set_title(f"Eventos corporativos detectados pelos próprios holders ({len(splits)} no total)")
ax.set_xticklabels([str(x) for x in per_q.index], rotation=90, fontsize=6)
plt.tight_layout(); plt.show()
# prova de fogo: os splits famosos, pescados sem nenhum vendor
FAMOSOS = {"037833100": "AAPL 4:1 (ago/2020)", "88160R101": "TSLA 5:1 (ago/2020)",
           "67066G104": "NVDA 4:1 (jul/2021) e 10:1 (jun/2024)"}
hit = splits[splits.instrument_id.isin(FAMOSOS)]
hit = hit.assign(nome=hit.instrument_id.map(FAMOSOS))
print(hit.sort_values("period_end").to_string(index=False))
print("\\nmaiores por nº de holders:")
print(splits.nlargest(8, "n_holders").to_string(index=False))"""),

    md("""### Caveat honesto: os extremos ±1,0 têm poluição de troca de CUSIP

Nos top-consenso abaixo, vários nomes com TI = ±1,0 e centenas de gestores
"unânimes" são **o mesmo papel trocando de CUSIP** (reorganização, mudança de share
class): o identificador antigo vira 100% "venda" e o novo vira 100% "compra" — churn
de identificador, não trading. O detector de splits não pega (são instrumentos
diferentes). A correção é o crosswalk **datado** CUSIP→instrumento (CRSP `ncusip`),
já previsto na camada de identificadores do crowdflow. Até lá: extremos exatamente
±1,0 com muitos gestores merecem desconfiança — mais um argumento pro filtro de
quantil do paper em vez do extremo absoluto."""),

    md("""## 5. Onde o crowding está agora

Top consenso de compra e de venda no último trimestre do painel (TI, com o piso de
gestores ativos). Identificadores são CUSIPs — o crosswalk para ticker/nome entra
com o painel de preços."""),

    code("""last = panel[panel.period_end == panel.period_end.max()]
cols = ["instrument_id", "n_buy", "n_sell", "n_active", "ti", "vi"]
print(f"trimestre: {panel.period_end.max().date()}")
print("\\n=== consenso de COMPRA (paper: candidatos a SHORT contrário) ===")
print(last[last.n_active >= 100].nlargest(10, "ti")[cols].round(3).to_string(index=False))
print("\\n=== consenso de VENDA (paper: candidatos a LONG contrário) ===")
print(last[last.n_active >= 100].nsmallest(10, "ti")[cols].round(3).to_string(index=False))"""),

    md("""## Próximos passos

1. **Backtest do sinal** na infra `factors/` (Yahoo): contrário aos top-quantis de
   |TI| e |VI|, horizontes 5/10/21/42/63d, retorno relativo ao SPY, equal-weight —
   a réplica fiel do paper, com o timing honesto do calendário de ativação;
2. sweep do filtro de gestores ativos (o paper mostra que mais atividade **não** é
   monotonicamente melhor) e dos quantis;
3. crosswalk CUSIP→ticker para casar com o painel Yahoo (e nomear os extremos acima);
4. cruzar com o universo dinâmico: TI calculado só sobre os top-25 transmissores de
   demanda vs. todos os filers — a tese do crowdflow em cima do sinal do paper."""),
]

nb = {
    "cells": CELLS,
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.12"},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

out = HERE / "analysis_v1.ipynb"
out.write_text(json.dumps(nb, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"wrote {out}")
