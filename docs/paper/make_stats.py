"""Paper data prep R2-R4: filing-delay statistics (justifies the D+45
clock with numbers), ETF share of book value over time, and manager
count over time.

    python make_stats.py

Outputs -> docs/paper/data/: filing_delays.csv (+summary printed),
etf_share.csv, manager_count.csv.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "factors" / "general_plan"))

import panel as pn                                  # noqa: E402

OUT = Path(__file__).resolve().parent / "data"
OUT.mkdir(parents=True, exist_ok=True)


def main() -> None:
    meta = pd.read_parquet(pn.QDIR / "filings_meta.parquet")
    orig = meta[~meta["is_amendment"]].copy()
    orig["delay"] = (orig["filing_date"] - orig["period_end"]).dt.days
    orig = orig[(orig["delay"] >= 0) & (orig["delay"] <= 400)]

    d = orig["delay"]
    summ = {
        "n_filings": len(d),
        "median_days": float(d.median()),
        "p90": float(d.quantile(0.90)),
        "p99": float(d.quantile(0.99)),
        "max": float(d.max()),
        "pct_by_d45": float((d <= 45).mean()),
        "pct_by_d40": float((d <= 40).mean()),
        "pct_by_d60": float((d <= 60).mean()),
        "pct_after_deadline": float((d > 45).mean()),
    }
    print("filing delays:", {k: round(v, 3) for k, v in summ.items()})
    d.to_frame("delay_days").to_csv(OUT / "filing_delays.csv", index=False)
    pd.Series(summ).to_csv(OUT / "filing_delay_summary.csv")

    # late-filer persistence: share of filers late in consecutive quarters
    orig["late"] = orig["delay"] > 45
    lt = orig.pivot_table(index="filer_id", columns="period_end",
                          values="late", aggfunc="first")
    both = (lt & lt.shift(axis=1)).sum().sum()
    base = (lt.shift(axis=1) == True).sum().sum()      # noqa: E712
    print(f"late-again given late: {both / max(base, 1):.2f}")

    etf = pd.read_csv(ROOT / "factors" / "ETF_strat" / "data"
                      / "etf_universe_flags.csv",
                      usecols=["instrument_id", "is_etf"])
    etf_ids = set(etf.loc[etf["is_etf"] == True, "instrument_id"])  # noqa: E712

    rows = []
    for q in pn.quarters():
        try:
            snap = pn.snapshot_as_of(q, q + pd.Timedelta(days=75))
        except Exception:
            continue
        if len(snap) < 1000:
            continue
        tot = snap["value_usd"].sum()
        etf_v = snap.loc[snap["instrument_id"].isin(etf_ids),
                         "value_usd"].sum()
        rows.append({"period": q,
                     "n_filers": snap["filer_id"].nunique(),
                     "total_value_usd": tot,
                     "etf_share": etf_v / tot if tot > 0 else np.nan})
        print(q.date(), rows[-1]["n_filers"], f"{rows[-1]['etf_share']:.3f}")
    df = pd.DataFrame(rows)
    df[["period", "etf_share"]].to_csv(OUT / "etf_share.csv", index=False)
    df[["period", "n_filers", "total_value_usd"]].to_csv(
        OUT / "manager_count.csv", index=False)
    print("done ->", OUT)


if __name__ == "__main__":
    main()
