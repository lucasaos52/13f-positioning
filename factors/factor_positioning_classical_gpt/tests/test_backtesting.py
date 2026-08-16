from __future__ import annotations

import numpy as np
import pandas as pd

from classical_positioning.backtesting import event_scores_to_portfolio
from indicator import Indicator
from portfolio import Portfolio


class FakeMarket:
    pass


def test_event_activates_strictly_after_public_cut():
    dates = pd.bdate_range("2024-01-01", periods=10)
    cols = list("ABCDE")
    md = FakeMarket()
    md.prices = pd.DataFrame(100.0, index=dates, columns=cols)
    universe = pd.DataFrame(True, index=dates, columns=cols)
    cut = dates[2]
    score = pd.Series(range(5), index=cols, dtype=float)
    p = event_scores_to_portfolio(
        "x", {cut: score}, md, universe, Portfolio, Indicator, pct=0.4, min_stocks=2
    )
    assert p.rb_dates.tolist() == [3]
    assert np.allclose(p.weights.iloc[:3], 0.0)
    assert p.weights.iloc[3].abs().sum() > 0
