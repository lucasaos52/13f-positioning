"""Backtest engine.

Structure is deliberately boring: a monthly loop that, at each rebalance date,
takes the signal that was tradeable on that date, forms weights, and earns the
*next* month's return net of the cost of getting into position. There is no
optimiser, no risk model and no shrinkage of the alpha into a target portfolio,
because none of those would make the evidence about the factor cleaner and all
of them would make it harder to attribute the result to the signal.

Timing convention, stated once and enforced in one place:

    weights formed from information available at ``t``
        -> return earned over ``(t, t+1]``
        -> costs charged at ``t``

The signal is quarterly and the return framework is monthly. The signal is held
flat between activations rather than interpolated. Holding it flat means the
factor's information decays naturally through the quarter, which is a property
we want to *measure* (the horizon decomposition) rather than to smooth away.

Two portfolios are reported for every factor:

* **quantile spread** - top minus bottom quintile, equal weighted. Robust,
  assumption-light, and the standard object in the literature, which makes the
  result comparable to published numbers.
* **z-weighted dollar-neutral** - weights proportional to the standardised
  score, gross normalised, per-name capped. Closer to how the signal would
  actually be deployed and therefore the one that carries the cost analysis.

Both are also reported gross, so the reader can see how much of the result the
cost model consumed rather than having to take the net number on faith.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from ..config import BacktestCfg
from .costs import borrow_cost, trade_costs

log = logging.getLogger(__name__)


def _form_weights(scores: pd.Series, cfg: BacktestCfg) -> pd.Series:
    """Dollar-neutral, gross-normalised, per-name capped weights."""
    s = scores.dropna()
    if s.empty:
        return s
    w = s - s.mean() if cfg.dollar_neutral else s
    gross = w.abs().sum()
    if gross <= 0:
        return w * 0.0
    w = w / gross * cfg.gross_leverage
    if cfg.max_weight:
        w = w.clip(-cfg.max_weight, cfg.max_weight)
        if cfg.dollar_neutral:
            w = w - w.mean()
        gross = w.abs().sum()
        if gross > 0:
            w = w / gross * cfg.gross_leverage
    return w


def _quantile_weights(scores: pd.Series, q: int) -> tuple[pd.Series, pd.Series]:
    s = scores.dropna()
    if s.nunique() < q * 2:
        return pd.Series(dtype=float), pd.Series(dtype=float)
    bins = pd.qcut(s.rank(method="first"), q, labels=False, duplicates="drop")
    top, bot = s[bins == bins.max()], s[bins == bins.min()]
    return (
        pd.Series(1.0 / len(top), index=top.index),
        pd.Series(1.0 / len(bot), index=bot.index),
    )


def run_backtest(
    signal_panel: pd.DataFrame,
    returns: pd.DataFrame,
    reference: pd.DataFrame,
    cfg: BacktestCfg,
    signal_col: str,
    capital_usd: float = 5e8,
) -> dict[str, pd.DataFrame]:
    """Run one factor through the monthly loop.

    ``signal_panel``: rebalance_date, instrument_id, <signal_col>, stale
    ``returns``: instrument_id, month, ret_m  (return *of* that month)
    ``reference``: instrument_id, period_end, price, adv_usd, vol_ann, mktcap
    """
    sig = signal_panel[~signal_panel.get("stale", False).fillna(False)].copy()
    sig["month"] = sig["rebalance_date"].dt.to_period("M")

    ret = returns.copy()
    ret["month"] = ret["month"].astype("period[M]")
    ret_lookup = ret.set_index(["month", "instrument_id"])["ret_m"]

    # Latest reference row per instrument at or before each rebalance, for the
    # cost model. Merge_asof keeps this strictly backward looking.
    ref = reference.sort_values("period_end")

    months = sorted(sig["month"].unique())
    prev_w = pd.Series(dtype=float)
    prev_top = pd.Series(dtype=float)
    prev_bot = pd.Series(dtype=float)
    rows: list[dict] = []
    weight_log: list[pd.DataFrame] = []

    for m in months:
        cut = sig[sig["month"] == m]
        if cut.empty:
            continue
        rdate = cut["rebalance_date"].iloc[0]

        # Eligibility at formation time only.
        ref_now = ref[ref["period_end"] <= rdate]
        if ref_now.empty:
            continue
        ref_now = ref_now.groupby("instrument_id").last()
        elig = ref_now[
            (ref_now["price"] >= cfg.price_floor_usd)
            & ref_now["adv_usd"].gt(0)
            & ref_now["mktcap"].gt(0)
        ]
        if cfg.max_names:
            elig = elig.nlargest(min(cfg.max_names, len(elig)), "mktcap")

        scores = cut.set_index("instrument_id")[signal_col]
        scores = scores[scores.index.isin(elig.index)].dropna()
        if len(scores) < 50:
            continue

        w = _form_weights(scores, cfg)
        top, bot = _quantile_weights(scores, cfg.quantiles)

        nxt = m + 1
        r = ret_lookup.reindex(pd.MultiIndex.from_product([[nxt], w.index])).droplevel(0)
        r = r.fillna(0.0)

        gross_ret = float((w * r).sum())
        q_top = float((top * ret_lookup.reindex(pd.MultiIndex.from_product([[nxt], top.index])).droplevel(0).fillna(0)).sum()) if len(top) else np.nan
        q_bot = float((bot * ret_lookup.reindex(pd.MultiIndex.from_product([[nxt], bot.index])).droplevel(0).fillna(0)).sum()) if len(bot) else np.nan

        # --- costs -------------------------------------------------------- #
        idx = w.index.union(prev_w.index)
        dw = w.reindex(idx).fillna(0.0) - prev_w.reindex(idx).fillna(0.0)
        c = trade_costs(
            dw,
            elig["adv_usd"].reindex(idx),
            elig["vol_ann"].reindex(idx),
            capital_usd,
            cfg.spread_bps,
            cfg.impact_coef_bps,
        ).sum()
        c += borrow_cost(w, cfg.borrow_bps_ann, months=1.0)

        idx_q = top.index.union(bot.index).union(prev_top.index).union(prev_bot.index)
        dq = (
            top.reindex(idx_q).fillna(0) - bot.reindex(idx_q).fillna(0)
        ) - (prev_top.reindex(idx_q).fillna(0) - prev_bot.reindex(idx_q).fillna(0))
        cq = trade_costs(
            dq, elig["adv_usd"].reindex(idx_q), elig["vol_ann"].reindex(idx_q),
            capital_usd, cfg.spread_bps, cfg.impact_coef_bps,
        ).sum()

        # --- information coefficient -------------------------------------- #
        r_all = ret_lookup.reindex(pd.MultiIndex.from_product([[nxt], scores.index])).droplevel(0)
        pair = pd.DataFrame({"s": scores, "r": r_all}).dropna()
        ic = pair["s"].corr(pair["r"], method="spearman") if len(pair) > 30 else np.nan

        rows.append(
            {
                "month": m,
                "rebalance_date": rdate,
                "n_names": len(scores),
                "gross_ret": gross_ret,
                "cost": c,
                "net_ret": gross_ret - c,
                "q_top": q_top,
                "q_bot": q_bot,
                "q_spread_gross": q_top - q_bot if pd.notna(q_top) else np.nan,
                "q_spread_net": (q_top - q_bot - cq) if pd.notna(q_top) else np.nan,
                "turnover": float(dw.abs().sum() / 2),
                "ic": ic,
                "signal_age": float(cut["signal_age_days"].iloc[0]) if "signal_age_days" in cut else np.nan,
            }
        )
        weight_log.append(w.rename("weight").to_frame().assign(month=str(m)))
        prev_w, prev_top, prev_bot = w, top, bot

    panel = pd.DataFrame(rows)
    weights = pd.concat(weight_log) if weight_log else pd.DataFrame()
    return {"panel": panel, "weights": weights}


def horizon_ic(
    signal_panel: pd.DataFrame,
    returns: pd.DataFrame,
    signal_col: str,
    horizons_months: tuple[int, ...],
) -> pd.DataFrame:
    """IC at several forward horizons - the continuation/reversal test.

    The whole hypothesis rests on the sign changing with horizon. Reporting IC
    only at one month would leave the interesting half of the claim untested,
    and reporting a single cumulative number would hide a sign flip inside it.
    """
    sig = signal_panel.copy()
    sig["month"] = sig["rebalance_date"].dt.to_period("M")
    ret = returns.copy()
    ret["month"] = ret["month"].astype("period[M]")
    wide = ret.pivot_table(index="month", columns="instrument_id", values="ret_m")

    rows = []
    for h in horizons_months:
        fwd = (1 + wide).rolling(h).apply(np.prod, raw=True).shift(-h) - 1
        for m, grp in sig.groupby("month"):
            if m not in fwd.index:
                continue
            s = grp.set_index("instrument_id")[signal_col]
            f = fwd.loc[m].reindex(s.index)
            pair = pd.DataFrame({"s": s, "f": f}).dropna()
            if len(pair) < 30:
                continue
            rows.append(
                {
                    "horizon_m": h,
                    "month": m,
                    "ic": pair["s"].corr(pair["f"], method="spearman"),
                    "n": len(pair),
                }
            )
    return pd.DataFrame(rows)
