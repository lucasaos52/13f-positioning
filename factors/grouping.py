"""Grouping: correlation clusters -> Sharpe-weighted combination.

The mini version of the multifactor's qualitative-grouping + aggregation
stages, in one place:

1. **Cluster by correlation of portfolio returns.** Agglomerative,
   average linkage: repeatedly merge the two clusters whose mean pairwise
   return correlation is highest, until `n_groups` remain. Two indicators
   that are the same bet in different clothes end up together, so the final
   book does not triple-count one idea.

2. **Combine inside each cluster proportionally to Sharpe** (production's
   SharpeWeightedGroup). Negative-Sharpe members get weight zero rather
   than a short position in their own factor — the grouping stage selects,
   it does not bet against.

3. **Intersection (the `intersection` parameter).** Within a cluster,
   positions where fewer than `intersection` (fraction) of the member
   portfolios agree on the SIDE are zeroed before combining. At 0 this is
   off; at 0.5, a name only survives if half the members hold it the same
   way. This is the mini version of production's portfolio-intersections
   boost: names several indicators agree on are the cluster's actual
   signal; one-off positions are noise.

The output portfolios come back un-rebalanced on purpose: combining and
re-normalizing changes the weights, so the caller re-runs
`rebalance(idxs, prices)` — same order as the production pipeline.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from portfolio import Portfolio


def sharpe_ratio(returns: pd.Series) -> float:
    """Production formula: annualized geometric return over annualized vol."""
    r = returns.dropna()
    if len(r) < 21 or r.std() == 0:
        return np.nan
    ann_ret = (1 + r).prod() ** (252 / len(r)) - 1
    return float(ann_ret / (r.std() * np.sqrt(252)))


def correlation_groups(returns: pd.DataFrame, n_groups: int) -> list[list[str]]:
    """Agglomerative average-linkage clustering on return correlation.

    `returns`: one column per portfolio. Returns a list of clusters, each a
    list of column names. Deterministic: ties break on column order.
    """
    corr = returns.corr()
    clusters: list[list[str]] = [[c] for c in returns.columns]
    while len(clusters) > max(n_groups, 1):
        best, best_pair = -np.inf, None
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                mean_corr = float(corr.loc[clusters[i], clusters[j]].mean().mean())
                if mean_corr > best:
                    best, best_pair = mean_corr, (i, j)
        i, j = best_pair
        clusters[i] = clusters[i] + clusters[j]
        del clusters[j]
    return clusters


def _apply_intersection(members: list[Portfolio], intersection: float) -> list[Portfolio]:
    """Zero positions where fewer than `intersection` of members agree on
    the side. Sign-aware: long agreement and short agreement count apart."""
    if intersection <= 0 or len(members) == 1:
        return members
    n = len(members)
    long_count = sum((p.weights > 0).astype(int) for p in members)
    short_count = sum((p.weights < 0).astype(int) for p in members)
    keep_long = long_count >= max(1, int(np.ceil(intersection * n)))
    keep_short = short_count >= max(1, int(np.ceil(intersection * n)))
    out = []
    for p in members:
        q = p.clone()
        q.weights = q.weights.where(
            ((q.weights > 0) & keep_long) | ((q.weights < 0) & keep_short) | (q.weights == 0), 0.0
        )
        out.append(q)
    return out


def sharpe_weighted_combine(name: str, members: list[Portfolio],
                            member_returns: pd.DataFrame,
                            intersection: float = 0.0,
                            normalize_type: str = "split") -> Portfolio:
    """One cluster -> one portfolio, members weighted by max(Sharpe, 0).

    If every member has non-positive Sharpe the cluster falls back to equal
    weights — the grouping stage must not silently delete a cluster.
    """
    members = _apply_intersection(members, intersection)
    sharpes = np.array([sharpe_ratio(member_returns[p.name]) for p in members])
    w = np.clip(np.nan_to_num(sharpes), 0, None)
    if w.sum() == 0:
        w = np.ones(len(members))
    w = w / w.sum()

    combined = None
    for weight, p in zip(w, members):
        scaled = p * float(weight)
        combined = scaled if combined is None else combined + scaled
    combined.name = name
    return combined.normalize(type=normalize_type)


def group_and_combine(portfolios: list[Portfolio], market_data,
                      n_groups: int, rb_idxs: np.ndarray,
                      trading_fee: float | None = None,
                      cash_leg: pd.Series | None = None,
                      intersection: float = 0.0,
                      normalize_type: str = "split") -> dict:
    """The full stage: returns -> clusters -> Sharpe-weighted combination.

    Returns {"groups": [[names]], "portfolios": [Portfolio per cluster],
    "combined": Portfolio equal-weighting the clusters} — all rebalanced on
    `rb_idxs`, ready for `period_return_sum`.

    The Sharpe used for weighting is computed on the SAME window being
    backtested, which is in-sample for the weights. Production solves this
    with expanding windows; here it is a stated simplification — quote
    cluster-level results, not the combined line, when that matters.
    """
    bt_returns = pd.DataFrame({
        p.name: p.period_return_sum(market_data, trading_fee, cash_leg) for p in portfolios
    })
    groups = correlation_groups(bt_returns, n_groups)

    prices = market_data.prices if hasattr(market_data, "prices") else None
    by_name = {p.name: p for p in portfolios}
    group_portfs = []
    for k, names in enumerate(groups):
        gp = sharpe_weighted_combine(
            f"group_{k + 1}", [by_name[n] for n in names], bt_returns,
            intersection=intersection, normalize_type=normalize_type,
        )
        if prices is not None:
            gp.rebalance(rb_idxs, prices)
        group_portfs.append(gp)

    combined = None
    for gp in group_portfs:
        scaled = gp * (1.0 / len(group_portfs))
        combined = scaled if combined is None else combined + scaled
    combined.name = "combined"
    combined.normalize(type=normalize_type)
    if prices is not None:
        combined.rebalance(rb_idxs, prices)

    return {"groups": groups, "portfolios": group_portfs, "combined": combined}
