"""Manager-level drift, filing-time updates and ETF event state."""

from __future__ import annotations

from collections import defaultdict

import numpy as np
import pandas as pd

from .config import ResearchConfig
from .signals import (
    ABLATION_SIGNALS,
    PRIMARY_SIGNALS,
    ZERO_BASED_SIGNALS,
    cross_sectional_z,
    score_event_state,
)


def _manager_stats(snapshot: pd.DataFrame, cfg: ResearchConfig) -> pd.DataFrame:
    if snapshot.empty:
        return pd.DataFrame(columns=["book_value", "n_positions", "eligible", "available_date"])
    out = snapshot.groupby("filer_id").agg(
        book_value=("value_usd", "sum"),
        n_positions=("instrument_id", "nunique"),
        available_date=("available_date", "max"),
    )
    out["eligible"] = out["book_value"].ge(cfg.min_manager_book_usd) & out["n_positions"].ge(
        cfg.min_manager_positions
    )
    return out


def initialize_manager_etf_state(
    snapshot: pd.DataFrame,
    master: pd.DataFrame,
    cfg: ResearchConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Seed stale state from the quarter immediately before the first test."""

    stats = _manager_stats(snapshot, cfg)
    e = snapshot[snapshot["instrument_id"].isin(master["instrument_id"])].copy()
    e = e.merge(
        master[["instrument_id", "ticker", "specialized_score", "etf_style"]],
        on="instrument_id",
        how="left",
        validate="many_to_one",
    )
    e = e.join(stats[["book_value", "eligible"]], on="filer_id")
    e["current_weight"] = e["value_usd"] / e["book_value"].replace(0.0, np.nan)
    held = e["value_usd"].gt(0) & e["eligible"]
    e["conviction"] = 0.0
    e.loc[held, "conviction"] = e.loc[held].groupby("filer_id")["current_weight"].rank(pct=True)
    e["quality"] = np.where(e["eligible"], 0.5, 0.0)
    e["churn_smoothed"] = np.where(e["eligible"], 0.5, np.nan)
    e["persistence_count"] = np.where(held, 1, 0)
    e["persistence"] = e["persistence_count"] / cfg.persistence_cap_quarters
    e["ccp"] = e["conviction"] * e["quality"] * e["persistence"]
    e["consensus"] = (e["conviction"] >= 0.90).astype(float) * e["quality"]
    e["state_value"] = e["value_usd"].where(held, 0.0)
    e["fragility_owner_value"] = e["state_value"]
    e["held_state"] = held.astype(float)
    e["churn_value"] = e["state_value"] * e["churn_smoothed"].fillna(0.0)
    cols = [
        "filer_id", "instrument_id", "ticker", "state_value", "held_state",
        "fragility_owner_value", "churn_value", "ccp", "consensus", "conviction", "quality",
        "churn_smoothed", "persistence_count", "persistence",
    ]
    return e[cols].copy(), stats


def build_manager_updates(
    current: pd.DataFrame,
    previous: pd.DataFrame,
    previous_state: pd.DataFrame,
    previous_stats: pd.DataFrame,
    master: pd.DataFrame,
    instrument_returns: pd.Series,
    spy_return: float,
    churn_history: dict[str, list[float]],
    residual_quarter: pd.Series,
    cfg: ResearchConfig,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, float]]:
    """Compute drift-adjusted manager ETF trades and state replacements."""

    cur_stats = _manager_stats(current, cfg)
    cur = current[["filer_id", "instrument_id", "value_usd"]].rename(
        columns={"value_usd": "current_value"}
    )
    prev = previous[["filer_id", "instrument_id", "value_usd"]].rename(
        columns={"value_usd": "previous_value"}
    )
    x = cur.merge(prev, on=["filer_id", "instrument_id"], how="outer").fillna(
        {"current_value": 0.0, "previous_value": 0.0}
    )
    # Only a current filing can replace stale state or release a current trade.
    release = cur_stats["available_date"]
    x["available_date"] = x["filer_id"].map(release)
    x = x[x["available_date"].notna()].copy()
    x["instrument_return"] = x["instrument_id"].map(instrument_returns)
    x["return_mapped"] = x["instrument_return"].notna()
    mapped_value = float(x.loc[x["return_mapped"], "previous_value"].sum())
    total_prev_value = float(x["previous_value"].sum())
    manager_prev_value = x.groupby("filer_id")["previous_value"].sum()
    manager_mapped_value = x[x["return_mapped"]].groupby("filer_id")["previous_value"].sum()
    manager_return_coverage = manager_mapped_value.reindex(manager_prev_value.index, fill_value=0.0).div(
        manager_prev_value.replace(0.0, np.nan)
    )
    x["instrument_return"] = x["instrument_return"].fillna(spy_return)
    x["drift_value"] = x["previous_value"] * (1.0 + x["instrument_return"].clip(lower=-0.999))
    current_books = x.groupby("filer_id")["current_value"].transform("sum").replace(0.0, np.nan)
    drift_books = x.groupby("filer_id")["drift_value"].transform("sum").replace(0.0, np.nan)
    x["current_weight"] = x["current_value"] / current_books
    x["drift_weight"] = x["drift_value"] / drift_books
    x["weight_change"] = x["current_weight"].fillna(0.0) - x["drift_weight"].fillna(0.0)
    churn = 0.5 * x.groupby("filer_id")["weight_change"].apply(lambda s: s.abs().sum())

    previous_eligible = previous_stats["eligible"].reindex(churn.index).fillna(False)
    history_eligible = (
        cur_stats["eligible"].reindex(churn.index).fillna(False)
        & previous_eligible
        & manager_return_coverage.reindex(churn.index).ge(cfg.min_manager_return_coverage).fillna(False)
    )
    smooth: dict[str, float] = {}
    for filer, value in churn[history_eligible].items():
        prior = churn_history.get(filer, [])[-(cfg.churn_smoothing_quarters - 1) :]
        smooth[filer] = float(np.mean([*prior, float(value)]))
    smooth_s = pd.Series(smooth, dtype=float)
    quality = pd.Series(0.0, index=smooth_s.index)
    if not smooth_s.empty:
        pct = smooth_s.rank(method="average", pct=True)
        quality.loc[pct.index] = (1.0 - pct).clip(0.05, 0.95)
    for filer, value in churn[history_eligible].items():
        churn_history.setdefault(filer, []).append(float(value))

    metrics = cur_stats.copy()
    metrics["churn"] = churn.reindex(metrics.index)
    metrics["churn_smoothed"] = smooth_s.reindex(metrics.index)
    metrics["quality"] = quality.reindex(metrics.index).fillna(0.0)
    metrics["return_mapping_coverage"] = manager_return_coverage.reindex(metrics.index)
    metrics["quality_eligible"] = history_eligible.reindex(metrics.index).fillna(False)

    e = x[x["instrument_id"].isin(master["instrument_id"])].copy()
    e = e.merge(
        master[["instrument_id", "ticker", "specialized_score", "etf_style", "is_specific"]],
        on="instrument_id",
        how="left",
        validate="many_to_one",
    )
    e["current_eligible"] = e["filer_id"].map(cur_stats["eligible"]).fillna(False)
    e["quality_eligible"] = e["filer_id"].map(history_eligible).fillna(False)
    e["previous_eligible"] = e["filer_id"].map(previous_stats["eligible"]).fillna(False)
    e["quality"] = e["filer_id"].map(quality).fillna(0.0)
    e["churn_smoothed"] = e["filer_id"].map(smooth_s)
    e["trade"] = e["weight_change"].where(e["quality_eligible"], 0.0)
    e["current_held"] = e["current_value"].gt(0.0) & e["current_eligible"]
    e["previous_held_raw"] = e["previous_value"].gt(0.0) & e["previous_eligible"]
    e["conviction"] = 0.0
    held = e["current_held"]
    e.loc[held, "conviction"] = e.loc[held].groupby("filer_id")["current_weight"].rank(pct=True)

    prev_cols = [
        "filer_id", "instrument_id", "state_value", "fragility_owner_value", "held_state", "churn_value",
        "ccp", "consensus", "persistence_count",
    ]
    prev_state = previous_state[prev_cols].rename(
        columns={c: f"previous_{c}" for c in prev_cols if c not in {"filer_id", "instrument_id"}}
    )
    e = e.merge(prev_state, on=["filer_id", "instrument_id"], how="left", validate="one_to_one")
    e["previous_held_state"] = e["previous_held_state"].fillna(e["previous_held_raw"].astype(float))
    e["previous_state_value"] = e["previous_state_value"].fillna(
        e["previous_value"].where(e["previous_eligible"], 0.0)
    )
    e["previous_fragility_owner_value"] = e["previous_fragility_owner_value"].fillna(
        e["previous_state_value"]
    )
    e["previous_churn_value"] = e["previous_churn_value"].fillna(
        e["previous_state_value"] * 0.5
    )
    e["previous_ccp"] = e["previous_ccp"].fillna(0.0)
    e["previous_consensus"] = e["previous_consensus"].fillna(0.0)
    prev_count = e["previous_persistence_count"].fillna(0).astype(int)
    e["persistence_count"] = np.where(
        e["current_held"], np.where(e["previous_held_state"].gt(0), prev_count + 1, 1), 0
    )
    e["persistence"] = e["persistence_count"].clip(upper=cfg.persistence_cap_quarters) / cfg.persistence_cap_quarters
    e["ccp"] = e["conviction"] * e["quality"] * e["persistence"]
    e["consensus"] = (e["conviction"] >= 0.90).astype(float) * e["quality"]
    e["state_value"] = e["current_value"].where(e["current_held"], 0.0)
    e["fragility_owner_value"] = e["current_value"].where(
        e["current_held"] & e["quality_eligible"], 0.0
    )
    e["held_state"] = e["current_held"].astype(float)
    e["churn_value"] = e["state_value"] * e["churn_smoothed"].fillna(0.0)

    e["sticky_raw"] = e["trade"]
    e["sticky_quality"] = e["trade"] * e["quality"]
    e["sticky_specificity"] = e["sticky_quality"] * (0.5 + 0.5 * e["specialized_score"].fillna(0.0))
    down = (-e["ticker"].map(residual_quarter)).clip(lower=0.0).fillna(0.0)
    e["double_down_all"] = e["quality"] * e["trade"].clip(lower=0.0) * down
    e["double_down_specific"] = e["double_down_all"].where(e["is_specific"])
    e["new_holder_breadth"] = (
        e["current_held"] & ~e["previous_held_state"].gt(0)
    ).astype(float)

    for col in ["state_value", "fragility_owner_value", "held_state", "churn_value", "ccp", "consensus"]:
        e[f"delta_{col}"] = e[col] - e[f"previous_{col}"]

    next_state_cols = [
        "filer_id", "instrument_id", "ticker", "state_value", "held_state",
        "fragility_owner_value", "churn_value", "ccp", "consensus", "conviction", "quality",
        "churn_smoothed", "persistence_count", "persistence",
    ]
    next_state = e[e["current_held"]][next_state_cols].copy()
    coverage = {
        "previous_value_usd": total_prev_value,
        "return_mapped_value_usd": mapped_value,
        "return_mapping_coverage": mapped_value / total_prev_value if total_prev_value else np.nan,
        "return_mapping_coverage_selected": (
            float(x.loc[x["filer_id"].isin(history_eligible[history_eligible].index) & x["return_mapped"], "previous_value"].sum())
            / float(x.loc[x["filer_id"].isin(history_eligible[history_eligible].index), "previous_value"].sum())
            if float(x.loc[x["filer_id"].isin(history_eligible[history_eligible].index), "previous_value"].sum()) > 0
            else np.nan
        ),
        "n_current_managers": float(len(cur_stats)),
        "n_eligible_managers": float(cur_stats["eligible"].sum()),
        "n_quality_eligible_managers": float(history_eligible.sum()),
    }
    return e, next_state, metrics, coverage


def build_event_panel(
    period: pd.Timestamp,
    updates: pd.DataFrame,
    previous_state: pd.DataFrame,
    previous_abnormal: pd.Series,
    market,
    master: pd.DataFrame,
    cfg: ResearchConfig,
) -> tuple[pd.DataFrame, pd.Series]:
    """Recompute ETF scores whenever a manager's selected filing becomes public."""

    tickers = pd.Index(master["ticker"].drop_duplicates())
    state_cols = {
        "state_value": "state_value",
        "fragility_owner_value": "fragility_owner_value",
        "held_state": "n_holders",
        "churn_value": "churn_value",
        "ccp": "ccp_state",
        "consensus": "consensus_state",
    }
    initial = previous_state.groupby("ticker")[[*state_cols]].sum().rename(columns=state_cols)
    initial = initial.reindex(tickers, fill_value=0.0)
    flow_cols = [
        "sticky_raw", "sticky_quality", "sticky_specificity", "double_down_all",
        "double_down_specific", "new_holder_breadth",
    ]
    state_delta_cols = [f"delta_{c}" for c in state_cols]
    daily = updates.groupby(["available_date", "ticker"])[flow_cols + state_delta_cols].sum()
    release_counts = (
        updates.loc[updates["quality_eligible"], ["available_date", "filer_id"]]
        .drop_duplicates()
        .groupby("available_date")
        .size()
    )
    state = initial.copy()
    flow = pd.DataFrame(0.0, index=tickers, columns=flow_cols)
    released = 0
    rows: list[pd.DataFrame] = []
    last_abnormal = previous_abnormal.reindex(tickers)
    for available_date in sorted(updates["available_date"].dropna().unique()):
        available_date = pd.Timestamp(available_date)
        released += int(release_counts.get(available_date, 0))
        if available_date not in daily.index.get_level_values(0):
            continue
        inc = daily.xs(available_date, level=0).reindex(tickers).fillna(0.0)
        flow = flow.add(inc[flow_cols], fill_value=0.0)
        for raw, renamed in state_cols.items():
            state[renamed] = state[renamed].add(inc[f"delta_{raw}"], fill_value=0.0)
        state["n_holders"] = state["n_holders"].clip(lower=0.0)
        state["state_value"] = state["state_value"].clip(lower=0.0)
        nonzero = flow["sticky_raw"].abs().gt(1e-12).sum()
        if released < cfg.min_released_managers or nonzero < cfg.min_cross_section:
            continue
        public = market.public_features(available_date)
        shock, stress = market.shock_state(available_date)
        scored = score_event_state(
            state,
            flow,
            public,
            shock,
            stress,
            previous_abnormal,
            master,
        )
        signal_cols = [*PRIMARY_SIGNALS, *ABLATION_SIGNALS]
        event = scored[signal_cols].stack(future_stack=True).dropna().rename("signal").reset_index()
        event.columns = ["ticker", "signal_name", "signal"]
        zero_based = event["signal_name"].isin(ZERO_BASED_SIGNALS)
        event = event[~zero_based | event["signal"].abs().gt(1e-15)].copy()
        # Markers preserve rebalance dates even when a zero-based signal has
        # no non-zero observation.  They are never a tradable ticker.
        markers = pd.DataFrame({
            "ticker": "__EVENT__",
            "signal_name": list(ZERO_BASED_SIGNALS),
            "signal": 0.0,
        })
        event = pd.concat([event, markers], ignore_index=True)
        event["period_end"] = pd.Timestamp(period)
        event["available_date"] = available_date
        event["released_managers"] = released
        event["market_stress"] = stress
        rows.append(event)
        slow_state = scored["fragility"].dropna().rename("signal").reset_index()
        slow_state.columns = ["ticker", "signal"]
        slow_state["signal_name"] = "_fragility_state"
        slow_state["period_end"] = pd.Timestamp(period)
        slow_state["available_date"] = available_date
        slow_state["released_managers"] = released
        slow_state["market_stress"] = stress
        rows.append(slow_state[event.columns])
        if scored["abnormal_level"].notna().sum() >= cfg.min_cross_section:
            last_abnormal = scored["abnormal_level"].copy()
    if not rows:
        return pd.DataFrame(
            columns=["ticker", "signal_name", "signal", "period_end", "available_date",
                     "released_managers", "market_stress"]
        ), last_abnormal
    return pd.concat(rows, ignore_index=True), last_abnormal


def expand_daily_fragility(events: pd.DataFrame, market, master: pd.DataFrame) -> pd.DataFrame:
    """Carry the slow 13F holder state and apply the memo's daily shock trigger."""

    slow = events[events["signal_name"].eq("_fragility_state")]
    keep = events[~events["signal_name"].isin(
        ["_fragility_state", "fragility_stress", "fragility_reversal", "fragility_unconditional"]
    )].copy()
    if slow.empty:
        return keep
    pivot = slow.pivot_table(
        index="available_date", columns="ticker", values="signal", aggfunc="last"
    ).sort_index()
    dates = market.prices.index[market.prices.index >= pd.Timestamp(pivot.index.min())]
    # A filing dated d is usable for the d shock only as an end-of-day signal;
    # the backtest trades on the next market date.
    state = pivot.reindex(pivot.index.union(dates)).sort_index().ffill().reindex(dates)
    daily_rows: list[pd.DataFrame] = []
    for date, fragility in state.iterrows():
        if fragility.notna().sum() < 10:
            continue
        shock, stress = market.shock_state(date)
        frag_z = cross_sectional_z(fragility)
        shock_z = cross_sectional_z(shock.reindex(fragility.index))
        scores = pd.DataFrame(index=fragility.index)
        scores["fragility_unconditional"] = frag_z
        scores["fragility_reversal"] = frag_z * (-shock_z).clip(lower=0.0)
        if stress:
            scores["fragility_stress"] = -frag_z
        long = scores.stack(future_stack=True).dropna().rename("signal").reset_index()
        long.columns = ["ticker", "signal_name", "signal"]
        long["period_end"] = pd.NaT
        long["available_date"] = pd.Timestamp(date)
        long["released_managers"] = np.nan
        long["market_stress"] = stress
        daily_rows.append(long)
    return pd.concat([keep, *daily_rows], ignore_index=True) if daily_rows else keep
