"""Prep for factor_cucuringu_miori_v1.ipynb: CUSIP->ticker map + signal file.

The imbalance panel (from prep_analysis_v1.py) is CUSIP-keyed; the Yahoo
backtester is ticker-keyed. With no paid crosswalk, the map is built by
matching normalised issuer names (13F side) against the S&P 500 constituent
names (Wikipedia side). Ambiguous names — one name spanning several tickers
(share classes: GOOG/GOOGL) or several CUSIPs — are DROPPED and counted,
never guessed. Coverage is reported; the notebook prints it.

Known limitation, stated: the map is undated (today's CUSIP for today's
ticker), so names that changed CUSIP mid-sample lose their older quarters.
The dated crosswalk (CRSP ncusip) fixes this later.

Output: notebooks/data/cm_signal_quarters.csv
    period_end, avail_date (= period_end + 71d), ticker, ti, vi, n_active
"""
from __future__ import annotations

import io
import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[0]
DATA = HERE / "data"
CURATED = ROOT / "crowdflow" / "data" / "20_curated"

AVAIL_DAYS = 71  # signal readable at p+70 (the panel's vantage) + 1 to trade

_STOP = {
    "INC", "INCORPORATED", "CORP", "CORPORATION", "CO", "COMPANY", "PLC", "LTD",
    "LIMITED", "LP", "LLC", "SA", "NV", "AG", "THE", "GROUP", "HOLDINGS",
    "HOLDING", "COS", "COMPANIES", "TRUST", "CL", "CLASS", "A", "B", "C",
    "COM", "NEW", "DEL", "&",
}


def norm_name(s: str) -> str:
    s = re.sub(r"[^A-Za-z0-9 ]", " ", str(s).upper())
    toks = [t for t in s.split() if t not in _STOP]
    return " ".join(toks)


def sp500_names() -> pd.DataFrame:
    cache = DATA / "sp500_names.csv"
    if cache.exists():
        return pd.read_csv(cache)
    html = requests.get(
        "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
        headers={"User-Agent": "factors-backtest/0.1 (research)"}, timeout=30).text
    df = pd.read_html(io.StringIO(html))[0]
    out = pd.DataFrame({
        "ticker": df["Symbol"].astype(str).str.replace(".", "-", regex=False).str.strip(),
        "name": df["Security"].astype(str),
    })
    out.to_csv(cache, index=False)
    return out


def log(m):
    print(f"{time.strftime('%H:%M:%S')} - {m}", flush=True)


def main() -> None:
    log("loading cusip -> issuer from the curated holdings (heavy, once)...")
    iss = pd.read_csv(CURATED / "holdings.csv.gz", usecols=["instrument_id", "issuer"])
    # dominant issuer string per cusip (filers typo; majority vote)
    iss = (iss.groupby(["instrument_id", "issuer"]).size().rename("k").reset_index()
              .sort_values("k", ascending=False).drop_duplicates("instrument_id"))
    iss["nname"] = iss["issuer"].map(norm_name)

    sp = sp500_names()
    sp["nname"] = sp["name"].map(norm_name)

    # ambiguity: a normalised name spanning >1 ticker (share classes) or the
    # same name on >1 cusip with conflicting matches -> dropped, counted
    amb_tickers = sp["nname"].value_counts()
    amb = set(amb_tickers[amb_tickers > 1].index)
    sp_clean = sp[~sp["nname"].isin(amb) & (sp["nname"].str.len() > 2)]

    m = iss.merge(sp_clean[["nname", "ticker"]], on="nname", how="inner")
    dup_cusips = m["ticker"].value_counts()
    multi = set(dup_cusips[dup_cusips > 1].index)
    # one ticker matched by several cusips: keep the cusip with the most
    # filer votes (the live one); the others are old/odd lines
    m = m.sort_values("k", ascending=False).drop_duplicates("ticker")
    cmap = m.set_index("instrument_id")["ticker"]
    log(f"map: {len(cmap)} cusip->ticker | dropped ambiguous names: {len(amb)} "
        f"| multi-cusip tickers resolved by vote: {len(multi)}")

    panel = pd.read_csv(DATA / "imbalance_panel.csv.gz", parse_dates=["period_end"])
    panel["ticker"] = panel["instrument_id"].map(cmap)
    mapped = panel.dropna(subset=["ticker"]).copy()
    cov_rows = mapped.groupby("period_end").size()
    log(f"panel mapped: {len(mapped):,} of {len(panel):,} stock-quarters "
        f"({len(mapped) / len(panel):.1%}); ~{cov_rows.median():.0f} S&P names/quarter")

    mapped["avail_date"] = mapped["period_end"] + pd.Timedelta(days=AVAIL_DAYS)
    out = mapped[["period_end", "avail_date", "ticker", "ti", "vi", "n_active"]]
    out.to_csv(DATA / "cm_signal_quarters.csv", index=False)
    log(f"wrote {DATA / 'cm_signal_quarters.csv'} ({len(out):,} rows)")


if __name__ == "__main__":
    main()
