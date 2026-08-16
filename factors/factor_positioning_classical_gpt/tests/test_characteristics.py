from __future__ import annotations

import numpy as np
import pandas as pd

from classical_positioning.characteristics import build_characteristics
from classical_positioning.config import ResearchConfig


class FakeMarket:
    pass


def _market(seed=7):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2022-01-03", periods=340)
    tickers = [f"T{i:03d}" for i in range(100)]
    common = rng.normal(0.0003, 0.008, len(dates))
    load = np.linspace(0.5, 1.5, len(tickers))
    ret = common[:, None] * load + rng.normal(0.0001, 0.006, (len(dates), len(tickers)))
    prices = pd.DataFrame(50 * np.exp(np.cumsum(ret, axis=0)), index=dates, columns=tickers)
    m = FakeMarket()
    m.prices = prices
    m.prices_raw = prices.copy()
    m.returns = prices.pct_change(fill_method=None).fillna(0)
    m.benchmark_returns = pd.Series(common, index=dates)
    m.dollar_volume = pd.DataFrame(20e6, index=dates, columns=tickers)
    cap = pd.DataFrame(
        np.tile(np.geomspace(1e8, 1e12, len(tickers)), (len(dates), 1)),
        index=dates,
        columns=tickers,
    )
    return m, cap


def test_characteristics_do_not_read_prices_after_cut():
    """Changing the future must leave every score at the cut bit-identical."""
    market, cap = _market()
    cut = market.prices.index[300]
    first = build_characteristics(cut, market, cap, ResearchConfig())
    market.prices.loc[market.prices.index > cut] *= 1000.0
    market.prices_raw.loc[market.prices_raw.index > cut] *= 1000.0
    market.returns = market.prices.pct_change(fill_method=None).fillna(0)
    second = build_characteristics(cut, market, cap, ResearchConfig())
    pd.testing.assert_frame_equal(first.scores, second.scores)


def test_size_sign_is_positive_for_small_stocks():
    market, cap = _market()
    snap = build_characteristics(market.prices.index[300], market, cap, ResearchConfig())
    small, large = cap.columns[0], cap.columns[-1]
    assert snap.scores.loc[small, "size"] > 0
    assert snap.scores.loc[large, "size"] < 0


def test_impossible_market_cap_is_rejected_not_benchmark_dominant():
    market, cap = _market()
    cut = market.prices.index[300]
    cap.loc[cut, "T050"] = 1e20
    snap = build_characteristics(cut, market, cap, ResearchConfig())
    assert "T050" not in snap.scores.index
    assert snap.quality["n_cap_rejected"] >= 1
    assert np.isclose(snap.benchmark_weights.sum(), 1.0)
