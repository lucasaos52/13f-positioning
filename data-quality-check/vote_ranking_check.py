"""Data-quality check: does purging ETF lines from books change WHO the
new_conviction census votes for?

    python vote_ranking_check.py [quarter, default 2024-12-31]

The mechanism check behind champion_noetf's null result (originally run
inline on 2026-08-16). For one quarter it builds the conviction vote set
twice - with and without ETF lines in the book weights/thresholds - and
measures:
  - individual votes changed            (then: 18.5% - a LOT at manager level)
  - per-stock vote-count rank corr      (then: 0.974)
  - top-100 overlap                     (then: 97/100)
Reading: the purge frees ~17% more stock votes (bets hidden behind SPY)
but they spread near-proportionally across the same names - a monotone
transformation, invisible to a rank-based signal. "Innocuous
contamination": uniform bias does not distort a ranking (contrast with
untreated splits = differential distortion, which required the
modal-atom detector in general_predictive_signals).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "factors"))
sys.path.insert(0, str(ROOT / "factors" / "general_plan"))

import panel as pn                                  # noqa: E402
from run_all import load_market                     # noqa: E402


def main(qstr: str = "2024-12-31") -> None:
    etf = pd.read_csv(ROOT / "factors" / "ETF_strat" / "data"
                      / "etf_universe_flags.csv",
                      usecols=["instrument_id", "is_etf"])
    etf_set = set(etf.loc[etf["is_etf"] == True, "instrument_id"])  # noqa: E712
    cmap, mdta = load_market()
    p = pd.Timestamp(qstr)
    p1 = pn.quarters()[pn.quarters().index(p) - 1]
    cur = pn.snapshot_as_of(p, p + pd.Timedelta(days=45))
    prev = pn.snapshot_as_of(p1, p + pd.Timedelta(days=45))
    prev_sh = prev.groupby(["filer_id", "instrument_id"])["shares"].sum()

    def votes(book):
        b = book.copy()
        tot = b.groupby("filer_id")["value_usd"].transform("sum")
        b["w"] = b["value_usd"] / tot.replace(0, np.nan)
        b["thr"] = b.groupby("filer_id")["w"].transform(
            lambda s: s.quantile(0.9))
        key = pd.MultiIndex.from_frame(b[["filer_id", "instrument_id"]])
        shp = pd.Series(prev_sh.reindex(key).values, index=b.index)
        grew = shp.isna() | (b["shares"] >= 1.25 * shp)
        v = b[(b["w"] >= b["thr"]) & grew]
        v = v[v["instrument_id"].map(cmap).notna()]
        return set(map(tuple, v[["filer_id", "instrument_id"]].values))

    vA = votes(cur)
    vB = votes(cur[~cur["instrument_id"].isin(etf_set)])
    inter = len(vA & vB)
    print(f"votes with ETFs: {len(vA)} | without: {len(vB)} | "
          f"identical: {inter}")
    print(f"fraction of votes changed: {1 - inter / max(len(vA | vB), 1):.1%}")
    nc_A = pd.Series([x[1] for x in vA]).value_counts()
    nc_B = pd.Series([x[1] for x in vB]).value_counts()
    cc = pd.concat([nc_A, nc_B], axis=1).fillna(0)
    print(f"per-stock vote-count rank corr (A vs B): "
          f"{cc.corr(method='spearman').iloc[0, 1]:.4f}")
    top = set(nc_A.nlargest(100).index) & set(nc_B.nlargest(100).index)
    print(f"top-100 overlap: {len(top)}/100")


if __name__ == "__main__":
    main(*(sys.argv[1:2] or []))
