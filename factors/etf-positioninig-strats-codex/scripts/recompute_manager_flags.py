"""Recompute precision-first manager flags from already materialized panels."""

from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "src"))

from etf_positioning.config import ResearchConfig  # noqa: E402
from etf_positioning.universe import manager_quality_weights, manager_style_flags  # noqa: E402


def main() -> None:
    cfg, data = ResearchConfig(), HERE / "data"
    features = pd.read_csv(data / "manager_features.csv.gz", parse_dates=["period_end", "knowledge_date"])
    state = pd.read_csv(data / "manager_etf_state.csv.gz", parse_dates=["period_end", "knowledge_date"])
    if "fund_candidate_value_usd" not in features:
        features["fund_candidate_value_usd"] = features["etf_value_usd"]
        features["fund_candidate_intensity"] = features["etf_intensity"]
    verified_value = state.groupby(["filer_id", "period_end"])["value_usd"].sum()
    equity_value = state[state["asset_class"].eq("equity")].groupby(
        ["filer_id", "period_end"]
    )["value_usd"].sum()
    keys = pd.MultiIndex.from_frame(features[["filer_id", "period_end"]])
    features["etf_value_usd"] = verified_value.reindex(keys, fill_value=0.0).to_numpy()
    features["equity_etf_value_usd"] = equity_value.reindex(keys, fill_value=0.0).to_numpy()
    den = features["aum_13f_equity_usd"].replace(0.0, np.nan)
    features["etf_intensity"] = features["etf_value_usd"] / den
    features["equity_etf_intensity"] = features["equity_etf_value_usd"] / den
    stale = ["manager_style", "passive_manager", "passive_manager_reason", "turnover_history_pct",
             "transient", "lag_etf_intensity", "weight_neutral", "weight_direct_tilt",
             "weight_direct_specialist"]
    features = features.drop(columns=[c for c in stale if c in features])
    features = manager_style_flags(features, cfg)
    weights = manager_quality_weights(features)
    features = features.merge(weights.drop(columns=["etf_intensity", "eligible_base"]),
                              on=["filer_id", "period_end"], how="left", validate="one_to_one")

    state = state.drop(columns=[c for c in stale if c in state] + [
        c for c in state if c.startswith("shares_weight_") or c == "transient_shares"
    ])
    state = state.merge(features[["filer_id", "period_end", "transient", "weight_neutral",
                                  "weight_direct_tilt", "weight_direct_specialist"]],
                        on=["filer_id", "period_end"], how="left", validate="many_to_one")
    for col in ["weight_neutral", "weight_direct_tilt", "weight_direct_specialist"]:
        state[f"shares_{col}"] = state["shares"] * state[col].fillna(0.0)
    state["transient_shares"] = state["shares"] * state["transient"].fillna(False)
    aggregate = state.groupby(
        ["period_end", "knowledge_date", "etf_id", "ticker", "asset_class", "etf_style"], as_index=False
    ).agg(
        institutional_shares=("shares", "sum"), neutral_shares=("shares_weight_neutral", "sum"),
        direct_tilt_shares=("shares_weight_direct_tilt", "sum"),
        direct_specialist_shares=("shares_weight_direct_specialist", "sum"),
        transient_shares=("transient_shares", "sum"), disclosed_value_usd=("value_usd", "sum"),
        n_managers=("filer_id", "nunique"),
    )
    aggregate["run_prone_share"] = aggregate["transient_shares"] / aggregate[
        "institutional_shares"
    ].replace(0.0, np.nan)
    features.to_csv(data / "manager_features.csv.gz", index=False)
    state.to_csv(data / "manager_etf_state.csv.gz", index=False)
    aggregate.to_csv(data / "etf_aggregate_state.csv.gz", index=False)
    print(f"recomputed {len(features):,} manager quarters using verified ETFs")


if __name__ == "__main__":
    main()
