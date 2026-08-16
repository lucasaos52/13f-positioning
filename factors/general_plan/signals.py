"""Factor construction: dACWB (main), Days-ADV (second axis), three nulls.

Every factor here consumes ONLY:
  - two point-in-time snapshots (current and prior quarter, both materialised
    at the SAME decision date - so a quarter-on-quarter change never mixes
    what was known then with what is known now), and
  - market data indexed strictly before the decision date.

== dACWB - change in Active Conviction-Weighted Breadth (plan §3.9) ==

Two mechanisms, one number. When concentrated, active managers raise their
active exposure to a stock: (i) Miller/Chen-Hong-Stein - more priced-in
participants means less residual optimism in the price under short-sale
constraints; (ii) best-ideas - information concentrates in high-tilt
positions (Cohen-Polk-Silli). The signal is restricted to the endogenous
universe because the AGGREGATE institutional portfolio is the market
portfolio (Lewellen 2011) and cannot contain information.

Step 2 - the drift correction - is the step "most people forget": if the
manager did nothing and the stock rose 40%, its weight rose by itself.
    aw_hold = w_prev * (1+r_stock)/(1+r_portfolio) - w_mkt
    daw     = aw_now - aw_hold
Without it the factor collapses into lagged price momentum, detectable in
thirty seconds by asking for the momentum correlation (we report it in the
diagnostics precisely because of that).

== Days-ADV (plan §3 family C) ==

    DaysADV(j) = sum_i value_ij / dollarADV_j  - days of volume to unwind the
institutional position. The only crowding measure with strong documented
alpha (Brown-Howard-Lundblad; Chincarini-Lazo-Paz-Moneta), and mechanically
correlated with illiquidity - which is why the transform pipeline logs it
and neutralises size, and the memo must show the Amihud-adjusted step.

== Declared nulls (plan §3.9) ==

dIO (change in aggregate institutional ownership), dNumInst (change in the
number of holders), PSO (percent of shares outstanding). The literature
(Chincarini et al.; Chen-Hong-Stein's own robustness) predicts these carry
no alpha: reproducing that null in OUR pipeline is the cheapest available
evidence that the pipeline itself is sound. They run through the identical
transform and backtest code paths as the main factor - same winsorisation,
same neutralisation, same clock - or the comparison means nothing.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _weights(snap: pd.DataFrame) -> pd.DataFrame:
    """Within-filer portfolio weights from a snapshot."""
    out = snap.copy()
    out["w"] = out["value_usd"] / out.groupby("filer_id")["value_usd"].transform("sum")
    return out


def dacwb(cur: pd.DataFrame, prev: pd.DataFrame, elig: pd.Series,
          conv: pd.Series, w_mkt: pd.Series,
          stock_ret_q: pd.Series) -> pd.DataFrame:
    """dACWB per instrument, plus the un-drift-corrected variant for the
    momentum-contamination diagnostic.

    Parameters
    ----------
    cur, prev : snapshots at the SAME decision date (filer_id, instrument_id,
        value_usd), already restricted or not - `elig` does the restriction.
    elig : boolean per filer_id - the endogenous universe at this date.
    conv : conviction weight per filer_id, min(1, HHI_norm/HHI_median).
    w_mkt : market weight per instrument (mktcap share); instruments without
        market cap fall back to the aggregate-13F weight, flagged upstream.
    stock_ret_q : quarter total return per instrument (prior quarter end to
        current quarter end) - the drift correction's r_j.
    """
    keep = elig[elig].index
    if len(keep) == 0:
        return pd.DataFrame(columns=["dacwb", "dacwb_nodrift", "n_holders_elig"])
    c = _weights(cur[cur["filer_id"].isin(keep)])
    p = _weights(prev[prev["filer_id"].isin(keep)])

    m = c.merge(p, on=["filer_id", "instrument_id"], how="outer",
                suffixes=("", "_p"))
    m[["w", "w_p"]] = m[["w", "w_p"]].fillna(0.0)

    # drift: what the previous weight would be today with zero trading
    r_j = m["instrument_id"].map(stock_ret_q).fillna(0.0)
    # portfolio drift return: value-weighted average of r_j over prev book
    pr = (p.assign(r=p["instrument_id"].map(stock_ret_q).fillna(0.0))
            .groupby("filer_id").apply(lambda g: np.average(g["r"], weights=g["w"])
                                       if g["w"].sum() > 0 else 0.0))
    r_port = m["filer_id"].map(pr).fillna(0.0)
    wm = m["instrument_id"].map(w_mkt).fillna(0.0)

    aw_now = m["w"] - wm
    aw_hold = m["w_p"] * (1 + r_j) / (1 + r_port) - wm
    m["daw"] = aw_now - aw_hold
    m["daw_raw"] = m["w"] - m["w_p"]          # no drift correction (diagnostic)
    m["cv"] = m["filer_id"].map(conv).fillna(0.0)

    n_active = float(len(keep))
    g = m.groupby("instrument_id")
    out = pd.DataFrame({
        "dacwb": g.apply(lambda x: (x["cv"] * x["daw"]).sum()) / n_active,
        "dacwb_nodrift": g.apply(lambda x: (x["cv"] * x["daw_raw"]).sum()) / n_active,
        "n_holders_elig": g["filer_id"].nunique(),
    })
    return out


def days_adv(cur: pd.DataFrame, dollar_adv: pd.Series) -> pd.Series:
    """Days of ADV to liquidate the aggregate institutional position.
    Uses ALL filers deliberately: capacity is about total ownership pressure,
    not about the selected universe."""
    tot = cur.groupby("instrument_id")["value_usd"].sum()
    adv = tot.index.to_series().map(dollar_adv)
    return (tot / adv.replace(0, np.nan)).rename("days_adv")


def nulls(cur: pd.DataFrame, prev: pd.DataFrame,
          shares_out: pd.Series) -> pd.DataFrame:
    """dIO, dNumInst, PSO - the declared nulls, all-filers by construction
    (they are the naive aggregates the literature says are empty)."""
    cs = cur.groupby("instrument_id").agg(sh=("shares", "sum"),
                                          n=("filer_id", "nunique"))
    ps = prev.groupby("instrument_id").agg(sh_p=("shares", "sum"),
                                           n_p=("filer_id", "nunique"))
    m = cs.join(ps, how="outer").fillna(0.0)
    so = m.index.to_series().map(shares_out)
    m["pso"] = m["sh"] / so
    m["dio"] = (m["sh"] - m["sh_p"]) / so
    # normalise by filer-count growth (the denominator grew 10x in 40 years)
    m["dnuminst"] = (m["n"] - m["n_p"]) / max(float(cur["filer_id"].nunique()), 1.0)
    return m[["dio", "dnuminst", "pso"]]
