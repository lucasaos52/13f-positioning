"""Event-driven quintile backtest for quarterly 13F signals.

Clock (plan §5.1): decisions happen at period_end + L calendar days for
L in {30, 45, 60} - and the SNAPSHOT at each decision date contains only
filings with filed_date <= decision date. So D+30 books are genuinely
thinner and skewed to fast filers (banks, quasi-indexers), D+60 has nearly
everyone including the strategic late filers (hedge funds). Comparing the
three is the plan's cheap, high-information experiment: alpha appearing
only at D+60 implicates the late filers and supports the skill story;
alpha already at D+30 implicates the passives and contradicts it.

Portfolios: quintile sort on the transformed signal, Q5-Q1 spread, held
from the first trading day after the decision date to the next formation.
EW and VW (mktcap) both reported - the gap between them is the microcap
dependence diagnostic. Returns accrue daily from the adjusted panel;
positions are constant-weight within the holding period (the simulator
convention of the reference multifactor; drift-vs-reset makes little
difference at quarterly holding and is not the object of study here).

Costs: a per-side bps ladder {0, 5, 10, 20, 50} applied to turnover, plus
the single most honest number: the BREAKEVEN cost per side at which the
net spread hits zero. No square-root impact model here - the parent
project has one; this engine is for factor comparison where a transparent
linear ladder is easier to defend than a calibrated-looking guess.

Metrics: mean spread, NW(4) t-stat, annualised Sharpe, IC (Spearman) at
formation vs next-quarter return, IC decay at 1/3/6/12 months,
monotonicity across quintiles (fraction of adjacent pairs ordered), and
per-quintile means - because a big spread with scrambled middle quintiles
means two names carry the result (plan §5.5).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats as sps


def nw_tstat(x: pd.Series, lags: int = 4) -> float:
    """Newey-West t-stat of the mean (quarterly overlap-robust)."""
    x = x.dropna().values
    n = len(x)
    if n < 8:
        return np.nan
    e = x - x.mean()
    g0 = float(e @ e) / n
    s = g0
    for k in range(1, min(lags, n - 1) + 1):
        gk = float(e[k:] @ e[:-k]) / n
        s += 2 * (1 - k / (lags + 1)) * gk
    se = np.sqrt(s / n)
    return float(x.mean() / se) if se > 0 else np.nan


def forward_return(cum: pd.DataFrame, dates: pd.DatetimeIndex,
                   start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    """Sum of daily returns (arithmetic, delisting-free by construction of
    the Yahoo panel - stated limitation) from first trading day AFTER
    `start` through `end`."""
    i0 = dates.searchsorted(start, side="right")
    i1 = dates.searchsorted(end, side="right") - 1
    if i0 >= len(dates) or i1 <= i0:
        return pd.Series(dtype=float)
    return cum.iloc[i1] - cum.iloc[i0 - 1] if i0 > 0 else cum.iloc[i1]


def quintile_event(signal: pd.Series, fwd: pd.Series,
                   mktcap: pd.Series | None) -> dict:
    """One formation event: quintile means EW and VW, spread, IC."""
    df = pd.concat([signal.rename("sig"), fwd.rename("fwd")], axis=1).dropna()
    if len(df) < 50:
        return {}
    df["q"] = pd.qcut(df["sig"], 5, labels=False, duplicates="drop") + 1
    if df["q"].nunique() < 5:
        return {}
    ew = df.groupby("q")["fwd"].mean()
    out = {f"ew_q{int(q)}": v for q, v in ew.items()}
    out["ew_spread"] = ew.get(5, np.nan) - ew.get(1, np.nan)
    if mktcap is not None:
        df["mc"] = mktcap.reindex(df.index)
        vw = df.dropna(subset=["mc"]).groupby("q").apply(
            lambda g: np.average(g["fwd"], weights=g["mc"]))
        out["vw_spread"] = vw.get(5, np.nan) - vw.get(1, np.nan)
    out["ic"] = sps.spearmanr(df["sig"], df["fwd"])[0]
    out["n"] = len(df)
    # one-sided turnover needs the previous membership - filled by caller
    out["_members_q5"] = set(df.index[df["q"] == 5])
    out["_members_q1"] = set(df.index[df["q"] == 1])
    return out


def summarise(events: pd.DataFrame) -> dict:
    """Aggregate event table -> headline metrics."""
    res = {}
    for leg in ("ew_spread", "vw_spread"):
        if leg not in events:
            continue
        s = events[leg]
        res[f"{leg}_mean_q"] = s.mean()
        res[f"{leg}_t_nw"] = nw_tstat(s)
        res[f"{leg}_sharpe"] = s.mean() / s.std() * np.sqrt(4) if s.std() > 0 else np.nan
    res["ic_mean"] = events["ic"].mean()
    res["ic_ir"] = events["ic"].mean() / events["ic"].std() if events["ic"].std() > 0 else np.nan
    res["ic_pos_frac"] = (events["ic"] > 0).mean()
    qcols = [c for c in events.columns if c.startswith("ew_q")]
    if qcols:
        means = events[qcols].mean()
        order = [means.get(f"ew_q{i}", np.nan) for i in range(1, 6)]
        pairs = [(a, b) for a, b in zip(order[:-1], order[1:])
                 if not (np.isnan(a) or np.isnan(b))]
        res["monotonicity"] = (np.mean([b >= a for a, b in pairs])
                               if pairs else np.nan)
        for i in range(1, 6):
            res[f"q{i}_mean"] = means.get(f"ew_q{i}", np.nan)
    # turnover and cost ladder
    if "turnover_1s" in events:
        to = events["turnover_1s"].mean()
        res["turnover_1s"] = to
        gross = res.get("ew_spread_mean_q", np.nan)
        for bps in (5, 10, 20, 50):
            # cost hits both legs' one-sided turnover, twice per side change
            res[f"net_{bps}bps"] = gross - 4 * to * bps / 1e4
        res["breakeven_bps"] = (gross / (4 * to) * 1e4) if to and to > 0 else np.nan
    res["n_events"] = len(events)
    return res
