"""Adapter from quarterly factor-flow events to the multifactor backtester."""
from __future__ import annotations

import numpy as np
import pandas as pd


def event_scores_to_portfolio(
    name: str,
    event_scores: dict[pd.Timestamp, pd.Series],
    market_data,
    universe: pd.DataFrame,
    portfolio_cls,
    indicator_cls,
    pct: float = 0.20,
    min_stocks: int = 50,
):
    """Create a quarterly HML portfolio and let production mechanics drift it.

    Events are stamped on the first trading date strictly after the 13F
    knowledge cut.  ``Portfolio.period_return`` then lags weights once more,
    so a filing known after the close can never earn that same day's return.
    """
    dates, tickers = market_data.prices.index, market_data.prices.columns
    values = pd.DataFrame(np.nan, index=dates, columns=tickers, dtype=float)
    event_indices: list[int] = []
    for date, score in sorted(event_scores.items()):
        i = dates.searchsorted(pd.Timestamp(date), side="right")
        if i >= len(dates):
            continue
        common = score.index.intersection(tickers)
        values.loc[dates[i], common] = score.reindex(common)
        event_indices.append(i)
    if not event_indices:
        raise ValueError(f"No tradable events for {name}")
    values = values.ffill()
    indicator = IndicatorAdapter(indicator_cls, name, values, universe)
    portfolio = portfolio_cls.from_indicator(
        name,
        indicator.scores,
        universe,
        side="HML",
        pct=pct,
        min_stocks=min_stocks,
    )
    portfolio.rebalance(np.asarray(sorted(set(event_indices)), dtype=int), market_data.prices)
    return portfolio


class IndicatorAdapter:
    """Keep the core Indicator chain explicit and easy to test."""

    def __init__(self, indicator_cls, name: str, values: pd.DataFrame, universe: pd.DataFrame):
        obj = indicator_cls(name, values=values)
        obj.filter_values(universe).generate_z_scores().clip_scores(-3.0, 3.0)
        self.scores = obj.scores


def run_cost_ladder(
    portfolios: list,
    market_data,
    backtest_cls,
    fee_bps: tuple[int, ...],
    start: pd.Timestamp | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Backtest via the shared engine; no parallel toy P&L implementation."""
    engine = backtest_cls(portfolios)
    summaries = []
    returns = []
    for bps in fee_bps:
        fee = bps / 10_000.0
        stat = engine.performance_analysis(
            market_data,
            trading_fee=fee,
            cash_leg=market_data.treasury_yield,
            start=start,
        ).reset_index(names="strategy")
        stat["fee_bps"] = bps
        summaries.append(stat)
        r = engine.get_returns(
            market_data, trading_fee=fee, cash_leg=market_data.treasury_yield
        )
        if start is not None:
            r = r.loc[r.index >= pd.Timestamp(start)]
        r = r.stack().rename("return").reset_index()
        r.columns = ["date", "strategy", "return"]
        r["fee_bps"] = bps
        returns.append(r)
    return pd.concat(summaries, ignore_index=True), pd.concat(returns, ignore_index=True)
