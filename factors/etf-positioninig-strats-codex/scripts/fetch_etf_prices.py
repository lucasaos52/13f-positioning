"""Fetch and pin adjusted ETF prices used by the empirical baseline."""

from __future__ import annotations

from pathlib import Path
import time

import pandas as pd
import yfinance as yf

HERE = Path(__file__).resolve().parents[1]


def main() -> None:
    master = pd.read_csv(HERE / "reference" / "etf_master_seed.csv")
    tickers = sorted(master.loc[master["asset_class"].eq("equity"), "ticker"].unique())
    data = yf.download(
        tickers, start="2013-01-01", end="2026-08-16", auto_adjust=False,
        actions=True, progress=False, threads=False, group_by="column", timeout=30,
    )
    if data.empty:
        raise RuntimeError("Yahoo returned no ETF prices; cache was not changed")
    outdir = HERE / "data"
    outdir.mkdir(exist_ok=True)
    fields = {"Adj Close": "etf_prices_adjusted.csv.gz", "Close": "etf_prices_raw.csv.gz",
              "Volume": "etf_volume.csv.gz", "Stock Splits": "etf_splits.csv.gz"}
    for field, filename in fields.items():
        if field not in data.columns.get_level_values(0):
            continue
        panel = data[field]
        if isinstance(panel, pd.Series):
            panel = panel.to_frame(tickers[0])
        panel.index.name = "date"
        panel.to_csv(outdir / filename)
    missing = sorted(set(tickers) - set(data["Adj Close"].dropna(how="all").columns))
    (outdir / "price_fetch_manifest.txt").write_text(
        f"fetched_utc={pd.Timestamp.now(tz='UTC')}\n"
        f"tickers={','.join(tickers)}\nmissing={','.join(missing)}\n",
        encoding="utf-8",
    )
    print(f"{time.strftime('%H:%M:%S')} - wrote {len(tickers) - len(missing)}/{len(tickers)} tickers")


if __name__ == "__main__":
    main()

