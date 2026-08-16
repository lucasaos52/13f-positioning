"""Performance statistics.

Two choices here are not cosmetic.

**Newey-West standard errors.** Monthly factor returns built from a quarterly
signal are autocorrelated by construction: the same signal is held for roughly
three months, so consecutive observations share information. An OLS t-statistic
on such a series overstates significance, sometimes badly. Every t-statistic
reported is HAC-corrected with a lag length tied to the holding period.

**A deflated Sharpe.** Any research process that evaluated several factor
variants faces a multiple-testing problem, and the honest response is to
discount the best observed Sharpe by the number of trials rather than to
present it raw. The implementation follows Bailey and Lopez de Prado. It is a
correction, not an absolution: it cannot recover what was lost to choices made
while looking at the data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

PERIODS = {"M": 12, "Q": 4, "D": 252}


def newey_west_tstat(x: pd.Series, lags: int | None = None) -> tuple[float, float]:
    """HAC t-statistic for the mean of a series, and the HAC standard error."""
    v = pd.Series(x).dropna().to_numpy(dtype=float)
    n = len(v)
    if n < 8:
        return np.nan, np.nan
    if lags is None:
        lags = int(np.floor(4 * (n / 100) ** (2 / 9)))
    mu = v.mean()
    e = v - mu
    gamma0 = (e @ e) / n
    s = gamma0
    for L in range(1, min(lags, n - 1) + 1):
        w = 1.0 - L / (lags + 1.0)  # Bartlett kernel
        s += 2 * w * (e[L:] @ e[:-L]) / n
    se = np.sqrt(max(s, 0.0) / n)
    return (mu / se if se > 0 else np.nan), se


def max_drawdown(returns: pd.Series) -> float:
    curve = (1 + returns.fillna(0)).cumprod()
    return float((curve / curve.cummax() - 1).min())


def deflated_sharpe(
    sr: float,
    n_obs: int,
    n_trials: int,
    skew: float = 0.0,
    kurt: float = 3.0,
    sr_dispersion: float | None = None,
) -> float:
    """Bailey and Lopez de Prado deflated Sharpe probability.

    ``sr`` is the *per-period* Sharpe, not the annualised one; mixing the two
    is the usual way this statistic gets reported as a meaningless number.

    The benchmark ``sr0`` is the expected maximum Sharpe across ``n_trials``
    independent attempts, and it scales with the dispersion of Sharpe estimates
    across those trials. Omitting that dispersion term - as is easy to do -
    leaves ``sr0`` around 1.0 in per-period units, which no monthly strategy
    ever clears, and the statistic degenerates to zero for everything.

    With no measured dispersion we use the null standard deviation of an
    estimated Sharpe, roughly ``1/sqrt(n_obs)``.
    """
    if n_obs < 12 or n_trials < 1 or not np.isfinite(sr):
        return np.nan
    dispersion = sr_dispersion if sr_dispersion is not None else 1.0 / np.sqrt(n_obs)
    euler = 0.5772156649
    n = max(n_trials, 2)
    z1 = stats.norm.ppf(1 - 1 / n)
    z2 = stats.norm.ppf(1 - 1 / (n * np.e))
    sr0 = dispersion * ((1 - euler) * z1 + euler * z2)
    denom = np.sqrt(max(1 - skew * sr + (kurt - 1) / 4 * sr**2, 1e-12))
    return float(stats.norm.cdf((sr - sr0) * np.sqrt(n_obs - 1) / denom))


def summarise_returns(
    returns: pd.Series, freq: str = "M", nw_lags: int = 6, n_trials: int = 1
) -> dict:
    r = pd.Series(returns).dropna()
    if r.empty:
        return {}
    ann = PERIODS.get(freq, 12)
    mu, sd = r.mean(), r.std(ddof=1)
    sharpe = (mu / sd * np.sqrt(ann)) if sd > 0 else np.nan
    t, se = newey_west_tstat(r, nw_lags)
    return {
        "n_periods": len(r),
        "mean_ann": float(mu * ann),
        "vol_ann": float(sd * np.sqrt(ann)),
        "sharpe": float(sharpe) if np.isfinite(sharpe) else np.nan,
        "t_stat_nw": float(t) if np.isfinite(t) else np.nan,
        "p_value_nw": float(2 * (1 - stats.norm.cdf(abs(t)))) if np.isfinite(t) else np.nan,
        "hit_rate": float((r > 0).mean()),
        "max_drawdown": max_drawdown(r),
        "skew": float(r.skew()),
        "kurtosis": float(r.kurtosis() + 3),
        "deflated_sharpe_prob": deflated_sharpe(
            sharpe / np.sqrt(ann) if np.isfinite(sharpe) else np.nan,
            len(r),
            n_trials,
            float(r.skew()),
            float(r.kurtosis() + 3),
        ),
    }


def summarise_ic(ic: pd.Series, nw_lags: int = 6) -> dict:
    v = pd.Series(ic).dropna()
    if v.empty:
        return {}
    t, _ = newey_west_tstat(v, nw_lags)
    return {
        "ic_mean": float(v.mean()),
        "ic_std": float(v.std(ddof=1)),
        "ic_ir": float(v.mean() / v.std(ddof=1)) if v.std(ddof=1) > 0 else np.nan,
        "ic_t_nw": float(t) if np.isfinite(t) else np.nan,
        "ic_hit_rate": float((v > 0).mean()),
        "n": len(v),
    }


def yearly_breakdown(panel: pd.DataFrame, ret_col: str = "net_ret") -> pd.DataFrame:
    """Per-year returns and IC. Sub-period instability is the main thing to look
    for in a factor with this few effective observations."""
    df = panel.copy()
    df["year"] = df["month"].astype(str).str[:4]
    return (
        df.groupby("year")
        .agg(
            months=("month", "size"),
            ret=(ret_col, lambda s: (1 + s).prod() - 1),
            vol=(ret_col, lambda s: s.std(ddof=1) * np.sqrt(12)),
            ic=("ic", "mean"),
            turnover=("turnover", "mean"),
        )
        .reset_index()
    )


def factor_table(results: dict[str, dict], nw_lags: int = 6) -> pd.DataFrame:
    """One row per factor variant, for the memo's headline table."""
    n_trials = len(results)
    rows = []
    for name, res in results.items():
        panel = res["panel"]
        if panel.empty:
            continue
        net = summarise_returns(panel["net_ret"], nw_lags=nw_lags, n_trials=n_trials)
        gross = summarise_returns(panel["gross_ret"], nw_lags=nw_lags, n_trials=n_trials)
        spread = summarise_returns(panel["q_spread_net"].dropna(), nw_lags=nw_lags, n_trials=n_trials)
        icd = summarise_ic(panel["ic"], nw_lags=nw_lags)
        rows.append(
            {
                "factor": name,
                "months": net.get("n_periods"),
                "gross_ann": gross.get("mean_ann"),
                "net_ann": net.get("mean_ann"),
                "vol_ann": net.get("vol_ann"),
                "sharpe_net": net.get("sharpe"),
                "t_nw": net.get("t_stat_nw"),
                "dsr_prob": net.get("deflated_sharpe_prob"),
                "maxdd": net.get("max_drawdown"),
                "q_spread_net_ann": spread.get("mean_ann"),
                "ic_mean": icd.get("ic_mean"),
                "ic_t_nw": icd.get("ic_t_nw"),
                "turnover_m": float(panel["turnover"].mean()),
                "cost_drag_ann": float(panel["cost"].mean() * 12),
            }
        )
    return pd.DataFrame(rows)
