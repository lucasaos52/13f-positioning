"""Transaction costs.

A liquidity-scaled 13F factor tilts, by construction, toward names where a
given dollar of flow is large relative to volume. That is the whole point of
the signal - and it is also exactly the condition under which a linear
basis-point cost assumption is too generous. A flat 10bp charge would flatter
this factor specifically, so the model is two-term:

    cost = half_spread + impact_coefficient * sigma_daily * sqrt(participation)

The second term is the square-root impact law, the same functional form used to
build the manager footprint metric, applied here to our own trades. Using the
same law on both sides keeps the exercise internally consistent: we cannot
claim that other managers' size is costly to move and then assume ours is not.

Participation is computed against the fraction of a day's volume the strategy
would consume at an assumed deployed capital, so cost rises with AUM. Capacity
is therefore a reported curve rather than an afterthought.

Shorting is charged a borrow fee. It is flat here, which understates the cost
of shorting hard-to-borrow small caps - a limitation stated rather than hidden,
and one of the reasons the memo reports long-only and long-short separately.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS_Y = 252.0


def trade_costs(
    weight_delta: pd.Series,
    adv_usd: pd.Series,
    vol_ann: pd.Series,
    capital_usd: float,
    spread_bps: float,
    impact_coef_bps: float,
) -> pd.Series:
    """Per-name cost as a fraction of portfolio capital."""
    turnover = weight_delta.abs()
    trade_usd = turnover * capital_usd
    adv = adv_usd.reindex(turnover.index)
    sigma_d = vol_ann.reindex(turnover.index) / np.sqrt(TRADING_DAYS_Y)

    participation = (trade_usd / adv).replace([np.inf, -np.inf], np.nan).fillna(0.0).clip(0, 1.0)
    spread_cost = turnover * spread_bps / 1e4
    impact_cost = turnover * (impact_coef_bps / 1e4) * sigma_d.fillna(0.0) * np.sqrt(participation) * np.sqrt(TRADING_DAYS_Y)
    return (spread_cost + impact_cost).fillna(0.0)


def borrow_cost(weights: pd.Series, borrow_bps_ann: float, months: float = 1.0) -> float:
    """Financing charge on the short book for one holding period."""
    short_gross = weights.clip(upper=0).abs().sum()
    return short_gross * (borrow_bps_ann / 1e4) * (months / 12.0)


def capacity_curve(
    turnover_per_period: float,
    adv_weighted: float,
    periods_per_year: int,
    spread_bps: float,
    impact_coef_bps: float,
    sigma_ann: float,
    gross_alpha_ann: float,
    capital_grid: np.ndarray | None = None,
) -> pd.DataFrame:
    """Net alpha as a function of deployed capital.

    Answers the only question that matters about a factor with this much
    small-cap exposure: at what size does it stop paying for itself?
    """
    grid = capital_grid if capital_grid is not None else np.logspace(7, 11, 25)
    sigma_d = sigma_ann / np.sqrt(TRADING_DAYS_Y)
    rows = []
    for cap in grid:
        participation = np.clip((turnover_per_period * cap) / max(adv_weighted, 1.0), 0, 1)
        per_period = turnover_per_period * (
            spread_bps / 1e4 + (impact_coef_bps / 1e4) * sigma_d * np.sqrt(participation) * np.sqrt(TRADING_DAYS_Y)
        )
        annual_cost = per_period * periods_per_year
        rows.append({"capital_usd": cap, "annual_cost": annual_cost, "net_alpha": gross_alpha_ann - annual_cost})
    return pd.DataFrame(rows)
