"""Shared machinery for the nowcasting study (plano_nowcasting_13F).

Everything here works in QUANTITY units (shares, or the IO ratio
shares_held / shares_outstanding), never in value. That is checklist item
"Unidades" of the plan (§9): value units mix price and quantity, and a
nowcaster evaluated in value units is a return calculator with extra steps -
the field's failure mode number one (§2). The IO ratio has a second virtue:
splits scale numerator and denominator identically, so ratio deltas are
split-invariant with no adjustment machinery at all.

Key objects
-----------
io_panel(p, d)         stock-level IO for quarter p as known at date d,
                       split by filers that HAVE filed p by d vs the rest -
                       the ragged edge made explicit.
ndcg_at_k              the metric of the temporal-graph benchmark (§3.6),
                       reimplemented so persistence and EMA heuristics can
                       be scored on OUR panel against the published numbers
                       (persistence 0.8891, EMA 0.8882, best ML 0.9127).
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
GP = HERE.parent / "general_plan"
sys.path.insert(0, str(GP))

import panel as pn  # noqa: E402  (general_plan snapshot machinery)


def log(msg: str) -> None:
    print(f"{datetime.now():%H:%M:%S} - {msg}", flush=True)


# --------------------------------------------------------------------------- #
# stock-level IO with the ragged edge explicit
# --------------------------------------------------------------------------- #

def filed_sets(meta: pd.DataFrame, period: pd.Timestamp,
               d: pd.Timestamp) -> set:
    """Filers whose ORIGINAL filing for `period` is public by d."""
    m = meta[(meta["period_end"] == period) & (~meta["is_amendment"])]
    return set(m.loc[m["filing_date"] <= d, "filer_id"])


def io_by_stock(snap: pd.DataFrame, filers: set | None = None) -> pd.Series:
    """Aggregate shares held per instrument, optionally restricted to a
    filer subset. Units: shares (caller divides by shares outstanding)."""
    s = snap if filers is None else snap[snap["filer_id"].isin(filers)]
    return s.groupby("instrument_id")["shares"].sum()


def weights_matrix(snap: pd.DataFrame, managers: list[str]) -> pd.DataFrame:
    """Manager x instrument portfolio-weight matrix (value weights within
    each manager's book) - the object the NDCG benchmark ranks."""
    s = snap[snap["filer_id"].isin(managers)].copy()
    s["w"] = s["value_usd"] / s.groupby("filer_id")["value_usd"].transform("sum")
    return s.pivot_table(index="filer_id", columns="instrument_id",
                         values="w", aggfunc="sum")


# --------------------------------------------------------------------------- #
# metrics
# --------------------------------------------------------------------------- #

def r2_oos(actual: pd.Series, pred: pd.Series) -> float:
    """Out-of-sample R^2 against the zero forecast (the convention of the
    Barardehi et al. horse race: 1 - SSE(pred)/SSE(0))."""
    df = pd.concat([actual.rename("a"), pred.rename("p")], axis=1).dropna()
    if len(df) < 30:
        return np.nan
    sse = ((df["a"] - df["p"]) ** 2).sum()
    sst = (df["a"] ** 2).sum()
    return float(1 - sse / sst) if sst > 0 else np.nan


def hit_rate(actual: pd.Series, pred: pd.Series) -> float:
    df = pd.concat([actual.rename("a"), pred.rename("p")], axis=1).dropna()
    df = df[(df["a"] != 0) & (df["p"] != 0)]
    if len(df) < 30:
        return np.nan
    return float((np.sign(df["a"]) == np.sign(df["p"])).mean())


def rank_ic(actual: pd.Series, pred: pd.Series) -> float:
    from scipy import stats as sps
    df = pd.concat([actual.rename("a"), pred.rename("p")], axis=1).dropna()
    if len(df) < 30:
        return np.nan
    return float(sps.spearmanr(df["a"], df["p"])[0])


def ndcg_at_k(true_w: pd.Series, pred_w: pd.Series, k: int = 10) -> float:
    """NDCG@k: rank instruments by predicted weight, score by true weight
    (graded relevance), normalise by the ideal ranking. The §3.6 metric."""
    t = true_w.fillna(0.0)
    p = pred_w.reindex(t.index).fillna(0.0)
    if t.sum() <= 0:
        return np.nan
    top_pred = p.sort_values(ascending=False).index[:k]
    top_true = t.sort_values(ascending=False).index[:k]
    kk = min(len(top_pred), len(top_true))
    if kk == 0:
        return np.nan
    disc = 1.0 / np.log2(np.arange(2, kk + 2))
    dcg = float((t.reindex(top_pred[:kk]).fillna(0.0).values * disc).sum())
    idcg = float((t.reindex(top_true[:kk]).values * disc).sum())
    return dcg / idcg if idcg > 0 else np.nan
