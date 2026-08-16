import numpy as np
import pandas as pd

from etf_positioning.evaluation import event_study


def test_event_study_enters_strictly_after_availability():
    dates = pd.bdate_range("2023-05-01", periods=8)
    tickers = [f"T{i}" for i in range(10)]
    prices = pd.DataFrame(100.0, index=dates, columns=tickers)
    prices.loc[dates[6]] = 100.0 + np.arange(10)
    signal = pd.DataFrame({
        "period_end": pd.Timestamp("2023-03-31"),
        "available_date": dates[0], "ticker": tickers, "signal": np.arange(10),
    })
    events, _ = event_study(signal, prices, horizons=(5,), one_way_cost_bps=0)
    assert events.loc[0, "entry_date"] == dates[1]
    assert events.loc[0, "ic"] > 0.99
    assert events.loc[0, "spread_gross"] > 0

