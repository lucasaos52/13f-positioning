"""Pinned market panels and strictly backward-looking ETF characteristics."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def _read_panel(
    path: str | Path, columns: list[str] | pd.Index | None = None
) -> pd.DataFrame:
    """Read a wide panel, optionally projecting only required tickers.

    The pinned Yahoo files now contain the full reconstructed ETF universe.
    Research runs trade equity ETFs only, so projecting at CSV parse time
    prevents non-equity products from inflating memory and the liquidity
    universe while preserving a single auditable market-data cache.
    """

    usecols = None
    if columns is not None:
        header = pd.read_csv(path, nrows=0).columns.tolist()
        requested = set(map(str, columns))
        usecols = [header[0], *[column for column in header[1:] if column in requested]]
    out = pd.read_csv(path, usecols=usecols, index_col=0, parse_dates=True)
    out.index = pd.DatetimeIndex(out.index).tz_localize(None)
    return out.sort_index().apply(pd.to_numeric, errors="coerce")


class MarketPanels:
    """Market-data adapter used by signal construction and shared backtest."""

    def __init__(
        self,
        etf_adjusted_path: str | Path,
        etf_raw_path: str | Path,
        etf_volume_path: str | Path,
        common_adjusted_path: str | Path,
        common_map_path: str | Path,
        benchmark_path: str | Path,
        etf_master: pd.DataFrame,
    ):
        required_tickers = pd.Index(etf_master["ticker"].dropna().astype(str).unique())
        required_tickers = required_tickers.union(pd.Index(["SPY", "IWM", "QQQ"]))
        self.prices = _read_panel(etf_adjusted_path, required_tickers)
        missing_factors = {"SPY", "IWM", "QQQ"} - set(self.prices)
        if missing_factors:
            raise ValueError(f"ETF price panel missing required factors: {sorted(missing_factors)}")
        self.prices_raw = _read_panel(etf_raw_path, self.prices.columns).reindex_like(self.prices)
        self.volume = _read_panel(etf_volume_path, self.prices.columns).reindex_like(self.prices)
        self.returns = self.prices.pct_change(fill_method=None).fillna(0.0)
        self.dollar_volume = (self.prices_raw * self.volume).fillna(0.0)
        self.volatility = self.returns.rolling(63, min_periods=40).std() * np.sqrt(252)
        self.daily_borrow_rate = pd.DataFrame(
            (1.005 ** (1 / 252) - 1), index=self.prices.index, columns=self.prices.columns
        )

        bench = _read_panel(benchmark_path).reindex(self.prices.index).ffill()
        # The repository cache is SPY + IRX.  SPY is both a traded ETF and the
        # opportunity/market benchmark for diagnostics.
        spy_col = "SPY" if "SPY" in bench else bench.columns[0]
        self.benchmark_returns = bench[spy_col].pct_change(fill_method=None).fillna(0.0).rename("SPY")
        irx = next((c for c in bench if "IRX" in c.upper()), None)
        self.treasury_yield = (
            ((1 + bench[irx] / 100.0) ** (1 / 252) - 1).fillna(0.0)
            if irx is not None
            else pd.Series(0.0, index=self.prices.index, name="tsy_daily")
        )

        self.common_prices = _read_panel(common_adjusted_path)
        mapping = pd.read_csv(common_map_path, dtype=str).dropna(subset=["instrument_id", "ticker"])
        self.instrument_to_ticker = mapping.drop_duplicates("instrument_id").set_index("instrument_id")["ticker"]
        etf_map = etf_master.set_index("instrument_id")["ticker"]
        self.instrument_to_ticker = pd.concat([self.instrument_to_ticker, etf_map])
        self.instrument_to_ticker = self.instrument_to_ticker[~self.instrument_to_ticker.index.duplicated(keep="last")]

    def _row_on_or_before(self, panel: pd.DataFrame, date: str | pd.Timestamp) -> pd.Series:
        pos = panel.index.searchsorted(pd.Timestamp(date), side="right") - 1
        if pos < 0:
            return pd.Series(np.nan, index=panel.columns)
        return panel.iloc[pos]

    def instrument_total_returns(
        self, previous_period: str | pd.Timestamp, current_period: str | pd.Timestamp
    ) -> pd.Series:
        """CUSIP-indexed total returns; missing names receive the SPY return.

        The fallback affects only the manager portfolio-drift denominator and
        is reported as a coverage statistic. ETF returns themselves always
        come from the pinned ETF price panel.
        """

        p0, p1 = pd.Timestamp(previous_period), pd.Timestamp(current_period)
        c0 = self._row_on_or_before(self.common_prices, p0)
        c1 = self._row_on_or_before(self.common_prices, p1)
        common_ret = c1.div(c0).sub(1.0).replace([np.inf, -np.inf], np.nan)
        e0 = self._row_on_or_before(self.prices, p0)
        e1 = self._row_on_or_before(self.prices, p1)
        etf_ret = e1.div(e0).sub(1.0).replace([np.inf, -np.inf], np.nan)
        by_ticker = pd.concat([common_ret, etf_ret])
        by_ticker = by_ticker[~by_ticker.index.duplicated(keep="last")]
        result = self.instrument_to_ticker.map(by_ticker)
        result.index = self.instrument_to_ticker.index
        return result

    def spy_period_return(self, previous_period: pd.Timestamp, current_period: pd.Timestamp) -> float:
        p0 = float(self._row_on_or_before(self.prices, previous_period).get("SPY", np.nan))
        p1 = float(self._row_on_or_before(self.prices, current_period).get("SPY", np.nan))
        return p1 / p0 - 1.0 if np.isfinite(p0) and p0 > 0 and np.isfinite(p1) else 0.0

    def residual_quarter_return(
        self, previous_period: str | pd.Timestamp, current_period: str | pd.Timestamp
    ) -> pd.Series:
        """ETF holding-period residual using betas estimated before the period.

        Betas use up to 252 daily observations ending at the previous quarter.
        The holding-period residual uses SPY plus size/technology tilts
        ``IWM-SPY`` and ``QQQ-SPY``.  No return after current period-end enters.
        """

        p0, p1 = pd.Timestamp(previous_period), pd.Timestamp(current_period)
        hist = self.returns.loc[:p0].tail(252)
        period = self.returns.loc[(self.returns.index > p0) & (self.returns.index <= p1)]
        if len(hist) < 60 or period.empty:
            return pd.Series(np.nan, index=self.prices.columns)
        factors_hist = pd.DataFrame(
            {
                "SPY": hist["SPY"],
                "SMALL": hist["IWM"] - hist["SPY"],
                "TECH": hist["QQQ"] - hist["SPY"],
            }
        ).fillna(0.0)
        factors_period = pd.DataFrame(
            {
                "SPY": period["SPY"],
                "SMALL": period["IWM"] - period["SPY"],
                "TECH": period["QQQ"] - period["SPY"],
            }
        ).fillna(0.0)
        x = np.column_stack([np.ones(len(factors_hist)), factors_hist.to_numpy()])
        factor_hpr = np.log1p(factors_period.clip(lower=-0.999)).sum().to_numpy()
        out: dict[str, float] = {}
        for ticker in self.prices:
            y = hist[ticker]
            valid = y.notna() & factors_hist.notna().all(axis=1)
            if valid.sum() < 60 or period[ticker].notna().sum() < 20:
                out[ticker] = np.nan
                continue
            beta = np.linalg.lstsq(x[valid], y[valid].to_numpy(), rcond=None)[0][1:]
            actual = float(np.log1p(period[ticker].clip(lower=-0.999)).sum())
            out[ticker] = actual - float(beta @ factor_hpr)
        return pd.Series(out)

    def public_features(self, date: str | pd.Timestamp) -> pd.DataFrame:
        """ETF controls known by ``date`` for abnormal-adoption residuals."""

        d = pd.Timestamp(date)
        r = self.returns.loc[:d]
        p = self.prices.loc[:d]
        raw = self.prices_raw.loc[:d]
        dv = self.dollar_volume.loc[:d]
        if p.empty:
            return pd.DataFrame(index=self.prices.columns)
        momentum = p.iloc[-1].div(p.iloc[max(0, len(p) - 64)]).sub(1.0)
        vol = r.tail(63).std() * np.sqrt(252)
        spy = r["SPY"].tail(126)
        var_spy = spy.var()
        beta = r.tail(126).apply(lambda s: s.cov(spy) / var_spy if var_spy > 0 else np.nan)
        adv = dv.tail(63).median()
        age = p.notna().sum()
        return pd.DataFrame(
            {
                "momentum_63d": momentum,
                "volatility_63d": vol,
                "beta_126d": beta,
                "log_adv_63d": np.log1p(adv),
                "log_price": np.log(raw.iloc[-1].where(raw.iloc[-1] > 0)),
                "log_age": np.log1p(age),
            }
        )

    def shock_state(self, date: str | pd.Timestamp) -> tuple[pd.Series, bool]:
        """Cross-sectional 5-day residual shock and an ex-ante market-stress flag."""

        d = pd.Timestamp(date)
        r = self.returns.loc[:d]
        if len(r) < 126:
            return pd.Series(np.nan, index=self.prices.columns), False
        trailing = r.tail(126)
        spy = trailing["SPY"]
        var_spy = spy.var()
        beta = trailing.apply(lambda s: s.cov(spy) / var_spy if var_spy > 0 else np.nan)
        hpr5 = np.log1p(trailing.tail(5).clip(lower=-0.999)).sum()
        residual = hpr5 - beta * float(hpr5["SPY"])
        hist_spy5 = np.log1p(r["SPY"].clip(lower=-0.999)).rolling(5).sum().shift(1).dropna().tail(504)
        stress = bool(float(hpr5["SPY"]) <= float(hist_spy5.quantile(0.10))) if len(hist_spy5) >= 100 else False
        return residual, stress
