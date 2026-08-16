"""Boolean eligibility universe — the multifactor `Filters`, mini version.

Exposes the fields downstream code consumes, with the production names:
`universe` and `sell` as boolean DataFrames (dates x tickers) and the
`daily_volume_mean*` panels. Three filters instead of eleven, on purpose:

    price_filter      trades today and above a price floor;
    liquidity_filter  rolling median dollar volume clears a minimum;
    history_filter    enough non-missing days to compute indicators on.

`universe` is their AND with the production min_stocks guard (a day whose
cross-section would be degenerate keeps the previous day's universe).
`sell` relaxes the liquidity bar so a name just below the entry threshold
can still be held/exited — the production buy/sell asymmetry.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from market_data import MarketData, log


class Filters:
    def __init__(self, md: MarketData,
                 min_price: float = 4.0,
                 min_dollar_volume: float = 5e6,
                 liquidity_window: int = 63,
                 min_history_days: int = 252,
                 min_stocks: int = 50,
                 sell_relax: float = 0.5):
        log("building universe filters")
        self.dates = md.prices.index
        self.stocks = pd.DataFrame({"ticker": md.prices.columns})

        self.daily_volume = md.dollar_volume
        self.daily_volume_mean_1m = self.daily_volume.rolling(21, min_periods=21).mean().fillna(0)
        self.daily_volume_mean_3m = self.daily_volume.rolling(63, min_periods=63).mean().fillna(0)
        self.daily_volume_mean_6m = self.daily_volume.rolling(126, min_periods=126).mean().fillna(0)
        self.daily_volume_mean_1y = self.daily_volume.rolling(252, min_periods=252).mean().fillna(0)
        # production convention: a name is only as liquid as its worst window
        self.daily_volume_mean = pd.DataFrame(
            np.fmin(np.fmin(self.daily_volume_mean_1m.values, self.daily_volume_mean_3m.values),
                    np.fmin(self.daily_volume_mean_6m.values, self.daily_volume_mean_1y.values)),
            index=self.dates, columns=md.prices.columns).fillna(0)

        self.price_filter = md.prices_raw.notna() & (md.prices_raw >= min_price)
        med_dv = self.daily_volume.rolling(liquidity_window, min_periods=liquidity_window).median()
        self.liquidity_filter = (med_dv >= min_dollar_volume).fillna(False)
        self.history_filter = md.prices.notna().rolling(min_history_days, min_periods=1).sum() \
            .ge(int(min_history_days * 0.9))

        self.universe = self._combine(
            [self.price_filter, self.liquidity_filter, self.history_filter], min_stocks)
        sell_liq = (med_dv >= min_dollar_volume * sell_relax).fillna(False)
        self.sell = self._combine(
            [self.price_filter, sell_liq, self.history_filter], min_stocks)

        counts = self.universe.sum(axis=1)
        log(f"universe: mean {int(counts.mean())} stocks/day, "
            f"min {int(counts.min())}, max {int(counts.max())}")

    @staticmethod
    def _combine(filters: list[pd.DataFrame], min_stocks: int) -> pd.DataFrame:
        combined = filters[0].copy()
        for f in filters[1:]:
            combined &= f.reindex_like(combined).fillna(False)
        counts = combined.sum(axis=1)
        bad = counts < min_stocks
        if bad.any():
            vals = combined.values.copy()
            for i in np.flatnonzero(bad.values):
                if i > 0:
                    vals[i] = vals[i - 1]
            combined = pd.DataFrame(vals, index=combined.index, columns=combined.columns)
        return combined
