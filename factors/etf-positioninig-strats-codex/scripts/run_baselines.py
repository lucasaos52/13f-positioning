"""Run feasible 13F-only ETF demand baselines without pretending they are flows."""

from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE / "src"))

from etf_positioning.config import ResearchConfig  # noqa: E402
from etf_positioning.evaluation import event_study  # noqa: E402


def _split_adjusted_change(panel: pd.DataFrame, value_col: str, splits: pd.DataFrame) -> pd.Series:
    x = panel.sort_values(["ticker", "period_end"]).copy()
    x["lag"] = x.groupby("ticker")[value_col].shift(1)
    ratio = splits.set_index(["period_end", "etf_id"])["ratio"]
    keys = pd.MultiIndex.from_frame(x[["period_end", "etf_id"]])
    x["lag_adjusted"] = x["lag"] * ratio.reindex(keys).fillna(1.0).to_numpy()
    denominator = (x[value_col].abs() + x["lag_adjusted"].abs()) / 2.0
    change = (x[value_col] - x["lag_adjusted"]) / denominator.replace(0.0, np.nan)
    return change.reindex(panel.index)


def _zscore(s: pd.Series) -> pd.Series:
    if s.notna().sum() < 5:
        return pd.Series(np.nan, index=s.index)
    lo, hi = s.quantile([0.01, 0.99])
    w = s.clip(lo, hi)
    sd = w.std(ddof=0)
    return (w - w.mean()) / sd if sd > 0 else pd.Series(0.0, index=s.index)


def main() -> None:
    cfg = ResearchConfig()
    data = HERE / "data"
    results = HERE / "results"
    results.mkdir(exist_ok=True)
    state = pd.read_csv(data / "etf_aggregate_state.csv.gz", parse_dates=["period_end", "knowledge_date"])
    state = state[state["asset_class"].eq("equity") & state["n_managers"].ge(10)].copy()
    split_path = ROOT / "notebooks" / "data" / "split_adjustments.csv"
    splits = pd.read_csv(split_path, dtype={"instrument_id": str}, parse_dates=["period_end"])[
        ["period_end", "instrument_id", "ratio"]
    ].rename(columns={"instrument_id": "etf_id"})
    for col in ["institutional_shares", "direct_tilt_shares", "direct_specialist_shares"]:
        state[f"change_{col}"] = _split_adjusted_change(state, col, splits)
    state["raw_reversal"] = -state.groupby("period_end")["change_institutional_shares"].transform(_zscore)
    state["quality_reversal"] = -state.groupby("period_end")["change_direct_tilt_shares"].transform(_zscore)
    state["specialist_reversal"] = -state.groupby("period_end")["change_direct_specialist_shares"].transform(_zscore)
    state["run_prone_reversal"] = state["raw_reversal"] * state["run_prone_share"].fillna(0.0)
    prices = pd.read_csv(data / "etf_prices_adjusted.csv.gz", index_col=0, parse_dates=True)

    summaries = []
    for signal_name in ["raw_reversal", "quality_reversal", "specialist_reversal", "run_prone_reversal"]:
        sig = state[["period_end", "knowledge_date", "ticker", signal_name]].rename(
            columns={"knowledge_date": "available_date", signal_name: "signal"}
        ).dropna()
        events, summary = event_study(
            sig, prices, cfg.horizons_days, cfg.quantile_fraction, cfg.trading_cost_bps
        )
        if events.empty:
            continue
        events["signal_name"] = signal_name
        events.to_csv(results / f"events_{signal_name}.csv", index=False)
        summary["signal_name"] = signal_name
        summary["sample"] = "full"
        summaries.append(summary)
        for label, mask in {
            "pre_2022": sig["period_end"] < pd.Timestamp("2022-01-01"),
            "post_2021": sig["period_end"] >= pd.Timestamp("2022-01-01"),
        }.items():
            _, sub = event_study(sig[mask], prices, cfg.horizons_days,
                                 cfg.quantile_fraction, cfg.trading_cost_bps)
            if not sub.empty:
                sub["signal_name"], sub["sample"] = signal_name, label
                summaries.append(sub)
    out = pd.concat(summaries, ignore_index=True)
    out.to_csv(results / "summary.csv", index=False)
    headline = out[(out["sample"].eq("full")) & (out["horizon"].isin([21, 63]))]
    report = [
        "# Resultado empirico: demanda institucional por ETF", "",
        "Todos os sinais entram somente em period_end + 70 dias. O teste e uma adaptacao 13F:",
        "mudanca nas acoes de ETF divulgadas por instituicoes nao e criacao/resgate no mercado primario.",
        "A ausencia de shares outstanding historico tambem impede chamar a medida de delta de ownership.", "",
        "Custos: 10 bps one-way; o spread liquido desconta entrada e saida das duas pernas.", "",
        headline.round(4).to_markdown(index=False), "",
        "O arquivo summary.csv contem 5/21/63/126 dias e cortes pre-2022/post-2021.",
    ]
    (results / "EMPIRICAL_REPORT.md").write_text("\n".join(report), encoding="utf-8")
    print(headline.to_string(index=False))


if __name__ == "__main__":
    main()
