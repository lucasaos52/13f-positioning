"""Market data from Yahoo Finance, shaped like the multifactor's MarketData.

Same conventions as the production model, no database anywhere:

    - every panel is a DataFrame indexed by trading date, one column per
      ticker (dates x stocks);
    - `returns` are daily simple returns from adjusted prices, NaN -> 0;
    - `volatility` is a rolling 252d annualized std;
    - `borrow_rate` is annualized, `daily_borrow_rate = (1+r)^(1/252)-1`,
      accrued daily against short weights inside Portfolio.period_return.
      (The 13F reference project does the same thing: a flat borrow rate on
      the short sleeve, no per-name vendor data — there is none for free.)
    - `benchmark_returns`: daily S&P 500 (^GSPC) returns, where the
      production model uses IBOV;
    - `treasury_yield`: DAILY risk-free return derived from the 13-week
      T-bill (^IRX), the cash/opportunity leg — production uses CDI.

Survivorship, stated not hidden: Yahoo only carries live tickers and the
S&P list is today's membership. Fine for prototyping factor mechanics;
not evidence about long-run premia.
"""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd


def log(text: str, indent: int = 0) -> None:
    prefix = "\t" * indent
    print(f"{prefix}{datetime.now():%H:%M:%S} - {text}", flush=True)


class Dates:
    """Trading-calendar helper mirroring the multifactor `Dates` interface,
    built from the panel's own index (the panel's dates ARE the calendar)."""

    def __init__(self, dates: pd.DatetimeIndex, rebalance_period: str = "1 month"):
        self.mdates = pd.DataFrame({"date_ref": pd.DatetimeIndex(dates)})
        self._rebalance_period = rebalance_period

    @property
    def all_dates(self) -> pd.DatetimeIndex:
        return pd.DatetimeIndex(self.mdates["date_ref"])

    def get_idxs(self, period: Optional[str] = None, first_date=None) -> np.ndarray:
        """Positional indexes of period endpoints (the rebalance days)."""
        dates = self.all_dates
        mask = np.ones(len(dates), dtype=bool)
        if first_date is not None:
            mask &= dates >= pd.Timestamp(first_date)
        sub = dates[mask]
        period = period or self._rebalance_period
        if period == "1 day":
            idxs = np.arange(len(sub))
        else:
            freq = {"1 month": "ME", "1 quarter": "QE", "1 week": "W", "1 year": "YE"}.get(period, "ME")
            ends = sub.to_series().resample(freq).last().dropna()
            idxs = np.searchsorted(sub, ends.values, side="right") - 1
            idxs = np.unique(idxs[(idxs >= 0) & (idxs < len(sub))])
        return idxs if mask.all() else np.flatnonzero(mask)[idxs]


def _field(raw: pd.DataFrame, field: str, tickers: list[str]) -> pd.DataFrame:
    """yfinance gives (field, ticker) MultiIndex columns for multi-ticker
    downloads and flat columns for one ticker; normalize both shapes."""
    out = raw[field].copy() if isinstance(raw.columns, pd.MultiIndex) else raw[[field]].set_axis(tickers[:1], axis=1)
    out.index = pd.DatetimeIndex(out.index).tz_localize(None)
    return out.sort_index()


def sp500_tickers(cache_dir: str | Path = "data") -> list[str]:
    """Today's S&P 500 membership (Wikipedia), cached. Survivorship-biased
    by construction — today's list applied to the whole past."""
    cache = Path(cache_dir) / "sp500_tickers.csv"
    if cache.exists():
        return pd.read_csv(cache)["ticker"].tolist()
    # Wikipedia 403s urllib's default User-Agent; fetch with an identified one.
    import io
    import requests
    html = requests.get(
        "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
        headers={"User-Agent": "factors-backtest/0.1 (research; contact via repo)"},
        timeout=30,
    ).text
    df = pd.read_html(io.StringIO(html))[0]
    tickers = df["Symbol"].astype(str).str.replace(".", "-", regex=False).str.strip().tolist()
    cache.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"ticker": tickers}).to_csv(cache, index=False)
    return tickers


class MarketData:
    """Yahoo-fed twin of the multifactor MarketData."""

    def __init__(self, tickers: list[str], start: str, end: Optional[str] = None,
                 benchmark: str = "^GSPC", treasury: str = "^IRX",
                 borrow_rate: float = 0.0050, vol_window: int = 252,
                 cache_dir: str | Path = "data", refresh: bool = False,
                 batch_size: int = 150):
        import yfinance as yf

        self.tickers = list(dict.fromkeys(tickers))
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        end = end or pd.Timestamp.today().strftime("%Y-%m-%d")

        key = f"{len(self.tickers)}tk_{start}_{end}".replace("-", "")
        paths = {n: self.cache_dir / f"{n}_{key}.csv" for n in ("prices", "prices_raw", "volume")}

        if not refresh and all(p.exists() for p in paths.values()):
            log(f"loading cached Yahoo panels ({key})")
            self.prices = pd.read_csv(paths["prices"], index_col=0, parse_dates=True)
            self.prices_raw = pd.read_csv(paths["prices_raw"], index_col=0, parse_dates=True)
            self.volume = pd.read_csv(paths["volume"], index_col=0, parse_dates=True)
        else:
            log(f"downloading {len(self.tickers)} tickers from Yahoo ({start} -> {end})")
            adj, rawp, vol = [], [], []
            for i in range(0, len(self.tickers), batch_size):
                chunk = self.tickers[i:i + batch_size]
                raw = yf.download(chunk, start=start, end=end, auto_adjust=False,
                                  progress=False, threads=True)
                if raw.empty:
                    log(f"batch {i // batch_size + 1}: EMPTY, skipped", 1)
                    continue
                adj.append(_field(raw, "Adj Close", chunk))
                rawp.append(_field(raw, "Close", chunk))
                vol.append(_field(raw, "Volume", chunk))
                log(f"batch {i // batch_size + 1}: {len(chunk)} tickers", 1)
                time.sleep(1.0)  # Yahoo throttles bursts
            if not adj:
                raise RuntimeError("Yahoo returned no data for any batch")
            self.prices, self.prices_raw, self.volume = (pd.concat(x, axis=1) for x in (adj, rawp, vol))
            for n, df in (("prices", self.prices), ("prices_raw", self.prices_raw), ("volume", self.volume)):
                df.to_csv(paths[n])

        # tickers with zero data are dropped LOUDLY, never silently
        dead = self.prices.columns[self.prices.notna().sum() == 0].tolist()
        if dead:
            log(f"{len(dead)} tickers had no data and were dropped: {dead[:8]}")
            for attr in ("prices", "prices_raw", "volume"):
                setattr(self, attr, getattr(self, attr).drop(columns=dead, errors="ignore"))
        self.tickers = self.prices.columns.tolist()

        self.returns = self.prices.pct_change(fill_method=None).fillna(0)
        self.dollar_volume = (self.prices_raw * self.volume).fillna(0)
        self.volatility = self.returns.rolling(vol_window, min_periods=vol_window // 2).std() * np.sqrt(252)

        self.borrow_rate = pd.DataFrame(borrow_rate, index=self.prices.index, columns=self.prices.columns)
        self.daily_borrow_rate = (1 + self.borrow_rate) ** (1 / 252) - 1

        # Benchmark + treasury: cached and LOUD on failure. Yahoo rate-limits
        # bursts, and a benchmark that silently degrades to zeros converts
        # every "excess return" downstream into a raw return - an invalid
        # backtest that looks perfectly ordinary. Better no run than that run.
        bench_cache = self.cache_dir / f"bench_{benchmark}_{treasury}_{start}_{end}".replace(
            "-", "").replace("^", "")
        bench_cache = bench_cache.with_suffix(".csv")
        px = None
        if not refresh and bench_cache.exists():
            px = pd.read_csv(bench_cache, index_col=0, parse_dates=True)
        else:
            log(f"downloading benchmark {benchmark} + treasury {treasury}")
            for attempt in range(4):
                bt = yf.download([benchmark, treasury], start=start, end=end,
                                 auto_adjust=False, progress=False)
                if not bt.empty:
                    cand = _field(bt, "Adj Close", [benchmark, treasury])
                    if benchmark in cand and cand[benchmark].notna().sum() > 100:
                        px = cand
                        px.to_csv(bench_cache)
                        break
                wait = 30 * (attempt + 1)
                log(f"benchmark download incomplete (rate limit?); retry in {wait}s")
                time.sleep(wait)
        if px is None or benchmark not in px or px[benchmark].notna().sum() <= 100:
            raise RuntimeError(
                f"benchmark {benchmark} could not be downloaded (Yahoo rate limit?). "
                "Refusing to continue: a silent zero benchmark turns every excess "
                "return into a raw return and invalidates the whole backtest."
            )
        px = px.reindex(self.prices.index).ffill()
        self.benchmark_returns = px[benchmark].pct_change(fill_method=None).fillna(0).rename(benchmark)
        # ^IRX quotes the annualized 13w bill yield in percent -> daily return
        self.treasury_yield = (((1 + px[treasury] / 100.0) ** (1 / 252)) - 1).fillna(0).rename("tsy_daily")

    def dates(self, rebalance_period: str = "1 month") -> Dates:
        return Dates(self.prices.index, rebalance_period)
