"""Historical shares outstanding from Yahoo, one cached CSV per ticker.

Why this exists: three pieces of the research plan need shares outstanding
(or market cap) that Yahoo's `.info` does not provide historically:

  - w_mkt in the ACWB active weight (market tilt needs market cap);
  - the null factors dIO and PSO (institutional shares / shares outstanding);
  - size neutralisation against real log-mktcap instead of the circular
    "sum of 13F holdings" proxy.

`Ticker.get_shares_full()` returns raw share counts at irregular event dates,
verified live: coverage starts ~Oct 2015, and AAPL's 4:1 split shows up as a
4.33bn -> 17.10bn jump (ratio 3.95 - the 0.05 gap is genuine buybacks). For
2013-2015 the loaders in market_cap.py back-project from the first known
count via the adjusted-price ratio, an approximation documented there.

Resumable by design: one file per ticker, skip if present, so a Yahoo rate
limit mid-run costs nothing but a re-invocation. Failures are recorded in
_failed.csv rather than silently skipped (the repository's loud-failure rule).
"""
from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
SHARES_DIR = HERE / "data" / "shares"
MAP_FILE = HERE.parents[1] / "notebooks" / "data" / "cm_map_wide.csv"


def log(msg: str) -> None:
    print(f"{datetime.now():%H:%M:%S} - {msg}", flush=True)


def main(limit: int | None = None) -> None:
    import yfinance as yf

    tickers = sorted(
        pd.read_csv(MAP_FILE, dtype=str).dropna()["ticker"].unique())
    if limit:
        tickers = tickers[:limit]
    SHARES_DIR.mkdir(parents=True, exist_ok=True)
    done = {p.stem for p in SHARES_DIR.glob("*.csv")} - {"_failed"}
    todo = [t for t in tickers if t not in done]
    log(f"{len(tickers)} tickers, {len(done)} cached, {len(todo)} to fetch")

    failed = []
    for i, tk in enumerate(todo):
        try:
            s = yf.Ticker(tk).get_shares_full(start="2013-01-01")
            if s is None or len(s) == 0:
                failed.append({"ticker": tk, "reason": "empty"})
            else:
                out = s.to_frame("shares")
                out.index = pd.DatetimeIndex(out.index).tz_localize(None)
                # collapse same-day duplicates (Yahoo emits several per day)
                out = out.groupby(level=0).last()
                out.to_csv(SHARES_DIR / f"{tk}.csv")
        except Exception as e:  # noqa: BLE001 - record and continue
            failed.append({"ticker": tk, "reason": f"{type(e).__name__}: {e}"[:120]})
            if "RateLimit" in type(e).__name__ or "429" in str(e):
                log(f"rate limited at {tk} ({i}/{len(todo)}); sleeping 120s")
                time.sleep(120)
        if (i + 1) % 100 == 0:
            log(f"{i + 1}/{len(todo)} fetched, {len(failed)} failed")
        time.sleep(0.35)  # stay under Yahoo's burst threshold

    if failed:
        pd.DataFrame(failed).to_csv(SHARES_DIR / "_failed.csv", index=False)
    log(f"done: {len(todo) - len(failed)} fetched, {len(failed)} failed")


if __name__ == "__main__":
    main(limit=int(sys.argv[1]) if len(sys.argv) > 1 else None)
