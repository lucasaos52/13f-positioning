"""Build compact point-in-time ETF/manager panels from repository parquets."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE / "src"))

from etf_positioning.config import ResearchConfig  # noqa: E402
from etf_positioning.panel import manager_turnover, snapshot_as_of  # noqa: E402
from etf_positioning.universe import manager_quality_weights, manager_style_flags  # noqa: E402


def log(message: str) -> None:
    print(f"{time.strftime('%H:%M:%S')} - {message}", flush=True)


def _manager_features(snap: pd.DataFrame, turnover: pd.Series, cfg: ResearchConfig) -> pd.DataFrame:
    g = snap.groupby("filer_id")
    out = g.agg(
        aum_13f_equity_usd=("value_usd", "sum"),
        n_positions=("instrument_id", "nunique"),
        largest_position_usd=("value_usd", "max"),
    )
    candidate = snap["instrument_class"].eq("fund")
    fund_value = snap[candidate].groupby("filer_id")["value_usd"].sum()
    out["fund_candidate_value_usd"] = fund_value.reindex(out.index, fill_value=0.0)
    out["fund_candidate_intensity"] = (
        out["fund_candidate_value_usd"] / out["aum_13f_equity_usd"].replace(0, np.nan)
    )
    out["top1_weight"] = out["largest_position_usd"] / out["aum_13f_equity_usd"].replace(0, np.nan)
    out["turnover"] = turnover.reindex(out.index)
    out["eligible_base"] = (
        out["aum_13f_equity_usd"].ge(cfg.min_manager_book_usd)
        & out["n_positions"].ge(cfg.min_manager_positions)
    )
    return out.reset_index()


def main(smoke: bool = False) -> None:
    cfg = ResearchConfig()
    qdir = ROOT / "factors" / "general_plan" / "data" / "quarters"
    outdir = HERE / ("data_smoke" if smoke else "data")
    outdir.mkdir(exist_ok=True)
    master = pd.read_csv(HERE / "reference" / "etf_master_seed.csv", dtype={"instrument_id": str})
    verified = set(master[master["is_etf"]]["instrument_id"])
    files = sorted(qdir.glob("q_*.parquet"))
    files = [p for p in files if pd.Timestamp("2013-06-30") <= pd.Timestamp(p.stem[2:])]
    if smoke:
        files = files[-8:]

    feature_parts, etf_parts, audit_parts = [], [], []
    for i, path in enumerate(files):
        period = pd.Timestamp(path.stem[2:])
        decision = period + pd.Timedelta(days=cfg.snapshot_lag_days)
        cur = snapshot_as_of(path, decision)
        if cur.empty:
            continue
        if i:
            prev = snapshot_as_of(files[i - 1], decision)
            turn = manager_turnover(cur, prev)
        else:
            turn = pd.Series(dtype=float)
        f = _manager_features(cur, turn, cfg)
        f["period_end"] = period
        f["knowledge_date"] = decision
        feature_parts.append(f)

        h = cur[cur["instrument_id"].isin(verified)].copy()
        h = h.rename(columns={"instrument_id": "etf_id"})
        h = h.merge(
            master[["instrument_id", "ticker", "asset_class", "etf_style", "specialized_score"]]
            .rename(columns={"instrument_id": "etf_id"}), on="etf_id", how="left", validate="many_to_one"
        )
        etf_parts.append(h[[
            "filer_id", "period_end", "knowledge_date", "etf_id", "ticker",
            "asset_class", "etf_style", "specialized_score", "shares", "value_usd",
        ]])
        funds = cur[cur["instrument_class"].eq("fund")]
        audit_parts.append(funds.groupby("instrument_id", as_index=False).agg(
            disclosed_value_usd=("value_usd", "sum"), n_managers=("filer_id", "nunique")
        ).assign(period_end=period))
        log(f"{period.date()} managers={f.shape[0]:,} verified ETF rows={len(h):,}")

    features = pd.concat(feature_parts, ignore_index=True)
    state = pd.concat(etf_parts, ignore_index=True)
    verified_value = state.groupby(["filer_id", "period_end"])["value_usd"].sum()
    equity_value = state[state["asset_class"].eq("equity")].groupby(
        ["filer_id", "period_end"]
    )["value_usd"].sum()
    key = pd.MultiIndex.from_frame(features[["filer_id", "period_end"]])
    features["etf_value_usd"] = verified_value.reindex(key, fill_value=0.0).to_numpy()
    features["equity_etf_value_usd"] = equity_value.reindex(key, fill_value=0.0).to_numpy()
    denominator = features["aum_13f_equity_usd"].replace(0, np.nan)
    features["etf_intensity"] = features["etf_value_usd"] / denominator
    features["equity_etf_intensity"] = features["equity_etf_value_usd"] / denominator
    features = manager_style_flags(features, cfg)
    weights = manager_quality_weights(features)
    features = features.merge(
        weights.drop(columns=["etf_intensity", "eligible_base"]),
        on=["filer_id", "period_end"], how="left", validate="one_to_one"
    )
    state = state.merge(
        features[["filer_id", "period_end", "transient", "weight_neutral",
                  "weight_direct_tilt", "weight_direct_specialist"]],
        on=["filer_id", "period_end"], how="left", validate="many_to_one"
    )

    for col in ["weight_neutral", "weight_direct_tilt", "weight_direct_specialist"]:
        state[f"shares_{col}"] = state["shares"] * state[col].fillna(0.0)
    state["transient_shares"] = state["shares"] * state["transient"].fillna(False)
    aggregate = state.groupby(
        ["period_end", "knowledge_date", "etf_id", "ticker", "asset_class", "etf_style"], as_index=False
    ).agg(
        institutional_shares=("shares", "sum"),
        neutral_shares=("shares_weight_neutral", "sum"),
        direct_tilt_shares=("shares_weight_direct_tilt", "sum"),
        direct_specialist_shares=("shares_weight_direct_specialist", "sum"),
        transient_shares=("transient_shares", "sum"),
        disclosed_value_usd=("value_usd", "sum"),
        n_managers=("filer_id", "nunique"),
    )
    aggregate["run_prone_share"] = aggregate["transient_shares"] / aggregate[
        "institutional_shares"
    ].replace(0, np.nan)

    audit = pd.concat(audit_parts, ignore_index=True)
    audit = audit.groupby("instrument_id", as_index=False).agg(
        first_period=("period_end", "min"), last_period=("period_end", "max"),
        n_periods=("period_end", "nunique"), disclosed_value_usd=("disclosed_value_usd", "sum"),
        max_managers=("n_managers", "max"),
    )
    issuer_path = ROOT / "notebooks" / "data" / "cusip_issuer.csv.gz"
    if issuer_path.exists():
        audit = audit.merge(pd.read_csv(issuer_path, dtype={"instrument_id": str})[
            ["instrument_id", "issuer"]], on="instrument_id", how="left")
    audit = audit.merge(master[["instrument_id", "ticker", "asset_class", "etf_style"]],
                        on="instrument_id", how="left")
    audit["verified_seed"] = audit["ticker"].notna()

    features.to_csv(outdir / "manager_features.csv.gz", index=False)
    state.to_csv(outdir / "manager_etf_state.csv.gz", index=False)
    aggregate.to_csv(outdir / "etf_aggregate_state.csv.gz", index=False)
    audit.sort_values("disclosed_value_usd", ascending=False).to_csv(
        outdir / "fund_candidate_audit.csv", index=False
    )
    log(f"wrote {outdir.name}/ | config={cfg.fingerprint()} | {len(aggregate):,} ETF-quarter rows")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    main(**vars(parser.parse_args()))
