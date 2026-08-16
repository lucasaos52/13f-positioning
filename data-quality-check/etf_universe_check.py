"""Data-quality check: do ETF instruments leak into the factor layer?

    python etf_universe_check.py

Three questions, answered with numbers (originally run inline on
2026-08-16; this script makes the diagnostic reproducible):
  1. How many audited ETF instruments (factors/ETF_strat flag list) are in
     the CUSIP->ticker crosswalk?           (answer then: 1 of 7,886)
  2. How many ETF tickers are in the price panel?      (answer then: 0)
  3. How much book VALUE do ETF lines represent inside 13F filings?
     (answer then: ~14.6% / $3.8T in 2025Q3)
Reading: ETFs were never tradable in any backtest (never mapped, never
priced) - but their lines sit inside manager books and inflate weight
denominators/conviction thresholds. Whether THAT matters was tested in
factors/champion_noetf (paired delta t=+0.08: innocuous).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "factors"))
sys.path.insert(0, str(ROOT / "factors" / "general_plan"))

import panel as pn                                  # noqa: E402
from run_all import load_market                     # noqa: E402


def main() -> None:
    etf = pd.read_csv(ROOT / "factors" / "ETF_strat" / "data"
                      / "etf_universe_flags.csv",
                      usecols=["instrument_id", "is_etf", "ticker"])
    etf = etf[etf["is_etf"] == True]                # noqa: E712
    cmap, mdta = load_market()

    in_cmap = [i for i in etf["instrument_id"] if i in cmap]
    tk = set(t for t in etf["ticker"].dropna())
    in_px = tk & set(mdta.prices.columns)
    print(f"flagged ETFs: {len(etf)} | with CUSIP in crosswalk: "
          f"{len(in_cmap)}")
    print(f"ETF tickers in the price panel: {len(in_px)}")

    q = pn.quarters()[-3]
    snap = pn.snapshot_as_of(q, q + pd.Timedelta(days=50))
    ev = snap[snap["instrument_id"].isin(set(etf["instrument_id"]))]
    tot = snap["value_usd"].sum()
    print(f"{q.date()}: ETF value inside books: "
          f"${ev['value_usd'].sum() / 1e9:,.1f}bn = "
          f"{ev['value_usd'].sum() / tot:.1%} of total "
          f"({ev['instrument_id'].nunique()} instruments)")


if __name__ == "__main__":
    main()
