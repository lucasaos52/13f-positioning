"""Portfolio: daily weights matrix + the production backtest mechanics.

A mini port of the multifactor Portfolio, keeping exactly the machinery a
factor simulation needs and nothing else:

    - `weights`: dates x tickers DataFrame. Long > 0, short < 0.
    - `normalize(type)`: long / short / gross / split exposure = 1;
    - `equalize()`: cash-neutral (|short| = long), the LS default;
    - `rebalance(idxs, prices)`: weights snap to target on rebalance days
      and DRIFT with prices in between — same arithmetic as production
      (long base normalization), producing `trades_matrix`;
    - `period_return(...)`: PnL accrual with the production timing
      convention `weights.shift(1) * returns` (decide today, earn
      tomorrow), minus trading fee on |trades|, plus borrow carry on
      shorts;
    - `period_return_sum(...)`: total daily PnL minus the cash leg
      (treasury_yield x net exposure) — for an equalized LS book the cash
      leg nets to ~zero, for a long-only book it is the full opportunity
      cost. Pass the benchmark's returns instead of the treasury to get
      benchmark-relative (excess) returns for LO, which is how production
      evaluates its long-only sleeve.

Deliberately NOT ported (out of scope by design): partialRebalance*,
volume caps, sector adjustments, risk parity. The point is a small core
whose every number can be checked by hand.
"""
from __future__ import annotations

import copy
from typing import Optional

import numpy as np
import pandas as pd


class Portfolio:
    def __init__(self, name: str = None, weights: Optional[pd.DataFrame] = None):
        self.name = name
        self.weights: Optional[pd.DataFrame] = weights.fillna(0) if weights is not None else None
        self.rb_dates: Optional[np.ndarray] = None
        self.trades_matrix: Optional[pd.DataFrame] = None

    # ── basics ─────────────────────────────────────────────────────────── #
    def clone(self) -> "Portfolio":
        p = Portfolio(self.name)
        p.weights = self.weights.copy() if self.weights is not None else None
        p.rb_dates = copy.copy(self.rb_dates)
        p.trades_matrix = self.trades_matrix.copy() if self.trades_matrix is not None else None
        return p

    def get_long(self, as_matrix: bool = False):
        lo = self.clone()
        lo.name = f"{lo.name}_LO"
        lo.weights = lo.weights.clip(lower=0)
        return lo.weights if as_matrix else lo

    def get_short(self, as_matrix: bool = False):
        so = self.clone()
        so.name = f"{so.name}_SO"
        so.weights = so.weights.clip(upper=0)
        return so.weights if as_matrix else so

    def get_exposure(self) -> dict:
        long_exp = self.weights.clip(lower=0).sum(axis=1)
        short_exp = -self.weights.clip(upper=0).sum(axis=1)
        return {"long": long_exp, "short": short_exp,
                "net": long_exp - short_exp, "gross": long_exp + short_exp}

    # ── normalization ──────────────────────────────────────────────────── #
    def normalize(self, type: str | None = None, notional: float = 1.0) -> "Portfolio":
        """Set exposure to `notional` each day.

        type='long'  divide the whole matrix by long exposure (production
                     default: long = 1, short keeps its ratio to long);
        type='short' / 'gross' analogous;
        type='split' long and short normalized independently to +/-notional.
        """
        long = self.weights.clip(lower=0)
        short = self.weights.clip(upper=0)
        long_sum = long.sum(axis=1).replace(0, np.nan)
        short_sum = short.sum(axis=1).abs().replace(0, np.nan)
        if type is None:
            type = "short" if (long.sum(axis=1) == 0).all() else "long"
        if type == "long":
            self.weights = (long + short).divide(long_sum, axis=0).mul(notional).fillna(0)
        elif type == "short":
            self.weights = (long + short).divide(short_sum, axis=0).mul(notional).fillna(0)
        elif type == "gross":
            gross = (long.sum(axis=1) + short.sum(axis=1).abs()).replace(0, np.nan)
            self.weights = (long + short).divide(gross, axis=0).mul(notional).fillna(0)
        elif type == "split":
            long = long.divide(long_sum, axis=0).mul(notional).fillna(0)
            short = short.divide(short_sum, axis=0).mul(notional).fillna(0)
            self.weights = long + short
        else:
            raise ValueError("type must be long/short/gross/split")
        return self

    def equalize(self) -> "Portfolio":
        """Cash-neutral: scale the short side so |short| == long, matching
        production `equalize` (R: portfS * expLong / -expShort)."""
        long = self.weights.clip(lower=0)
        short = self.weights.clip(upper=0)
        scale = (long.sum(axis=1) / short.sum(axis=1).abs()) \
            .replace([np.inf, -np.inf], 1).fillna(1)
        self.weights = long + short.multiply(scale, axis=0)
        return self

    def adjust_by_universe(self, universe: pd.DataFrame) -> "Portfolio":
        """Zero any position outside the boolean eligibility matrix."""
        univ = universe.reindex_like(self.weights).fillna(False)
        self.weights = self.weights.where(univ, 0.0)
        return self

    def adjust_by_volatility(self, volatility: pd.DataFrame,
                             universe: pd.DataFrame | None = None,
                             inverse: bool = True) -> "Portfolio":
        """Scale positions by (inverse) volatility — production semantics.

        Multifactor's adjustByVolatility: 1/vol, masked to the universe,
        divided by the row MEDIAN so the typical stock keeps weight 1, then
        clipped to [0.1, 5] so one sleepy utility cannot own the book. The
        caller re-normalizes/equalizes afterwards, exactly as in production
        (this method deliberately does not).
        """
        vol = volatility.reindex_like(self.weights)
        if universe is not None:
            vol = vol.where(universe.reindex_like(self.weights).fillna(False))
        scale = (1.0 / vol if inverse else vol).replace([np.inf, -np.inf], np.nan)
        w = scale.divide(scale.median(axis=1), axis=0).clip(0.1, 5.0).fillna(0.0)
        self.weights = (self.weights * w).fillna(0.0)
        return self

    # ── rebalancing ────────────────────────────────────────────────────── #
    def rebalance(self, idxs: np.ndarray, prices: pd.DataFrame) -> "Portfolio":
        """Snap to target on rebalance days, drift with prices in between.

        Production arithmetic: between rebalances each position's weight
        moves with its price relative to the whole book's drifted value
        (long-base normalization, so a self-financing book stays consistent),
        and `trades_matrix` records target-minus-drifted on rebalance days —
        which is what the trading fee is charged on.
        """
        idxs = np.asarray(idxs, dtype=int)
        self.rb_dates = idxs
        n, m = self.weights.shape
        idx, cols = self.weights.index, self.weights.columns

        px = prices.reindex(index=idx, columns=cols).ffill().fillna(1).values

        target = np.full((n, m), np.nan)
        target[idxs] = self.weights.values[idxs]
        rb_mask = np.zeros(n, dtype=bool)
        rb_mask[idxs] = True

        long_t = np.where(rb_mask[:, None], np.where(target >= 0, target, 0.0), np.nan)
        short_t = np.where(rb_mask[:, None], np.where(target <= 0, target, 0.0), np.nan)
        long_f = pd.DataFrame(long_t, index=idx, columns=cols).ffill().fillna(0).values
        short_f = pd.DataFrame(short_t, index=idx, columns=cols).ffill().fillna(0).values
        exp_l_lag = np.concatenate([[0.0], long_f[:-1].sum(axis=1)])

        # price relative to the last rebalance day's price
        px_rb = np.full((n, m), np.nan)
        px_rb[idxs] = px[idxs]
        px_base = pd.DataFrame(px_rb, index=idx, columns=cols).shift(1).ffill()
        px_base.iloc[0] = px[0]
        ratio = px / np.where(px_base.values == 0, 1.0, px_base.values)

        long_prev = np.vstack([np.zeros((1, m)), long_f[:-1]])
        short_prev = np.vstack([np.zeros((1, m)), short_f[:-1]])
        drifted_l = long_prev * ratio
        base = drifted_l.sum(axis=1) + (1.0 - exp_l_lag)
        base = np.where(base == 0, np.nan, base)
        drifted = np.nan_to_num(drifted_l / base[:, None]) + np.nan_to_num((short_prev * ratio) / base[:, None])

        out = drifted.copy()
        out[idxs] = np.nan_to_num(target[idxs])
        trades = np.zeros((n, m))
        trades[idxs] = np.nan_to_num(target[idxs]) - drifted[idxs]

        self.weights = pd.DataFrame(out, index=idx, columns=cols)
        self.trades_matrix = pd.DataFrame(trades, index=idx, columns=cols)
        return self

    # ── PnL accrual ────────────────────────────────────────────────────── #
    def period_return(self, market_data, trading_fee: float | None = None) -> pd.DataFrame:
        """Per-stock daily PnL: lagged weights x returns, minus fees, plus
        borrow carry on the short side. `market_data` is a MarketData or a
        plain returns DataFrame."""
        rets = market_data.returns if hasattr(market_data, "returns") else market_data
        rets = rets.reindex(index=self.weights.index, columns=self.weights.columns).fillna(0)
        pnl = self.weights.shift(1) * rets

        if trading_fee and self.trades_matrix is not None:
            pnl = pnl - (trading_fee * self.trades_matrix.abs()).shift(1)

        borrow = getattr(market_data, "daily_borrow_rate", None)
        if borrow is not None:
            borrow = borrow.reindex(index=self.weights.index, columns=self.weights.columns).fillna(0)
            pnl = pnl + self.weights.clip(upper=0) * borrow  # negative carry

        return pnl.fillna(0)

    def period_return_sum(self, market_data, trading_fee: float | None = None,
                          cash_leg: pd.Series | None = None) -> pd.Series:
        """Total daily PnL minus the cash/opportunity leg.

        `cash_leg` is a daily-return Series scaled by NET exposure:
        treasury for an absolute-return view (production tsy/CDI leg), or
        the benchmark's returns for excess-vs-benchmark on a long-only book.
        """
        total = self.period_return(market_data, trading_fee).sum(axis=1)
        if cash_leg is not None:
            net = self.weights.sum(axis=1)
            total = total - cash_leg.reindex(self.weights.index).fillna(0) * net
        return total.rename(self.name)

    # ── construction from an indicator ─────────────────────────────────── #
    @classmethod
    def from_indicator(cls, name: str, scores: pd.DataFrame, universe: pd.DataFrame,
                       side: str = "HML", pct: float = 0.2,
                       min_stocks: int = 10) -> "Portfolio":
        """Quantile portfolio from a scores matrix — the production H-M-L.

        side='HML'  long the top `pct` quantile, short the bottom (high
                    score minus low);
        side='LMH'  the reverse;
        side='LO'   long-only: top quantile, no short;
        side='SO'   short-only: bottom quantile.

        Days where either leg would hold fewer than `min_stocks`/2 names are
        zeroed — a 3-stock leg is noise wearing a portfolio costume.
        Weights come out normalized (split for LS, long=1 for LO).
        """
        valid = universe.reindex_like(scores).fillna(False) & scores.notna()
        vals = scores.where(valid).to_numpy(dtype=float)
        with np.errstate(all="ignore"):
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                q_hi = np.nanquantile(vals, 1 - pct, axis=1)
                q_lo = np.nanquantile(vals, pct, axis=1)
        long = (vals >= q_hi[:, None]) & ~np.isnan(vals)
        short = (vals <= q_lo[:, None]) & ~np.isnan(vals)

        if side in ("HML", "LO"):
            pass
        elif side in ("LMH", "SO"):
            long, short = short, long
        else:
            raise ValueError("side must be HML/LMH/LO/SO")
        if side in ("LO", "SO"):
            short = np.zeros_like(short)

        if min_stocks:
            bad = long.sum(axis=1) < max(min_stocks // 2, 1)
            if side not in ("LO", "SO"):
                bad |= short.sum(axis=1) < max(min_stocks // 2, 1)
            long[bad] = False
            short[bad] = False

        w = pd.DataFrame(long.astype(float) - short.astype(float),
                         index=scores.index, columns=scores.columns)
        p = cls(name=name, weights=w)
        return p.normalize(type="long" if side in ("LO", "SO") else "split")

    def long_only(self) -> "Portfolio":
        """The LO sleeve of an LS portfolio, renormalized to long = 1."""
        lo = self.get_long()
        return lo.normalize(type="long")

    # ── operators (for combination) ────────────────────────────────────── #
    def __add__(self, other: "Portfolio") -> "Portfolio":
        return Portfolio(f"{self.name}+{other.name}",
                         weights=self.weights.add(other.weights, fill_value=0))

    def __mul__(self, scalar: float) -> "Portfolio":
        p = self.clone()
        p.weights = p.weights * scalar
        return p

    __rmul__ = __mul__

    def __repr__(self) -> str:
        shape = self.weights.shape if self.weights is not None else None
        return f"Portfolio(name={self.name}, shape={shape})"
