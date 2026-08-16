"""Point-in-time snapshots and the endogenous filer universe.

`snapshot_as_of(period, decision_date)` is the ONLY way holdings reach the
signal layer in this package - the same single-door discipline as the parent
project's bitemporal store (its invariant #1), re-implemented over the
per-quarter parquet written by prep_quarters.py so this package stands alone.

Amendment semantics (plan §2.2, crowdflow invariant #2):
  - among versions with filing_date <= d, the latest RESTATEMENT (or the
    original when no restatement is visible yet) REPLACES the filer's table;
  - NEW HOLDINGS amendments visible by d are UNIONED on top (they are lapsed
    confidential-treatment positions, additive by definition);
  - a filer whose first visible version arrives after d simply does not
    exist at d. No 45-day assumption anywhere: composition at D+30 is
    genuinely thinner than at D+60, and that difference is the experiment.

The endogenous filer universe (plan §2.6) is computed from 13F data alone,
each cut with an economic reason stated in `universe_mask`:
    15 <= n_positions <= 200      not an equity picker / quasi-indexer
    HHI > cross-sectional median  benchmark huggers carry no conviction
    turnover_4q > 33rd pct        dedicated long-horizon books do not predict
                                  returns (Yan & Zhang 2009)
    AUM_13F > $250M               below this, books are noise and minimums
    history >= 8 quarters         no basis to measure behaviour
All thresholds are computed cross-sectionally AT the decision date - never
from the full sample (that would be the normalisation lookahead of plan §5.1).
"""
from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
QDIR = HERE / "data" / "quarters"


def log(msg: str) -> None:
    print(f"{datetime.now():%H:%M:%S} - {msg}", flush=True)


def quarters() -> list[pd.Timestamp]:
    return sorted(pd.Timestamp(p.stem[2:]) for p in QDIR.glob("q_*.parquet"))


@lru_cache(maxsize=6)
def _load_quarter(pstr: str) -> pd.DataFrame:
    return pd.read_parquet(QDIR / f"q_{pstr}.parquet")


def snapshot_as_of(period: pd.Timestamp, decision_date: pd.Timestamp,
                   equity_only: bool = True) -> pd.DataFrame:
    """Holdings for `period` as publicly known at `decision_date`.

    Returns one row per (filer_id, instrument_id) with shares and value_usd.
    """
    df = _load_quarter(str(period)[:10])
    df = df[df["filing_date"] <= decision_date]
    if df.empty:
        return df.assign(shares=[], value_usd=[])
    if equity_only:
        # options are already dropped at prep; keep share-denominated classes
        df = df[~df["instrument_class"].isin(["debt", "principal"])]

    # latest replacing version per filer: original or RESTATEMENT
    # (missing amendment_type on an amendment = restatement, the conservative
    # reading - crowdflow invariant: cover page decides, absence replaces)
    is_new = df["is_amendment"] & (df["amendment_type"] == "NEW HOLDINGS")
    base = df[~is_new]
    keep_seq = base.groupby("filer_id")["seq"].transform("max")
    out = base[base["seq"] == keep_seq]
    add = df[is_new]
    if len(add):
        out = pd.concat([out, add], ignore_index=True)
    out = (out.groupby(["filer_id", "instrument_id"], as_index=False)
              .agg(shares=("shares", "sum"), value_usd=("value_usd", "sum"),
                   cusip6=("cusip6", "first")))
    return out


def filer_stats(snap: pd.DataFrame) -> pd.DataFrame:
    """Per-filer book characteristics used by the endogenous universe."""
    g = snap.groupby("filer_id")["value_usd"]
    stats = pd.DataFrame({"aum": g.sum(), "n_pos": g.size()})
    w2 = snap.assign(w2=(snap["value_usd"] /
                         snap.groupby("filer_id")["value_usd"].transform("sum")) ** 2)
    stats["hhi"] = w2.groupby("filer_id")["w2"].sum()
    # normalised HHI in [0,1]: (HHI - 1/N) / (1 - 1/N), degenerate N=1 -> 1
    n = stats["n_pos"].clip(lower=2)
    stats["hhi_norm"] = ((stats["hhi"] - 1 / n) / (1 - 1 / n)).clip(0, 1)
    return stats


def turnover(cur: pd.DataFrame, prev: pd.DataFrame) -> pd.Series:
    """One-quarter name-level turnover per filer: value of entries + exits
    over average book. Coarse by design (13F hides intra-quarter round
    trips - Puckett & Yan 2011), but it separates dedicated holders from
    active traders, which is all the universe filter needs."""
    m = cur.merge(prev, on=["filer_id", "instrument_id"], how="outer",
                  suffixes=("_c", "_p"))
    m[["value_usd_c", "value_usd_p"]] = m[["value_usd_c", "value_usd_p"]].fillna(0.0)
    m["traded"] = (m["value_usd_c"] - m["value_usd_p"]).abs()
    g = m.groupby("filer_id")
    return (g["traded"].sum() / g[["value_usd_c", "value_usd_p"]].sum()
            .sum(axis=1).replace(0, np.nan) * 2).rename("turnover")


def universe_mask(stats: pd.DataFrame, turn4: pd.Series,
                  history: pd.Series) -> pd.Series:
    """Boolean: filer belongs to the endogenous universe at this date."""
    hhi_med = stats["hhi_norm"].median()
    turn_p33 = turn4.quantile(1 / 3)
    ok = (stats["n_pos"].between(15, 200)
          & (stats["hhi_norm"] > hhi_med)
          & (stats["aum"] > 250e6)
          & (turn4.reindex(stats.index) > turn_p33)
          & (history.reindex(stats.index) >= 8))
    return ok.fillna(False)
