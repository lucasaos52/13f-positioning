"""Point-in-time adapter for the repository's per-quarter 13F parquet store."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def snapshot_as_of(
    quarter_file: str | Path,
    decision_date: str | pd.Timestamp,
) -> pd.DataFrame:
    """Materialize filings visible on ``decision_date`` with amendment semantics.

    Replacement happens by registrant CIK, never by economic ``filer_id``:
    family members can file separate, simultaneously valid books.  ``NEW
    HOLDINGS`` amendments are additive; all other amendments replace.  The
    upstream parquet has day-level filing timestamps, so same-day cutoff
    precision is unavailable here and is disclosed in the research report.
    """

    path = Path(quarter_file)
    period = pd.Timestamp(path.stem.removeprefix("q_"))
    df = pd.read_parquet(path)
    df["filing_date"] = pd.to_datetime(df["filing_date"])
    df = df[df["filing_date"] <= pd.Timestamp(decision_date)].copy()
    if df.empty:
        return df.assign(period_end=pd.Series(dtype="datetime64[ns]"))

    vkey = "cik" if "cik" in df else "filer_id"
    is_new = df["is_amendment"] & df["amendment_type"].eq("NEW HOLDINGS")
    base = df[~is_new]
    last_replace = base.groupby(vkey)["seq"].max().rename("last_replace")
    keep_base = base[base["seq"].eq(base[vkey].map(last_replace))]
    # A later restatement replaces earlier additive amendments too. Only NEW
    # HOLDINGS versions after the last replacing version survive the fold.
    additive = df[is_new]
    additive = additive[
        additive["seq"].gt(additive[vkey].map(last_replace).fillna(-np.inf))
    ]
    visible = pd.concat([keep_base, additive], ignore_index=True)
    # A NEW HOLDINGS amendment can repeat an already visible security.  Later
    # versions win within the CIK; siblings then sum at the filer family level.
    visible = visible.sort_values("seq").drop_duplicates(
        [vkey, "instrument_id"], keep="last"
    )
    group_cols = ["filer_id", "instrument_id"]
    out = visible.groupby(group_cols, as_index=False).agg(
        shares=("shares", "sum"),
        value_usd=("value_usd", "sum"),
        instrument_class=("instrument_class", "first"),
        cusip6=("cusip6", "first"),
    )
    out["period_end"] = period
    out["knowledge_date"] = pd.Timestamp(decision_date)
    return out


def manager_turnover(current: pd.DataFrame, previous: pd.DataFrame) -> pd.Series:
    """Balanced quarterly turnover: min(buys, sells) / average 13F book."""

    keys = ["filer_id", "instrument_id"]
    x = current[keys + ["value_usd"]].merge(
        previous[keys + ["value_usd"]], on=keys, how="outer", suffixes=("_cur", "_prev")
    ).fillna({"value_usd_cur": 0.0, "value_usd_prev": 0.0})
    x["delta"] = x["value_usd_cur"] - x["value_usd_prev"]
    by = x.groupby("filer_id")
    buys = by["delta"].apply(lambda s: s.clip(lower=0.0).sum())
    sells = by["delta"].apply(lambda s: -s.clip(upper=0.0).sum())
    books = by[["value_usd_cur", "value_usd_prev"]].sum()
    denominator = (books["value_usd_cur"] + books["value_usd_prev"]) / 2.0
    return pd.concat([buys, sells], axis=1).min(axis=1) / denominator.replace(0.0, np.nan)
