from __future__ import annotations

import pandas as pd

from etf_strategies.config import ResearchConfig
from etf_strategies.panel import build_manager_updates, initialize_manager_etf_state


def _snapshot(etf_value, stock_value, date):
    return pd.DataFrame(
        {
            "filer_id": ["F", "F"], "instrument_id": ["ETF1", "STK"],
            "value_usd": [etf_value, stock_value], "shares": [1.0, 1.0],
            "cusip6": ["ETF1", "STK"], "instrument_class": ["fund", "common"],
            "available_date": pd.to_datetime([date, date]),
        }
    )


def test_no_trade_when_current_book_equals_drift(master):
    cfg = ResearchConfig(min_manager_book_usd=0, min_manager_positions=1)
    previous = _snapshot(40.0, 60.0, "2024-02-14")
    current = _snapshot(44.0, 66.0, "2024-05-10")
    prior_state, prior_stats = initialize_manager_etf_state(previous, master, cfg)
    updates, _, metrics, coverage = build_manager_updates(
        current=current,
        previous=previous,
        previous_state=prior_state,
        previous_stats=prior_stats,
        master=master,
        instrument_returns=pd.Series({"ETF1": 0.10, "STK": 0.10}),
        spy_return=0.10,
        churn_history={},
        residual_quarter=pd.Series({"AAA": -0.05, "BBB": 0.0}),
        cfg=cfg,
    )
    assert abs(updates.loc[updates["ticker"].eq("AAA"), "trade"].iloc[0]) < 1e-12
    assert abs(metrics.loc["F", "churn"]) < 1e-12
    assert coverage["return_mapping_coverage"] == 1.0


def test_double_down_requires_buy_and_negative_residual(master):
    cfg = ResearchConfig(min_manager_book_usd=0, min_manager_positions=1)
    previous = _snapshot(20.0, 80.0, "2024-02-14")
    current = _snapshot(40.0, 70.0, "2024-05-10")
    prior_state, prior_stats = initialize_manager_etf_state(previous, master, cfg)
    updates, *_ = build_manager_updates(
        current, previous, prior_state, prior_stats, master,
        pd.Series({"ETF1": 0.0, "STK": 0.0}), 0.0, {},
        pd.Series({"AAA": -0.10, "BBB": -0.10}), cfg,
    )
    row = updates.loc[updates["ticker"].eq("AAA")].iloc[0]
    assert row["trade"] > 0
    assert row["double_down_all"] > 0
    assert pd.isna(row["double_down_specific"])

