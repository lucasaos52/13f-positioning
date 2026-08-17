"""Wide stock universe for the paper replication: all US listings, not S&P.

The paper runs on ~5,000 securities per quarter — essentially everything
institutions hold. This prep builds the widest map Yahoo can serve:

1. official Nasdaq symbol directories (nasdaqlisted.txt + otherlisted.txt,
   ~10k current listings) -> ticker + security name, ETFs and test issues
   dropped by their own flags;
2. cusip -> dominant issuer name from the curated 13F holdings;
3. normalised-name exact match between the two. Ambiguous names (one name,
   several tickers or CUSIPs) are dropped and counted, never guessed.

Survivorship, stated: the directory lists TODAY's tickers, so delisted
names never enter — coverage is necessarily worse than the paper's and the
bias favours the follow side. The comparison section must keep saying so.

Outputs: data/cm_map_wide.csv (cusip,ticker), data/cm_signal_wide.csv
(the mapped signal file, same schema as cm_signal_quarters.csv).
"""
from __future__ import annotations

import io
import re
import time
from pathlib import Path

import pandas as pd
import requests

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
DATA.mkdir(parents=True, exist_ok=True)   # fresh clones have no data/
CURATED = HERE.parents[0] / "crowdflow" / "data" / "20_curated"
AVAIL_DAYS = 71

_STOP = {
    "INC", "INCORPORATED", "CORP", "CORPORATION", "CO", "COMPANY", "PLC", "LTD",
    "LIMITED", "LP", "LLC", "SA", "NV", "AG", "THE", "GROUP", "HOLDINGS",
    "HOLDING", "COS", "COMPANIES", "TRUST", "CL", "CLASS", "A", "B", "C",
    "COM", "NEW", "DEL", "&", "ORDINARY", "SHARES", "SHARE", "COMMON", "STOCK",
    "DEPOSITARY", "ADS", "ADR", "AMERICAN", "ETF",
}
_BAD_NAME = re.compile(
    r"WARRANT|RIGHTS?\b|UNITS?\b|PREFERRED|PFD|NOTES?\b|DEBENTURE|%|DUE\b|BOND",
    re.IGNORECASE,
)


def norm_name(s: str) -> str:
    s = re.sub(r"[^A-Za-z0-9 ]", " ", str(s).upper())
    return " ".join(t for t in s.split() if t not in _STOP)


def log(m):
    print(f"{time.strftime('%H:%M:%S')} - {m}", flush=True)


def nasdaq_directory() -> pd.DataFrame:
    cache = DATA / "us_listings.csv"
    if cache.exists():
        return pd.read_csv(cache)
    frames = []
    for url, sym_col, name_col, etf_col, extra in [
        ("https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
         "Symbol", "Security Name", "ETF", "Test Issue"),
        ("https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt",
         "ACT Symbol", "Security Name", "ETF", "Test Issue"),
    ]:
        txt = requests.get(url, timeout=30,
                           headers={"User-Agent": "research/0.1"}).text
        df = pd.read_csv(io.StringIO(txt), sep="|")
        df = df[df[etf_col].astype(str).str.upper().ne("Y")
                & df[extra].astype(str).str.upper().ne("Y")]
        frames.append(pd.DataFrame({
            "ticker": df[sym_col].astype(str).str.strip(),
            "name": df[name_col].astype(str),
        }))
    out = pd.concat(frames, ignore_index=True)
    out = out[~out["name"].str.contains(_BAD_NAME, na=False)]
    out = out[~out["ticker"].str.contains(r"[\.\$\^]", na=False)]  # test/class oddities
    out["ticker"] = out["ticker"].str.replace(".", "-", regex=False)
    out = out.drop_duplicates("ticker")
    out.to_csv(cache, index=False)
    return out


def main() -> None:
    listings = nasdaq_directory()
    log(f"US listings after ETF/warrant/test filters: {len(listings):,}")

    cache = DATA / "cusip_issuer.csv.gz"
    if cache.exists():
        iss = pd.read_csv(cache)
    else:
        log("loading cusip -> issuer from curated holdings (heavy, once)...")
        iss = pd.read_csv(CURATED / "holdings.csv.gz", usecols=["instrument_id", "issuer"])
        iss = (iss.groupby(["instrument_id", "issuer"]).size().rename("k").reset_index()
               .sort_values("k", ascending=False).drop_duplicates("instrument_id"))
        iss.to_csv(cache, index=False)
    iss["nname"] = iss["issuer"].map(norm_name)
    listings["nname"] = listings["name"].map(norm_name)

    amb = listings["nname"].value_counts()
    listings_clean = listings[~listings["nname"].isin(set(amb[amb > 1].index))
                              & (listings["nname"].str.len() > 2)]
    m = iss.merge(listings_clean[["nname", "ticker"]], on="nname", how="inner")
    m = m.sort_values("k", ascending=False).drop_duplicates("ticker")
    m = m.drop_duplicates("instrument_id")
    cmap = m.set_index("instrument_id")["ticker"]
    log(f"wide map: {len(cmap):,} cusip -> ticker "
        f"(ambiguous names dropped: {int((amb > 1).sum()):,})")
    cmap.rename("ticker").to_csv(DATA / "cm_map_wide.csv")

    # legacy tail: maps the early imbalance-replication signal file if
    # its intermediate exists (not part of the bootstrap path; fresh
    # clones skip it - the crosswalk above is already written)
    ip = DATA / "imbalance_panel.csv.gz"
    if not ip.exists():
        log("imbalance_panel.csv.gz not present - legacy signal "
            "mapping skipped (crosswalk already written)")
        return
    panel = pd.read_csv(ip, parse_dates=["period_end"])
    panel["ticker"] = panel["instrument_id"].map(cmap)
    mapped = panel.dropna(subset=["ticker"]).copy()
    per_q = mapped.groupby("period_end").size()
    log(f"signal mapped: {len(mapped):,} of {len(panel):,} stock-quarters "
        f"({len(mapped) / len(panel):.1%}); median {per_q.median():.0f} names/quarter "
        f"(paper: ~5,000)")
    mapped["avail_date"] = mapped["period_end"] + pd.Timedelta(days=AVAIL_DAYS)
    mapped[["period_end", "avail_date", "ticker", "ti", "vi", "n_active"]].to_csv(
        DATA / "cm_signal_wide.csv", index=False)
    log("wrote cm_signal_wide.csv")


if __name__ == "__main__":
    main()
