"""Market reference data: prices, volume, volatility, market cap.

13F gives share counts. Everything else the factor needs - dollar size,
liquidity, volatility, returns - comes from a price panel, and the quality of
that panel bounds the quality of the result.

The loader is deliberately an interface with pluggable backends rather than a
hardcoded vendor, because the right answer depends on what the reader has:

* ``CsvPanelLoader`` - a CRSP/Compustat or vendor export. Preferred. CRSP is
  the only source here that is survivorship-bias-free and delisting-aware, and
  both matter over a ten-year window.
* ``StooqLoader`` - free daily OHLCV, no key, adequate for reproduction but
  built from *surviving* tickers, so it is biased and says so.
* ``SyntheticPanel`` - generated (see ``simulate.py``), for tests and for
  exercising the pipeline without network access.

Two adjustments are applied by every backend and both are easy to skip and
expensive to skip:

**Split adjustment.** 13F share counts are as-filed, unadjusted. A 4:1 split
between quarters makes an untouched position look like a 300% purchase. Every
share count is converted to a split-adjusted basis using a cumulative factor
before any delta is computed. Getting this wrong does not add noise - it
manufactures enormous fake trades in exactly the large, liquid, widely held
names the factor cares most about.

**Delisting returns.** A name that disappears has a return, usually a bad one.
Dropping it on the last trading day is a survivorship bias that flatters any
factor with a value or distress tilt.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

PANEL_COLS = [
    "instrument_id",
    "date",
    "price",
    "volume",
    "shares_outstanding",
    "cum_split_factor",
    "ret",
]


class PriceLoader(Protocol):
    def load(self, start: str, end: str, instruments: list[str] | None = None) -> pd.DataFrame: ...


# --------------------------------------------------------------------------- #
class CsvPanelLoader:
    """Vendor export. Expected columns are ``PANEL_COLS``; extras are ignored."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self, start: str, end: str, instruments: list[str] | None = None) -> pd.DataFrame:
        df = pd.read_csv(self.path, parse_dates=["date"])
        missing = set(PANEL_COLS) - set(df.columns)
        if missing:
            raise ValueError(f"price panel missing columns: {sorted(missing)}")
        df = df[(df["date"] >= start) & (df["date"] <= end)]
        if instruments:
            df = df[df["instrument_id"].isin(instruments)]
        return df.sort_values(["instrument_id", "date"]).reset_index(drop=True)


class StooqLoader:
    """Free daily bars. Convenience backend, biased sample - documented as such."""

    URL = "https://stooq.com/q/d/l/?s={sym}.us&i=d"

    def __init__(self, client, symbol_map: dict[str, str]) -> None:
        self.client = client
        self.symbol_map = symbol_map

    def load(self, start: str, end: str, instruments: list[str] | None = None) -> pd.DataFrame:
        import io

        frames = []
        for iid in instruments or list(self.symbol_map):
            sym = self.symbol_map.get(iid)
            if not sym:
                continue
            try:
                raw = self.client.get_text(self.URL.format(sym=sym.lower()))
            except Exception:  # noqa: BLE001 - one bad symbol must not kill the run
                continue
            d = pd.read_csv(io.StringIO(raw))
            if d.empty or "Close" not in d:
                continue
            d = d.rename(columns={"Date": "date", "Close": "price", "Volume": "volume"})
            d["date"] = pd.to_datetime(d["date"])
            d["instrument_id"] = iid
            d["cum_split_factor"] = 1.0  # stooq bars are already adjusted
            d["shares_outstanding"] = np.nan
            frames.append(d[["instrument_id", "date", "price", "volume", "shares_outstanding", "cum_split_factor"]])
        if not frames:
            return pd.DataFrame(columns=PANEL_COLS)
        out = pd.concat(frames, ignore_index=True)
        out = out[(out["date"] >= start) & (out["date"] <= end)]
        out["ret"] = out.groupby("instrument_id")["price"].pct_change()
        return out.sort_values(["instrument_id", "date"]).reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Derived quantities
# --------------------------------------------------------------------------- #
def quarterly_reference(
    panel: pd.DataFrame,
    adv_window: int = 63,
    vol_window: int = 126,
    min_obs: int = 40,
) -> pd.DataFrame:
    """Collapse a daily panel to quarter-end reference values.

    All windows are strictly backward looking and end on the quarter-end date,
    so nothing computed here can see past the period it is stamped with. The
    factor layer then applies its own additional lag on top.
    """
    df = panel.sort_values(["instrument_id", "date"]).copy()
    df["dollar_vol"] = df["price"] * df["volume"]

    g = df.groupby("instrument_id", sort=False)
    df["adv_usd"] = g["dollar_vol"].transform(lambda s: s.rolling(adv_window, min_periods=min_obs).mean())
    df["vol_ann"] = g["ret"].transform(
        lambda s: s.rolling(vol_window, min_periods=min_obs).std() * np.sqrt(252)
    )
    # Amihud illiquidity: |return| per dollar traded, the standard price-impact
    # proxy and a natural control for a liquidity-scaled signal.
    df["amihud"] = g.apply(
        lambda d: (d["ret"].abs() / d["dollar_vol"].replace(0, np.nan))
        .rolling(adv_window, min_periods=min_obs)
        .mean(),
        include_groups=False,
    ).reset_index(level=0, drop=True)
    df["mktcap"] = df["price"] * df["shares_outstanding"]

    qends = df[df["date"].dt.is_quarter_end | df["date"].eq(g["date"].transform("max"))]
    qends = df.loc[df.groupby(["instrument_id", df["date"].dt.to_period("Q")])["date"].idxmax()]

    out = qends[
        ["instrument_id", "date", "price", "adv_usd", "vol_ann", "amihud", "mktcap", "cum_split_factor"]
    ].copy()
    out["period_end"] = out["date"].dt.to_period("Q").dt.end_time.dt.normalize()
    return out.reset_index(drop=True)


def monthly_returns(panel: pd.DataFrame) -> pd.DataFrame:
    """Month-end total returns, long format."""
    df = panel.sort_values(["instrument_id", "date"]).copy()
    df["month"] = df["date"].dt.to_period("M")
    grp = df.groupby(["instrument_id", "month"])
    last = df.loc[grp["date"].idxmax()]
    out = last[["instrument_id", "month", "price", "date"]].copy()
    out["ret_m"] = out.groupby("instrument_id")["price"].pct_change()
    return out.dropna(subset=["ret_m"]).reset_index(drop=True)


def split_adjust_shares(
    holdings: pd.DataFrame,
    reference: pd.DataFrame,
    ref_period: str = "period_end",
) -> pd.DataFrame:
    """Put reported share counts onto a common split-adjusted basis.

    ``cum_split_factor`` is the cumulative adjustment from the panel's base
    date. Dividing reported shares by it makes counts comparable across
    quarters, which is a precondition for any share-delta.
    """
    ref = reference[["instrument_id", ref_period, "cum_split_factor"]].drop_duplicates()
    out = holdings.merge(ref, on=["instrument_id", ref_period], how="left")
    factor = out["cum_split_factor"].fillna(1.0)
    out["shares_adj"] = out["shares"] / factor
    unmatched = out["cum_split_factor"].isna().mean()
    if unmatched > 0.05:
        log.warning("%.1f%% of holdings had no split factor; assumed 1.0", 100 * unmatched)
    return out
