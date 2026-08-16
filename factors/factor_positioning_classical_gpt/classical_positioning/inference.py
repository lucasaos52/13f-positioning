"""Small-sample inference utilities for the factor-by-quarter panel."""
from __future__ import annotations

import numpy as np
import pandas as pd


def newey_west_t(s: pd.Series, lags: int = 4) -> float:
    x = s.dropna().to_numpy(float)
    n = len(x)
    if n < 8:
        return np.nan
    e = x - x.mean()
    long_var = float(e @ e) / n
    for lag in range(1, min(lags, n - 1) + 1):
        gamma = float(e[lag:] @ e[:-lag]) / n
        long_var += 2.0 * (1.0 - lag / (lags + 1.0)) * gamma
    se = np.sqrt(max(long_var, 0.0) / n)
    return float(x.mean() / se) if se > 0 else np.nan


def clustered_panel_ols(
    data: pd.DataFrame,
    y: str,
    x: list[str],
    cluster: str = "period_end",
    factor_fe: bool = True,
    time_fe: bool = False,
) -> pd.DataFrame:
    """OLS with quarter-clustered CR1 errors and optional fixed effects."""
    cols = [y, cluster, *x]
    if factor_fe:
        cols.append("factor")
    if time_fe and "period_end" not in cols:
        cols.append("period_end")
    d = data[cols].replace([np.inf, -np.inf], np.nan).dropna().copy()
    if len(d) < 20:
        return pd.DataFrame(columns=["term", "coef", "se", "t", "n", "clusters"])
    design = pd.DataFrame({"intercept": 1.0}, index=d.index)
    for c in x:
        design[c] = d[c].astype(float)
    if factor_fe:
        design = pd.concat(
            [design, pd.get_dummies(d["factor"], prefix="factor", drop_first=True, dtype=float)],
            axis=1,
        )
    if time_fe:
        design = pd.concat(
            [
                design,
                pd.get_dummies(
                    pd.to_datetime(d["period_end"]).astype(str),
                    prefix="time",
                    drop_first=True,
                    dtype=float,
                ),
            ],
            axis=1,
        )
    X = design.to_numpy(float)
    Y = d[y].to_numpy(float)
    xtx_inv = np.linalg.pinv(X.T @ X)
    beta = xtx_inv @ X.T @ Y
    resid = Y - X @ beta
    meat = np.zeros((X.shape[1], X.shape[1]))
    groups = d[cluster].astype(str).to_numpy()
    unique = np.unique(groups)
    for g in unique:
        mask = groups == g
        score = X[mask].T @ resid[mask]
        meat += np.outer(score, score)
    n, k, G = len(d), X.shape[1], len(unique)
    correction = (G / (G - 1)) * ((n - 1) / max(n - k, 1)) if G > 1 else 1.0
    variance = correction * xtx_inv @ meat @ xtx_inv
    se = np.sqrt(np.maximum(np.diag(variance), 0.0))
    out = pd.DataFrame(
        {
            "term": design.columns,
            "coef": beta,
            "se": se,
            "t": np.divide(beta, se, out=np.full_like(beta, np.nan), where=se > 0),
            "n": n,
            "clusters": G,
        }
    )
    return out[out["term"].isin(x)].reset_index(drop=True)


def circular_block_bootstrap_mean(
    returns: pd.Series,
    block: int = 63,
    replications: int = 2000,
    seed: int = 17,
) -> dict[str, float]:
    """Confidence interval for daily mean preserving quarterly dependence."""
    x = returns.dropna().to_numpy(float)
    if len(x) < block * 2:
        return {"mean": float(np.mean(x)) if len(x) else np.nan, "lo": np.nan, "hi": np.nan}
    rng = np.random.default_rng(seed)
    means = np.empty(replications)
    n_blocks = int(np.ceil(len(x) / block))
    offsets = np.arange(block)
    for j in range(replications):
        starts = rng.integers(0, len(x), n_blocks)
        idx = (starts[:, None] + offsets[None, :]) % len(x)
        means[j] = x[idx.ravel()[: len(x)]].mean()
    lo, hi = np.quantile(means, [0.025, 0.975])
    return {"mean": float(x.mean()), "lo": float(lo), "hi": float(hi)}
