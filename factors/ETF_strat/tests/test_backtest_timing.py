from __future__ import annotations

import pandas as pd

from etf_strategies.backtesting import prepare_event_values


def test_stress_exits_on_the_day_after_one_day_signal():
    dates = pd.bdate_range("2024-01-02", periods=5)
    events = pd.DataFrame(
        {"available_date": [dates[0]], "ticker": ["AAA"], "signal": [2.0]}
    )
    values, idx = prepare_event_values("fragility_stress", events, dates, pd.Index(["AAA"]))
    assert values.loc[dates[1], "AAA"] == 2.0
    assert values.loc[dates[2], "AAA"] == 0.0
    assert idx == list(range(1, len(dates)))


def test_reversal_uses_overlapping_21_day_cohorts():
    dates = pd.bdate_range("2024-01-02", periods=5)
    events = pd.DataFrame(
        {
            "available_date": [dates[0], dates[1]],
            "ticker": ["AAA", "AAA"],
            "signal": [1.0, 3.0],
        }
    )
    values, idx = prepare_event_values("fragility_reversal", events, dates, pd.Index(["AAA"]))
    assert values.loc[dates[1], "AAA"] == 1.0
    assert values.loc[dates[2], "AAA"] == 2.0
    assert idx == [1, 2]


def test_sparse_zero_based_event_reconstructs_dense_cross_section():
    dates = pd.bdate_range("2024-01-02", periods=4)
    dense = pd.DataFrame({
        "available_date": [dates[0], dates[0], dates[0]],
        "ticker": ["AAA", "BBB", "CCC"],
        "signal": [2.0, 0.0, 0.0],
    })
    sparse = pd.DataFrame({
        "available_date": [dates[0], dates[0]],
        "ticker": ["AAA", "__EVENT__"],
        "signal": [2.0, 0.0],
    })
    columns = pd.Index(["AAA", "BBB", "CCC"])
    dense_values, dense_idx = prepare_event_values(
        "double_down_all", dense, dates, columns
    )
    sparse_values, sparse_idx = prepare_event_values(
        "double_down_all", sparse, dates, columns, zero_tickers=columns
    )
    pd.testing.assert_frame_equal(dense_values, sparse_values)
    assert dense_idx == sparse_idx
