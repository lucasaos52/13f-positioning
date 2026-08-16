"""Falsification battery (plan §6.1) - run and REPORT even when they pass.

Each test targets one specific failure class:

  shuffled signal   permute the signal across stocks within each date, 200x;
                    the actual spread's percentile in that null distribution
                    is a permutation p-value free of distributional
                    assumptions. Detects: spurious spread from cross-
                    sectional structure (skew, clustering) rather than
                    signal-return alignment.
  lead signal       use the signal formed at t+1 to "predict" the return
                    over t. If this WORKS, information from the future is
                    leaking into the panel (bad PIT join, wrong date
                    arithmetic). It must fail; its failing is evidence.
  split halves      first vs second half of the sample. Detects: one-regime
                    results and post-publication decay (McLean-Pontiff).
  momentum overlap  correlation of the factor with 12-1 momentum and with
                    the drift-uncorrected variant. The drift correction
                    (signals.py step 2) exists precisely because the naive
                    version IS lagged momentum; this measures how much.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats as sps


def permutation_pvalue(events: list[tuple[pd.Series, pd.Series]],
                       n_perm: int = 200, seed: int = 13) -> dict:
    """events: list of (signal, fwd_return) per formation date.
    Returns actual mean spread, null distribution stats, p-value."""
    rng = np.random.default_rng(seed)
    actual, nulls = [], np.zeros(n_perm)
    for sig, fwd in events:
        df = pd.concat([sig.rename("s"), fwd.rename("f")], axis=1).dropna()
        if len(df) < 50:
            continue
        q = pd.qcut(df["s"], 5, labels=False, duplicates="drop")
        actual.append(df["f"][q == 4].mean() - df["f"][q == 0].mean())
        f = df["f"].values
        for k in range(n_perm):
            perm = rng.permutation(len(f))
            nulls[k] += f[perm][q == 4].mean() - f[perm][q == 0].mean()
    if not actual:
        return {}
    mean_actual = float(np.mean(actual))
    nulls /= len(actual)
    p = float((np.abs(nulls) >= abs(mean_actual)).mean())
    return {"spread_actual": mean_actual, "null_sd": float(nulls.std()),
            "perm_pvalue": p, "n_events": len(actual)}


def lead_signal_test(signals: dict, fwds: dict) -> dict:
    """Spread using signal formed at the NEXT event against this event's
    return. Must be ~zero; significance here = lookahead bug."""
    keys = sorted(signals)
    spreads = []
    for a, b in zip(keys[:-1], keys[1:]):
        sig_next, fwd_now = signals[b], fwds[a]
        df = pd.concat([sig_next.rename("s"), fwd_now.rename("f")], axis=1).dropna()
        if len(df) < 50:
            continue
        q = pd.qcut(df["s"], 5, labels=False, duplicates="drop")
        spreads.append(df["f"][q == 4].mean() - df["f"][q == 0].mean())
    if len(spreads) < 8:
        return {}
    s = pd.Series(spreads)
    t = s.mean() / s.std() * np.sqrt(len(s)) if s.std() > 0 else np.nan
    # Sign matters. Lookahead = the future signal HELPS predict the past
    # return (positive t: the signal contains the return). A strongly
    # NEGATIVE t is the opposite arrow: returns cause the NEXT signal -
    # managers trade in response to past returns (feedback trading,
    # Nofsinger-Sias 1999). That is an economic finding, not a PIT bug.
    if t > 2.5:
        verdict = "FAIL (lookahead!)"
    elif t < -2.5:
        verdict = "pass (negative = feedback trading, returns -> next signal)"
    else:
        verdict = "pass"
    return {"lead_spread_mean": float(s.mean()), "lead_t": float(t),
            "verdict": verdict}


def split_halves(events: pd.DataFrame, col: str = "ew_spread") -> dict:
    if col not in events or len(events) < 16:
        return {}
    h = len(events) // 2
    a, b = events[col].iloc[:h], events[col].iloc[h:]
    return {"first_half_mean": float(a.mean()), "second_half_mean": float(b.mean()),
            "first_half_t": float(a.mean() / a.std() * np.sqrt(len(a))),
            "second_half_t": float(b.mean() / b.std() * np.sqrt(len(b)))}


def momentum_overlap(sig: pd.Series, sig_nodrift: pd.Series,
                     mom: pd.Series) -> dict:
    """Rank correlations at one date; averaged across dates by caller."""
    out = {}
    df = pd.concat([sig.rename("s"), sig_nodrift.rename("nd"),
                    mom.rename("m")], axis=1).dropna()
    if len(df) > 50:
        out["corr_sig_mom"] = float(sps.spearmanr(df["s"], df["m"])[0])
        out["corr_nodrift_mom"] = float(sps.spearmanr(df["nd"], df["m"])[0])
    return out
