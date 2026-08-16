"""Market cap panel from Yahoo raw close x historical shares outstanding.

Why real market cap matters here (and why the common shortcut in 13F studies
could not do this): the ACWB market tilt, the size neutralisation and two of
the null factors (dIO, PSO) need shares outstanding AS OF each date. The
usual substitute - the stock's weight in the aggregate 13F book - is
partially circular: crowding and "size" then share the same numerator, which
mechanically inflates their correlation. Price x share count breaks that.

Sources and their honest limits:
  - `get_shares_full` (cached per ticker by fetch_shares.py): raw counts at
    irregular event dates, verified to start ~Oct 2015 and to capture splits
    in the raw count (AAPL 4.33bn -> 17.10bn at the 4:1).
  - pre-2015 (and gaps): BACK-PROJECTION from the earliest known count via
    the adjusted-price ratio - mktcap_t ~ mktcap_first x adjP_t / adjP_first.
    Exact under splits, wrong by cumulative buyback/dilution drift (~1-3%/yr).
    Acceptable for cross-sectional RANKS, stated in the memo, and flagged
    per-cell via `is_projected` so diagnostics can split by data quality.
  - survivors only, as with everything Yahoo. The dead names have no shares
    series and no prices either, so they exit the tradable universe jointly -
    a bias that is stated, not hidden.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
SHARES_DIR = HERE / "data" / "shares"


def log(msg: str) -> None:
    print(f"{datetime.now():%H:%M:%S} - {msg}", flush=True)


def shares_panel(dates: pd.DatetimeIndex, tickers: list[str],
                 prices_adj: pd.DataFrame | None = None,
                 prices_raw: pd.DataFrame | None = None) -> pd.DataFrame:
    """Daily shares-outstanding panel (dates x tickers), ffilled between
    event dates; back-projected before the first observation when adjusted
    and raw prices are supplied.

    Back-projection derivation: adjusted price already folds splits in, so
        mktcap_t = mktcap_first * adjP_t / adjP_first   (no-issuance approx)
        shares_t = mktcap_t / rawP_t
    which reproduces the correct pre-split raw share count without knowing
    the split calendar."""
    cols = {}
    for tk in tickers:
        f = SHARES_DIR / f"{tk}.csv"
        # zero-byte files are interrupted writes; skip so the resumable
        # fetcher redownloads them instead of crashing every consumer
        if not f.exists() or f.stat().st_size < 20:
            continue
        s = pd.read_csv(f, index_col=0, parse_dates=True)["shares"]
        s = s[~s.index.duplicated(keep="last")].sort_index()
        cols[tk] = s.reindex(dates.union(s.index)).ffill().reindex(dates)
    if not cols:
        return pd.DataFrame(index=dates)
    panel = pd.DataFrame(cols)
    log(f"shares panel: {panel.shape[1]} tickers with data "
        f"({len(tickers) - panel.shape[1]} missing)")

    if prices_adj is not None and prices_raw is not None:
        first_valid = panel.apply(lambda c: c.first_valid_index())
        for tk, fv in first_valid.dropna().items():
            if fv <= dates[0] or tk not in prices_adj:
                continue
            pre = dates[dates < fv]
            adj, raw = prices_adj[tk], prices_raw[tk]
            if fv not in adj.index or adj.loc[fv] == 0:
                continue
            mcap_first = panel.at[fv, tk] * raw.loc[fv]
            proj = (mcap_first * adj.loc[pre] / adj.loc[fv]) / raw.loc[pre]
            panel.loc[pre, tk] = proj
    return panel


def mktcap_panel(prices_raw: pd.DataFrame, shares: pd.DataFrame) -> pd.DataFrame:
    common = [c for c in prices_raw.columns if c in shares.columns]
    return prices_raw[common] * shares[common]
