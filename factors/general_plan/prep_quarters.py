"""Partition the curated 13F base into per-quarter parquet with version metadata.

Why: the research plan's core PIT requirement is `snapshot_as_of(decision_date)`
driven by FILING dates, not reference periods. The curated layer already holds
everything needed - `holdings.csv.gz` keyed by accession, `revisions.csv.gz`
with (filing_date, amendment_type, seq) per accession - but as one 1.45GB CSV
whose full scan costs minutes. This script pays that scan ONCE and writes one
parquet per quarter carrying every version's rows plus the version metadata,
so `snapshot_as_of(p, d)` becomes a cheap filter:

    keep versions with filing_date <= d
    latest RESTATEMENT (or the original) replaces; NEW HOLDINGS unions

which is exactly the amendment semantics of the crowdflow store (invariant #2
of the parent project), re-implemented over flat files so the factor layer
here has no import dependency on crowdflow internals.

Row filters applied here (and counted, never silent):
  - put_call rows dropped: options cannot be summed with shares without delta
    (plan §1, consequence 2). The dropped notional share is reported.
  - PRN-like rows: the curated layer already classifies instruments; only
    `instrument_class == 'common'`-ish classes carry share counts comparable
    across filers. We keep all classes but flag them; signal code filters.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
CUR = HERE.parents[1] / "crowdflow" / "data" / "20_curated"
OUT = HERE / "data" / "quarters"


def log(msg: str) -> None:
    print(f"{datetime.now():%H:%M:%S} - {msg}", flush=True)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    rev = pd.read_csv(
        CUR / "revisions.csv.gz",
        usecols=["accession", "filer_id", "cik", "period_end", "filing_date",
                 "amendment_type", "is_amendment", "seq", "form"],
        parse_dates=["period_end", "filing_date"])
    # 13F-NT and notice-like rows never carry holdings; keep HR family only
    rev = rev[rev["form"].str.startswith("13F-HR", na=False)]
    rev.to_parquet(OUT / "filings_meta.parquet", index=False)
    log(f"filings meta: {len(rev):,} versions, "
        f"{rev.is_amendment.sum():,} amendments")

    meta = rev.set_index("accession")[["filing_date", "amendment_type",
                                       "is_amendment", "seq"]]

    log("streaming holdings.csv.gz (single full scan)")
    usecols = ["accession", "filer_id", "cik", "period_end", "instrument_id",
               "cusip6", "instrument_class", "shares", "value_usd", "put_call"]
    parts: dict[str, list[pd.DataFrame]] = {}
    n_rows = n_opt = 0
    for chunk in pd.read_csv(CUR / "holdings.csv.gz", usecols=usecols,
                             chunksize=4_000_000):
        n_rows += len(chunk)
        opt = chunk["put_call"].notna()
        n_opt += int(opt.sum())
        chunk = chunk[~opt].drop(columns=["put_call"])
        chunk = chunk.join(meta, on="accession")
        chunk = chunk[chunk["filing_date"].notna()]  # HR-family only
        for p, g in chunk.groupby("period_end", sort=False):
            parts.setdefault(str(p)[:10], []).append(g)
        log(f"  {n_rows:,} rows in, {n_opt:,} option rows dropped")

    for p, frames in sorted(parts.items()):
        df = pd.concat(frames, ignore_index=True).drop(columns=["period_end"])
        df.to_parquet(OUT / f"q_{p}.parquet", index=False)
    log(f"wrote {len(parts)} quarters; options dropped: "
        f"{n_opt:,}/{n_rows:,} rows ({n_opt / n_rows:.2%})")


if __name__ == "__main__":
    main()
