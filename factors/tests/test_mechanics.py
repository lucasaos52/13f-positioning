"""Backtest mechanics pinned on a hand-checkable synthetic panel.

Every expected number here can be recomputed with a pocket calculator; that
is the point. If a refactor changes any of these, it changed the economics,
not the style. Run: python -m pytest tests -q (needs only pandas/numpy).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backtest import Backtest  # noqa: E402
from grouping import correlation_groups, sharpe_weighted_combine, group_and_combine  # noqa: E402
from portfolio import Portfolio  # noqa: E402


def _dates(n):
    return pd.bdate_range("2024-01-01", periods=n)


class FakeMarketData:
    """Just the attributes period_return consumes."""
    def __init__(self, returns, daily_borrow_rate=None, prices=None):
        self.returns = returns
        self.daily_borrow_rate = daily_borrow_rate
        self.prices = prices


# ── normalize / equalize ───────────────────────────────────────────────── #
def test_normalize_long_keeps_short_ratio():
    d = _dates(2)
    w = pd.DataFrame({"A": [2.0, 2.0], "B": [-1.0, -1.0]}, index=d)
    p = Portfolio("x", w).normalize(type="long")
    assert p.weights.loc[d[0], "A"] == 1.0
    assert p.weights.loc[d[0], "B"] == -0.5  # short scaled by the SAME factor


def test_normalize_split_sets_both_sides_to_one():
    d = _dates(1)
    w = pd.DataFrame({"A": [2.0], "B": [3.0], "C": [-4.0]}, index=d)
    p = Portfolio("x", w).normalize(type="split")
    assert p.weights.iloc[0]["A"] == pytest.approx(0.4)
    assert p.weights.iloc[0]["C"] == pytest.approx(-1.0)


def test_equalize_scales_short_to_match_long():
    """Regression for the inverted-ratio bug found in the python port: the
    SHORT side must be scaled by long/|short|, so |short| == long."""
    d = _dates(1)
    w = pd.DataFrame({"A": [1.0], "B": [-0.25]}, index=d)
    p = Portfolio("x", w).equalize()
    assert p.weights.iloc[0]["B"] == pytest.approx(-1.0)
    assert p.get_exposure()["net"].iloc[0] == pytest.approx(0.0)


# ── rebalance drift ────────────────────────────────────────────────────── #
def test_rebalance_drifts_with_price_between_snaps():
    """One long name, price +10% the day after rebalance: its weight rises
    to 1.1/(1.1+cash 0) — with full investment the long-base normalization
    keeps weight 1.0; with half investment weight drifts to .55/1.05."""
    d = _dates(4)
    px = pd.DataFrame({"A": [100, 110, 110, 110], "B": [100.0] * 4}, index=d)
    w = pd.DataFrame({"A": [0.5, 0.5, 0.5, 0.5], "B": [0.0] * 4}, index=d)
    p = Portfolio("x", w)
    p.rebalance(np.array([0, 3]), px)
    # day1: A worth .5*1.1=.55, cash .5 -> base 1.05 -> weight .55/1.05
    assert p.weights.loc[d[1], "A"] == pytest.approx(0.55 / 1.05)
    # snap back at the next rebalance
    assert p.weights.loc[d[3], "A"] == pytest.approx(0.5)
    # trades on d3 = target - drifted
    assert p.trades_matrix.loc[d[3], "A"] == pytest.approx(0.5 - 0.55 / 1.05)
    assert p.trades_matrix.loc[d[1], "A"] == 0.0


# ── PnL accrual: timing, fee, borrow, cash leg ─────────────────────────── #
def test_pnl_uses_lagged_weights():
    d = _dates(3)
    rets = pd.DataFrame({"A": [0.0, 0.10, 0.0]}, index=d)
    w = pd.DataFrame({"A": [1.0, 1.0, 1.0]}, index=d)
    p = Portfolio("x", w)
    pnl = p.period_return(FakeMarketData(rets))
    assert pnl.loc[d[1], "A"] == pytest.approx(0.10)  # decided d0, earned d1
    assert pnl.loc[d[0], "A"] == 0.0                  # nothing earned day one


def test_trading_fee_charged_on_trades_next_day():
    d = _dates(3)
    rets = pd.DataFrame({"A": [0.0, 0.0, 0.0]}, index=d)
    px = pd.DataFrame({"A": [100.0, 100, 100]}, index=d)
    w = pd.DataFrame({"A": [1.0, 1.0, 1.0]}, index=d)
    p = Portfolio("x", w)
    p.rebalance(np.array([0, 1, 2]), px)  # trade of 1.0 happens on day 0
    pnl = p.period_return(FakeMarketData(rets), trading_fee=0.001)
    assert pnl.loc[d[1], "A"] == pytest.approx(-0.001 * 1.0)  # fee lagged like pnl


def test_borrow_accrues_daily_on_shorts_only():
    d = _dates(2)
    rets = pd.DataFrame({"A": [0.0, 0.0], "B": [0.0, 0.0]}, index=d)
    borrow = pd.DataFrame(0.0001, index=d, columns=["A", "B"])
    w = pd.DataFrame({"A": [1.0, 1.0], "B": [-1.0, -1.0]}, index=d)
    pnl = Portfolio("x", w).period_return(FakeMarketData(rets, borrow))
    assert pnl.loc[d[1], "B"] == pytest.approx(-0.0001)  # short pays
    assert pnl.loc[d[1], "A"] == 0.0                     # long does not


def test_cash_leg_scales_with_net_exposure():
    d = _dates(2)
    rets = pd.DataFrame({"A": [0.0, 0.0]}, index=d)
    tsy = pd.Series(0.0002, index=d)
    lo = Portfolio("lo", pd.DataFrame({"A": [1.0, 1.0]}, index=d))
    total = lo.period_return_sum(FakeMarketData(rets), cash_leg=tsy)
    assert total.loc[d[1]] == pytest.approx(-0.0002)  # LO pays full cash cost
    ls = Portfolio("ls", pd.DataFrame({"A": [1.0, 1.0]}, index=d))
    ls.weights["B"] = -1.0
    rets["B"] = 0.0
    total_ls = ls.period_return_sum(FakeMarketData(rets), cash_leg=tsy)
    assert total_ls.loc[d[1]] == pytest.approx(0.0)   # net 0 -> no cash leg


def test_vol_weighting_median_stock_keeps_weight():
    """Production semantics: 1/vol over the row median, clipped [0.1, 5].
    The median-vol stock keeps its weight; a stock at half the median vol
    doubles; extremes are clipped."""
    d = _dates(1)
    w = pd.DataFrame({"A": [1.0], "B": [1.0], "C": [1.0]}, index=d)
    vol = pd.DataFrame({"A": [0.10], "B": [0.20], "C": [0.40]}, index=d)  # median 0.20
    p = Portfolio("x", w).adjust_by_volatility(vol)
    assert p.weights.iloc[0]["B"] == pytest.approx(1.0)   # median stock unchanged
    assert p.weights.iloc[0]["A"] == pytest.approx(2.0)   # half the vol -> double
    assert p.weights.iloc[0]["C"] == pytest.approx(0.5)
    # clipping
    vol2 = pd.DataFrame({"A": [0.001], "B": [0.20], "C": [10.0]}, index=d)
    p2 = Portfolio("x", w).adjust_by_volatility(vol2)
    assert p2.weights.iloc[0]["A"] == pytest.approx(5.0)  # capped
    assert p2.weights.iloc[0]["C"] == pytest.approx(0.1)  # floored


# ── from_indicator: sides and quantiles ────────────────────────────────── #
def _scores_universe():
    d = _dates(2)
    scores = pd.DataFrame([[1.0, 2, 3, 4, 5]] * 2, index=d, columns=list("ABCDE"))
    univ = pd.DataFrame(True, index=d, columns=list("ABCDE"))
    return scores, univ


def test_hml_longs_top_shorts_bottom():
    scores, univ = _scores_universe()
    p = Portfolio.from_indicator("f", scores, univ, side="HML", pct=0.2, min_stocks=2)
    assert p.weights.iloc[0]["E"] > 0 and p.weights.iloc[0]["A"] < 0
    assert p.weights.iloc[0]["C"] == 0
    exp = p.get_exposure()
    assert exp["long"].iloc[0] == pytest.approx(1.0)
    assert exp["short"].iloc[0] == pytest.approx(1.0)


def test_lo_has_no_shorts_and_long_one():
    scores, univ = _scores_universe()
    p = Portfolio.from_indicator("f", scores, univ, side="LO", pct=0.4, min_stocks=2)
    assert (p.weights.values >= 0).all()
    assert p.get_exposure()["long"].iloc[0] == pytest.approx(1.0)


def test_universe_excludes_from_selection():
    scores, univ = _scores_universe()
    univ["E"] = False  # best score not eligible
    p = Portfolio.from_indicator("f", scores, univ, side="HML", pct=0.25, min_stocks=2)
    assert (p.weights["E"] == 0).all()


# ── grouping ───────────────────────────────────────────────────────────── #
def _three_return_series():
    rng = np.random.default_rng(7)
    d = _dates(252)
    a = rng.normal(0.001, 0.01, 252)
    b = a + rng.normal(0, 0.001, 252)          # near-clone of a
    c = rng.normal(0.0005, 0.01, 252)          # independent
    return pd.DataFrame({"a": a, "b": b, "c": c}, index=d)


def test_correlation_groups_join_the_clones():
    rets = _three_return_series()
    groups = correlation_groups(rets, n_groups=2)
    joined = next(g for g in groups if len(g) == 2)
    assert set(joined) == {"a", "b"}


def test_sharpe_weights_favor_the_higher_sharpe():
    d = _dates(252)
    rng = np.random.default_rng(1)
    good = pd.Series(rng.normal(0.002, 0.01, 252), index=d)
    bad = pd.Series(rng.normal(-0.001, 0.01, 252), index=d)
    rets = pd.DataFrame({"g": good, "b": bad})
    w = pd.DataFrame({"A": [1.0] * 252, "B": [-1.0] * 252}, index=d)
    pg, pb = Portfolio("g", w), Portfolio("b", w * 0.5)
    combined = sharpe_weighted_combine("grp", [pg, pb], rets)
    # bad has negative sharpe -> weight 0 -> combined == normalized pg
    pd.testing.assert_frame_equal(combined.weights, pg.clone().normalize("split").weights)


def test_intersection_drops_disputed_names():
    d = _dates(5)
    rng = np.random.default_rng(3)
    rets = pd.DataFrame(rng.normal(0.001, 0.01, (5, 2)), index=d, columns=["p1", "p2"])
    w1 = pd.DataFrame({"A": [1.0] * 5, "B": [1.0] * 5, "C": [-1.0] * 5}, index=d)
    w2 = pd.DataFrame({"A": [1.0] * 5, "B": [0.0] * 5, "C": [-1.0] * 5}, index=d)
    p1, p2 = Portfolio("p1", w1), Portfolio("p2", w2)
    combined = sharpe_weighted_combine("grp", [p1, p2], rets, intersection=1.0)
    assert (combined.weights["B"] == 0).all()   # only p1 held B -> dropped
    assert (combined.weights["A"] > 0).all()    # both agreed -> kept
    assert (combined.weights["C"] < 0).all()


def test_group_and_combine_end_to_end():
    d = _dates(260)
    rng = np.random.default_rng(11)
    px = pd.DataFrame(
        100 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, (260, 6)), axis=0)),
        index=d, columns=list("ABCDEF"))
    rets = px.pct_change(fill_method=None).fillna(0)
    md = FakeMarketData(rets, prices=px)
    rb = np.arange(0, 260, 21)

    portfs = []
    for i, name in enumerate(["f1", "f2", "f3"]):
        w = pd.DataFrame(0.0, index=d, columns=px.columns)
        w.iloc[:, i] = 1.0
        w.iloc[:, 5 - i] = -1.0
        p = Portfolio(name, w)
        p.rebalance(rb, px)
        portfs.append(p)

    res = group_and_combine(portfs, md, n_groups=2, rb_idxs=rb)
    assert len(res["portfolios"]) == 2
    assert res["combined"].trades_matrix is not None
    total = res["combined"].period_return_sum(md)
    assert np.isfinite(total.values).all()


def test_backtest_stats_shape():
    d = _dates(260)
    rets = pd.DataFrame({"A": np.full(260, 0.001)}, index=d)
    p = Portfolio("x", pd.DataFrame({"A": [1.0] * 260}, index=d))
    stats = Backtest([p]).performance_analysis(FakeMarketData(rets))
    assert stats.loc["x", "ann_return"] > 0.2  # ~0.1% daily compounds to >25%
    assert {"sharpe", "max_drawdown", "hit_ratio"} <= set(stats.columns)
