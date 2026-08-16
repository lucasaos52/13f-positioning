"""The signal transformation pipeline (plan §4.1), applied identically to
every factor so cross-factor comparison is clean.

Order matters and each step has a reason:
  1. universe filter FIRST - every statistic below is computed on the
     tradable cross-section only, or winsor bounds and ranks leak
     information from names the portfolio can never hold;
  2. winsorise 1%/99% (never truncate - dropping tails throws away the very
     names a positioning factor is about);
  3. log for long-tailed ratio variables (Days-ADV, PSO);
  4. percentile rank - robust to the remaining outliers, scale-free across
     quarters whose cross-section width varies 3x over the sample;
  5. size neutralisation by cross-sectional regression on log mktcap:
     institutional ownership is mechanically increasing in cap
     (Gompers-Metrick 2001), so an un-neutralised positioning factor is a
     size factor with extra steps. Regression residual, not double-sort:
     with ~1,000-1,500 names per date, 5x5 sorts leave ~40 names per cell.
  6. orthogonalisation against momentum 12-1 and the PRIOR-QUARTER return -
     the latter is critical: position changes follow past returns
     (feedback trading, Nofsinger-Sias 1999); without this step a holdings
     "change" factor is lagged momentum. Book-to-market is NOT available
     free of survivorship in this stack - stated exclusion, not an oversight.
  7. optional 2-quarter smoothing (average of last K signals).

Sector neutralisation is deliberately absent: no free point-in-time GICS/SIC
panel exists in this stack, and using today's classifications retroactively
is lookahead (plan §5.1 table). Listed in next-steps; the EDGAR SIC code per
filer is fetchable and would slot into step 5's regression as dummies.

Everything is computed per decision date, cross-sectionally - no full-sample
statistics anywhere (the normalisation lookahead of plan §5.1).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def winsorise(s: pd.Series, lo: float = 0.01, hi: float = 0.99) -> pd.Series:
    if s.notna().sum() < 20:
        return s
    return s.clip(s.quantile(lo), s.quantile(hi))


def rank_pct(s: pd.Series) -> pd.Series:
    return s.rank(pct=True)


def residualise(y: pd.Series, xs: pd.DataFrame) -> pd.Series:
    """Cross-sectional OLS residual of y on xs (with intercept), returned on
    y's index. Rows with any missing regressor keep their raw (de-meaned)
    value rather than being dropped - documented degradation, not silent."""
    # +-inf (log of a zero market cap) passes a NaN filter and blows up the
    # SVD; neutralise to NaN so those rows take the de-meaned fallback
    df = pd.concat([y.rename("y"), xs], axis=1).replace([np.inf, -np.inf], np.nan)
    ok = df.notna().all(axis=1)
    if ok.sum() < 30:
        return y - y.mean()
    X = np.column_stack([np.ones(ok.sum()), df.loc[ok, xs.columns].values])
    try:
        beta, *_ = np.linalg.lstsq(X, df.loc[ok, "y"].values, rcond=None)
    except np.linalg.LinAlgError:
        return y - y.mean()
    resid = y.copy()
    resid[ok] = df.loc[ok, "y"].values - X @ beta
    resid[~ok] = y[~ok] - y[ok].mean()
    return resid


def pipeline(raw: pd.Series, log_first: bool,
             controls: pd.DataFrame) -> pd.Series:
    """winsorise -> (log) -> rank -> residualise on controls -> re-rank.

    `controls` columns expected: log_mktcap, mom_12_1, ret_prev_q (any subset;
    missing columns are simply not controlled for - and REPORTED upstream)."""
    s = winsorise(raw.replace([np.inf, -np.inf], np.nan))
    if log_first:
        s = np.log1p(s.clip(lower=0))
    s = rank_pct(s)
    ctrl = controls.reindex(s.index)
    s = residualise(s, ctrl)
    return rank_pct(s)


def smooth(history: list[pd.Series], k: int = 2) -> pd.Series:
    """Average of the last k quarterly signals (union index)."""
    take = [h for h in history[-k:] if h is not None]
    if not take:
        return pd.Series(dtype=float)
    return pd.concat(take, axis=1).mean(axis=1)
