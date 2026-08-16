"""Backtest: run a list of portfolios and report the production stats."""
from __future__ import annotations

import numpy as np
import pandas as pd

from portfolio import Portfolio


class Backtest:
    def __init__(self, portfolios: list[Portfolio] | Portfolio):
        if isinstance(portfolios, Portfolio):
            portfolios = [portfolios]
        self.portfolios = list(portfolios)

    def names(self) -> list[str]:
        return [p.name for p in self.portfolios]

    def get_returns(self, market_data, trading_fee: float | None = None,
                    cash_leg: pd.Series | None = None) -> pd.DataFrame:
        return pd.DataFrame({
            p.name: p.period_return_sum(market_data, trading_fee, cash_leg)
            for p in self.portfolios
        })

    def performance_analysis(self, market_data, trading_fee: float | None = None,
                             cash_leg: pd.Series | None = None,
                             benchmark: pd.Series | None = None,
                             start=None, end=None) -> pd.DataFrame:
        """One row per portfolio: total/annualized return, vol, Sharpe, max
        drawdown, hit ratio, annualized turnover. Optionally a benchmark row
        for reference (gross of everything, as an index is)."""
        rets = self.get_returns(market_data, trading_fee, cash_leg)
        if start is not None:
            rets = rets[rets.index >= pd.Timestamp(start)]
        if end is not None:
            rets = rets[rets.index <= pd.Timestamp(end)]

        rows = {}
        for name, r in rets.items():
            rows[name] = self._stats(r)
            p = next(x for x in self.portfolios if x.name == name)
            if p.trades_matrix is not None:
                tm = p.trades_matrix
                if start is not None:
                    tm = tm[tm.index >= pd.Timestamp(start)]
                years = max(len(r) / 252, 1e-9)
                rows[name]["ann_turnover"] = float(tm.abs().sum().sum() / 2 / years)
        out = pd.DataFrame(rows).T

        if benchmark is not None:
            b = benchmark.reindex(rets.index).fillna(0)
            out.loc[f"benchmark ({benchmark.name})"] = self._stats(b)
        return out

    @staticmethod
    def _stats(r: pd.Series) -> dict:
        cum = (1 + r).cumprod()
        total = float(cum.iloc[-1] - 1)
        ann = (1 + total) ** (252 / len(r)) - 1
        vol = float(r.std() * np.sqrt(252))
        return {
            "total_return": total,
            "ann_return": float(ann),
            "ann_vol": vol,
            "sharpe": float(ann / vol) if vol > 0 else np.nan,
            "max_drawdown": float((cum / cum.cummax() - 1).min()),
            "hit_ratio": float((r > 0).sum() / max((r != 0).sum(), 1)),
        }
