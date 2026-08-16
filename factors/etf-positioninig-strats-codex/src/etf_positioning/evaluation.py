"""Event-study evaluation with an honest 13F information clock."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from statsmodels.stats.sandwich_covariance import cov_hac
from statsmodels.regression.linear_model import OLS


def _nw_mean_t(values: pd.Series, maxlags: int = 1) -> float:
    y = values.dropna().to_numpy(dtype=float)
    if len(y) < 5:
        return np.nan
    fit = OLS(y, np.ones((len(y), 1))).fit()
    var = float(cov_hac(fit, nlags=min(maxlags, len(y) - 2))[0, 0])
    return float(fit.params[0] / np.sqrt(var)) if var > 0 else np.nan


def event_study(
    signals: pd.DataFrame,
    adjusted_prices: pd.DataFrame,
    horizons: tuple[int, ...] = (5, 21, 63, 126),
    quantile_fraction: float = 0.20,
    one_way_cost_bps: float = 10.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Cross-sectional IC and equal-weight top-minus-bottom event returns.

    Required signal columns are ``period_end``, ``available_date``, ``ticker``
    and ``signal``. Entry is the first close strictly after available_date;
    returns are adjusted close ratios. The conservative cost assumes entry and
    exit on both long and short legs (four one-way trades per event).
    """

    req = {"period_end", "available_date", "ticker", "signal"}
    missing = req - set(signals)
    if missing:
        raise ValueError(f"signals missing columns: {sorted(missing)}")
    px = adjusted_prices.sort_index()
    if not isinstance(px.index, pd.DatetimeIndex):
        raise ValueError("adjusted_prices index must be DatetimeIndex")
    rows = []
    for period, group in signals.groupby("period_end", sort=True):
        available = pd.Timestamp(group["available_date"].max())
        entry_pos = px.index.searchsorted(available, side="right")
        if entry_pos >= len(px):
            continue
        s = group.groupby("ticker")["signal"].mean().dropna()
        s = s[s.index.isin(px.columns)]
        if len(s) < 10 or s.nunique() < 5:
            continue
        n_tail = max(int(np.floor(len(s) * quantile_fraction)), 2)
        low, high = s.nsmallest(n_tail).index, s.nlargest(n_tail).index
        entry = px.iloc[entry_pos]
        for horizon in horizons:
            exit_pos = entry_pos + horizon
            if exit_pos >= len(px):
                continue
            fwd = px.iloc[exit_pos] / entry - 1.0
            both = pd.concat([s.rename("signal"), fwd.rename("fwd")], axis=1).dropna()
            if len(both) < 10:
                continue
            ic = float(spearmanr(both["signal"], both["fwd"]).statistic)
            spread = float(fwd.reindex(high).mean() - fwd.reindex(low).mean())
            rows.append({
                "period_end": pd.Timestamp(period),
                "available_date": available,
                "entry_date": px.index[entry_pos],
                "exit_date": px.index[exit_pos],
                "horizon": horizon,
                "n_names": len(both),
                "ic": ic,
                "spread_gross": spread,
                "spread_net": spread - 4.0 * one_way_cost_bps / 10_000.0,
            })
    events = pd.DataFrame(rows)
    if events.empty:
        return events, pd.DataFrame()
    summary_rows = []
    for horizon, g in events.groupby("horizon"):
        std = g["spread_net"].std(ddof=1)
        summary_rows.append({
            "horizon": horizon,
            "n_events": len(g),
            "n_names_median": g["n_names"].median(),
            "ic_mean": g["ic"].mean(),
            "ic_t_nw": _nw_mean_t(g["ic"], 1),
            "spread_gross_mean": g["spread_gross"].mean(),
            "spread_net_mean": g["spread_net"].mean(),
            "spread_net_t_nw": _nw_mean_t(g["spread_net"], 1),
            "spread_net_sharpe_ann": (
                g["spread_net"].mean() / std * np.sqrt(252.0 / horizon)
                if std and np.isfinite(std) else np.nan
            ),
            "positive_share": g["spread_net"].gt(0).mean(),
        })
    return events, pd.DataFrame(summary_rows)

