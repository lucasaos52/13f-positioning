"""Write a human-readable report from pinned panels and backtest outputs."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parents[1]


def main() -> None:
    data, results = HERE / "data", HERE / "results"
    summary = pd.read_csv(results / "summary.csv")
    audit = pd.read_csv(data / "fund_candidate_audit.csv")
    features = pd.read_csv(data / "manager_features.csv.gz")
    state = pd.read_csv(data / "etf_aggregate_state.csv.gz")
    coverage = audit.loc[audit["verified_seed"], "disclosed_value_usd"].sum() / audit[
        "disclosed_value_usd"
    ].sum()
    last_period = features["period_end"].max()
    last = features[features["period_end"].eq(last_period)]
    headline = summary[(summary["sample"].eq("full")) & summary["horizon"].isin([21, 63, 126])]
    headline = headline[["signal_name", "horizon", "n_events", "n_names_median", "ic_mean",
                         "ic_t_nw", "spread_net_mean", "spread_net_t_nw",
                         "spread_net_sharpe_ann", "positive_share"]].round(4)
    stability = summary[(summary["signal_name"].eq("raw_reversal")) &
                        summary["horizon"].isin([63, 126])]
    stability = stability[["sample", "horizon", "n_events", "ic_mean", "ic_t_nw",
                           "spread_net_mean", "spread_net_t_nw"]].round(4)
    lines = [
        "# Relatorio de pesquisa — 13F x ETF positioning", "",
        "## Veredito", "",
        "O baseline 13F-only foi **reprovado como alpha de producao**. Ha IC positivo no periodo",
        "inicial e no horizonte longo, mas o spread liquido nao e significativo e o efeito nao",
        "sobrevive ao corte pos-2021. O resultado apoia a tese do blueprint de que ownership bruto",
        "deve ser apenas controle; o mecanismo forte exige baskets historicos e/ou fluxo primario.", "",
        "## Universo auditado", "",
        f"- {len(audit):,} instrumentos receberam `fund` em ao menos um snapshot.",
        f"- {int(audit['verified_seed'].sum()):,} ETFs verificados apareceram na base; cobertura de valor: {coverage:.1%}.",
        f"- {state['ticker'].nunique()} produtos no painel, {int((state['asset_class'] == 'equity').sum())} ETF-quarters de acoes.",
        f"- {len(last):,} gestores em {last_period}; mediana ETF intensity verificada {last['etf_intensity'].median():.1%}.",
        f"- A triagem `fund` teria mediana {last['fund_candidate_intensity'].median():.1%}: a diferenca mostra por que ela nao entra no sinal.",
        "- `passive_manager` nao foi inferido; estilos sao comportamentais e variam por trimestre.", "",
        "## Full sample — 10 bps one-way", "", headline.to_markdown(index=False), "",
        "## Estabilidade do baseline bruto", "", stability.to_markdown(index=False), "",
        "## Interpretacao", "",
        "- O raw reversal em 126d tem IC medio proximo de 0,06, mas t do spread liquido proximo de 1.",
        "- O quality tilt nao produz incremento estavel sobre o raw baseline.",
        "- Direct-specialist e run-prone nao resgatam o sinal ETF-level.",
        "- Resultado ETF-level nao testa ainda o principal uso de #8: ponderar a conviccao residual #5.",
        "- D+70 e honesto/conservador, mas nao e o nowcast filing-by-filing recomendado para producao.", "",
        "## O que falta para o teste principal", "",
        "Baskets historicos, AUM/shares outstanding point-in-time e fluxo primario. Sem esses contratos,",
        "#1–#4 nao podem ser apresentados como replicas da literatura. Consulte `docs/DATA_CONTRACTS.md`.",
    ]
    (results / "RESEARCH_REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    print(results / "RESEARCH_REPORT.md")


if __name__ == "__main__":
    main()
