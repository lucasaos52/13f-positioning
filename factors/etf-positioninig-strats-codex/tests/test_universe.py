import numpy as np
import pandas as pd

from etf_positioning.config import ResearchConfig
from etf_positioning.universe import (
    build_manager_features,
    classify_etfs,
    manager_quality_weights,
    manager_style_flags,
)


def test_classification_separates_equity_bond_and_commodity_funds():
    x = pd.DataFrame(
        {
            "instrument_id": ["SPY", "AGG", "GLD", "AAPL"],
            "issuer": ["SPDR S&P 500 ETF TR", "ISHARES TR", "SPDR GOLD TR", "APPLE INC"],
            "title_of_class": ["TR UNIT", "CORE US AGG BD ETF", "GOLD SHS", "COM"],
            "instrument_class": ["fund", "fund", "fund", "common"],
        }
    )
    out = classify_etfs(x).set_index("instrument_id")
    assert out.loc["SPY", "etf_asset_class"] == "equity"
    assert out.loc["SPY", "etf_style"] == "broad"
    assert out.loc["AGG", "etf_asset_class"] == "fixed_income"
    assert out.loc["GLD", "etf_asset_class"] == "commodity"
    assert not out.loc["AAPL", "etf_candidate"]


def test_manager_features_use_all_managers_and_flag_style_not_passivity():
    dates = [pd.Timestamp("2023-03-31"), pd.Timestamp("2023-06-30")]
    rows = []
    for d in dates:
        rows += [
            ("direct", d, "AAPL", 900.0), ("direct", d, "SPY", 100.0),
            ("allocator", d, "AAPL", 100.0), ("allocator", d, "SPY", 900.0),
        ]
    h = pd.DataFrame(rows, columns=["filer_id", "period_end", "instrument_id", "value_usd"])
    master = classify_etfs(pd.DataFrame({
        "instrument_id": ["AAPL", "SPY"],
        "issuer": ["APPLE INC", "SPDR S&P 500 ETF TR"],
        "title_of_class": ["COM", "TR UNIT"],
        "instrument_class": ["common", "fund"],
    }))
    cfg = ResearchConfig(min_manager_book_usd=0, min_manager_positions=1)
    out = manager_style_flags(build_manager_features(h, master, cfg), cfg)
    style = out.set_index(["filer_id", "period_end"])["manager_style"]
    assert style.loc[("direct", dates[0])] == "mixed"
    assert style.loc[("allocator", dates[0])] == "etf_allocator"
    assert out["passive_manager"].isna().all()


def test_transient_flag_never_uses_future_turnover():
    q = pd.date_range("2020-03-31", periods=6, freq="QE")
    x = pd.DataFrame({
        "filer_id": "m",
        "period_end": q,
        "etf_intensity": 0.1,
        "turnover": [0.1, 0.2, 0.3, 0.4, 99.0, 0.1],
    })
    out = manager_style_flags(x)
    assert pd.isna(out.loc[0, "turnover_history_pct"])
    assert pd.isna(out.loc[3, "turnover_history_pct"])
    assert out.loc[4, "transient"]
    # The future 99 observation must not make the last 0.1 look transient.
    assert not out.loc[5, "transient"]


def test_quality_weight_uses_lagged_intensity_only():
    periods = pd.date_range("2022-03-31", periods=3, freq="QE")
    features = pd.DataFrame({
        "filer_id": "m", "period_end": periods,
        "etf_intensity": [0.1, 0.8, 0.2], "eligible_base": True,
    })
    out = manager_quality_weights(features)
    assert out.loc[1, "weight_direct_tilt"] == 0.9
    assert np.isclose(out.loc[2, "weight_direct_tilt"], 0.2)
