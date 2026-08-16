"""Stock-level positioning factors built from the dynamic manager universe.

The hypothesis is deliberately two-sided, because the literature is two-sided
and pretending otherwise would be the easiest way to fool ourselves.

**Continuation.** Sias documents that institutional demand is persistent
quarter to quarter and that institutions follow each other into names. If a
quarter's crowded accumulation is the visible first leg of a multi-quarter
reallocation, the near-term drift is positive. Lou's flow-induced trading
result is the sharpest version of this: predictable mechanical buying pushes
prices up first and only reverses later.

**Reversal.** Coval and Stafford give the mechanism in reverse - funds facing
outflows liquidate existing positions, and when several distressed funds share
holdings the pressure lands on the same names. Greenwood and Thesmar formalise
the state variable: a stock is *fragile* when ownership is concentrated among
holders whose trading needs are volatile or correlated, and fragility predicts
volatility. Ben-David et al. add that ownership by very large institutions is
itself associated with more noise.

These are not competing hypotheses about the sign of one number. They are
statements about different horizons and different conditioning states, and the
factor set is built to separate them rather than to average them into mush:

* ``caf`` - liquidity-scaled net demand from universe managers. The
  continuation leg. Expected to work at short horizons if it works at all.
* ``fragility`` - the Greenwood-Thesmar quadratic form, computed on the
  universe's holdings and the empirical covariance of manager flow rates.
  A conditioning variable, not a return forecast.
* ``caf_x_fragility`` - the interaction. The reversal leg: crowded
  accumulation *into fragile names* is the configuration where non-fundamental
  demand should be largest relative to the market's capacity to absorb it, and
  therefore where subsequent reversal should be strongest.
* ``consensus`` - breadth of agreement, signed. Distinguishes one manager
  buying a lot from ten managers each buying a little. The crowding story is
  about the second.

Everything is scaled by liquidity rather than by market cap. Price pressure is
a function of order flow against available volume, not against capitalisation,
and this is also what keeps a megacap's absolute dollar flow from dominating a
signal that is supposed to be about absorbable demand.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from ..config import FactorCfg

log = logging.getLogger(__name__)

FACTOR_NAMES = ["caf", "consensus", "fragility", "own_share", "caf_x_fragility"]


# --------------------------------------------------------------------------- #
def _delta_positions(
    cur: pd.DataFrame, prev: pd.DataFrame, ref: pd.DataFrame, prev_ref: pd.DataFrame | None = None
) -> pd.DataFrame:
    """Split-adjusted share changes, valued at the current quarter-end price.

    Each leg uses the cumulative split factor of its *own* quarter. Applying
    the current quarter's factor to the prior quarter's share count would turn
    every post-split name into a large phantom sale.
    """
    keys = ["filer_id", "instrument_id"]
    split = ref["cum_split_factor"]
    prev_split = prev_ref["cum_split_factor"] if prev_ref is not None else split
    c = cur.assign(shares_adj=cur["shares"] / cur["instrument_id"].map(split).fillna(1.0))
    p = prev.assign(shares_adj=prev["shares"] / prev["instrument_id"].map(prev_split).fillna(1.0))

    m = c[keys + ["shares_adj", "value_usd"]].merge(
        p[keys + ["shares_adj", "value_usd"]], on=keys, how="outer", suffixes=("_t", "_p")
    )
    m[["shares_adj_t", "shares_adj_p", "value_usd_t", "value_usd_p"]] = m[
        ["shares_adj_t", "shares_adj_p", "value_usd_t", "value_usd_p"]
    ].fillna(0.0)
    m["price"] = m["instrument_id"].map(ref["price"])
    m = m.dropna(subset=["price"])
    m["d_shares"] = m["shares_adj_t"] - m["shares_adj_p"]
    m["d_usd"] = m["d_shares"] * m["price"]
    return m


def _flow_covariance(
    flow_history: pd.DataFrame, managers: list[str], shrinkage: float
) -> tuple[np.ndarray, list[str]]:
    """Covariance of manager net-flow rates, shrunk toward its diagonal.

    Greenwood and Thesmar's fragility needs the covariance of holders' trading
    needs. With 25 managers and a dozen quarters the sample covariance is close
    to singular and its off-diagonal entries are mostly noise, so we shrink
    toward the diagonal. The shrinkage intensity is a config parameter rather
    than an estimate, and the result is checked to be positive semi-definite.
    """
    wide = flow_history.pivot_table(index="period_end", columns="filer_id", values="flow_rate")
    wide = wide.reindex(columns=managers)
    wide = wide.dropna(axis=1, how="all")
    kept = list(wide.columns)
    if len(kept) < 2:
        return np.zeros((len(kept), len(kept))), kept

    wide = wide.fillna(wide.mean())
    S = np.cov(wide.to_numpy(), rowvar=False)
    S = np.atleast_2d(S)
    D = np.diag(np.diag(S))
    S = (1.0 - shrinkage) * S + shrinkage * D

    # Guarantee PSD: fragility is a quadratic form and a negative value is
    # meaningless, so we clip eigenvalues rather than let it happen.
    vals, vecs = np.linalg.eigh(S)
    vals = np.clip(vals, 0.0, None)
    return (vecs * vals) @ vecs.T, kept


# --------------------------------------------------------------------------- #
def build_quarter_factors(
    cur_holdings: pd.DataFrame,
    prev_holdings: pd.DataFrame,
    universe_members: list[str],
    reference: pd.DataFrame,
    flow_history: pd.DataFrame,
    cfg: FactorCfg,
    prev_reference: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """All stock-level factors for one quarter.

    Both holdings frames must come from the bitemporal store at the same
    vantage date and must already be restricted to nothing - the universe
    filter is applied here so that the caller cannot forget it.
    """
    members = set(universe_members)
    cur = cur_holdings[cur_holdings["filer_id"].isin(members)]
    prev = prev_holdings[prev_holdings["filer_id"].isin(members)]
    if cur.empty:
        return pd.DataFrame(columns=["instrument_id", "period_end", *FACTOR_NAMES])

    ref = reference.set_index("instrument_id")
    pref = prev_reference.set_index("instrument_id") if prev_reference is not None else None
    deltas = _delta_positions(cur, prev, ref, pref)
    deltas["adv_usd"] = deltas["instrument_id"].map(ref["adv_usd"])
    deltas = deltas[deltas["adv_usd"].fillna(0) > 0]
    if deltas.empty:
        return pd.DataFrame(columns=["instrument_id", "period_end", *FACTOR_NAMES])

    qvol = deltas["adv_usd"] * cfg.quarter_trading_days

    # --- caf: net demand in units of quarterly dollar volume --------------- #
    caf = deltas.assign(scaled=deltas["d_usd"] / qvol).groupby("instrument_id")["scaled"].sum()

    # --- consensus: signed breadth ---------------------------------------- #
    moves = deltas[deltas["d_shares"].abs() > 0]
    n_buy = moves[moves["d_usd"] > 0].groupby("instrument_id").size()
    n_sell = moves[moves["d_usd"] < 0].groupby("instrument_id").size()
    n_tot = n_buy.add(n_sell, fill_value=0)
    consensus = (n_buy.sub(n_sell, fill_value=0) / n_tot).where(n_tot >= cfg.min_holders_for_consensus)

    # --- own_share: universe ownership as a fraction of market cap --------- #
    held = cur.groupby("instrument_id")["value_usd"].sum()
    mktcap = ref["mktcap"].reindex(held.index)
    own_share = (held / mktcap).replace([np.inf, -np.inf], np.nan)

    # --- fragility: Greenwood-Thesmar quadratic form ----------------------- #
    fragility = _fragility(cur, flow_history, ref, cfg)

    out = pd.DataFrame({"caf": caf}).join([consensus.rename("consensus"), own_share.rename("own_share"), fragility])
    out["fragility"] = out["fragility"].fillna(0.0)
    out.index.name = "instrument_id"
    out = out.reset_index()
    out["period_end"] = cur["period_end"].iloc[0]

    # The interaction is formed on ranks, not levels, because both legs are
    # heavy-tailed and their product in levels is dominated by a handful of
    # observations that are extreme in both.
    r_caf = out["caf"].rank(pct=True) - 0.5
    r_frag = out["fragility"].rank(pct=True)
    out["caf_x_fragility"] = r_caf * r_frag

    return out[["instrument_id", "period_end", *FACTOR_NAMES]]


def _fragility(
    cur: pd.DataFrame, flow_history: pd.DataFrame, ref: pd.DataFrame, cfg: FactorCfg
) -> pd.Series:
    """G_i = theta_i' Sigma theta_i / W_i^2 over universe managers."""
    managers = sorted(cur["filer_id"].unique())
    period = cur["period_end"].iloc[0]
    hist = flow_history[
        (flow_history["period_end"] < period)
        & (flow_history["period_end"] >= period - pd.DateOffset(months=3 * cfg.fragility_flow_lookback_q))
    ]
    Sigma, kept = _flow_covariance(hist, managers, cfg.fragility_shrinkage)
    if len(kept) < 2:
        return pd.Series(dtype=float, name="fragility")

    theta = cur.pivot_table(
        index="instrument_id", columns="filer_id", values="value_usd", aggfunc="sum", fill_value=0.0
    ).reindex(columns=kept, fill_value=0.0)
    T = theta.to_numpy(dtype=float)

    # Row-wise quadratic form without materialising an N x N matrix.
    g = np.einsum("ij,jk,ik->i", T, Sigma, T)
    W = ref["mktcap"].reindex(theta.index).to_numpy(dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        frag = np.where(W > 0, g / W**2, np.nan)
    return pd.Series(frag, index=theta.index, name="fragility")


# --------------------------------------------------------------------------- #
def manager_flow_rates(
    cur: pd.DataFrame,
    prev: pd.DataFrame,
    reference: pd.DataFrame,
    prev_reference: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Net flow rate per manager: net dollars traded over prior book.

    This is the ``trading needs`` input to fragility. Net, not gross: two
    managers who each churn 40% of their book but in opposite directions do
    not create correlated pressure, and a gross measure would say they do.
    """
    if cur.empty or prev.empty:
        return pd.DataFrame(columns=["filer_id", "period_end", "flow_rate"])
    ref = reference.set_index("instrument_id")
    pref = prev_reference.set_index("instrument_id") if prev_reference is not None else None
    d = _delta_positions(cur, prev, ref, pref)
    net = d.groupby("filer_id")["d_usd"].sum()
    prev_book = prev.groupby("filer_id")["value_usd"].sum()
    rate = (net / prev_book).replace([np.inf, -np.inf], np.nan).dropna()
    return pd.DataFrame(
        {"filer_id": rate.index, "period_end": cur["period_end"].iloc[0], "flow_rate": rate.to_numpy()}
    )


# --------------------------------------------------------------------------- #
def standardise(
    factors: pd.DataFrame,
    reference: pd.DataFrame,
    cfg: FactorCfg,
    columns: list[str] | None = None,
) -> pd.DataFrame:
    """Winsorise, z-score, and neutralise the mechanical size/liquidity tilt.

    A signal scaled by ADV is mechanically larger for illiquid names, so a raw
    version is partly a bet on small and illiquid stocks - a bet that is well
    compensated in-sample and expensive to trade out of sample. Regressing the
    signal on log market cap and log Amihud within each quarter and keeping the
    residual removes the mechanical part while retaining the cross-sectional
    positioning content. Both the raw and neutral versions are kept so the
    difference is visible in the results rather than assumed away.
    """
    columns = columns or FACTOR_NAMES
    ref = reference[["instrument_id", "period_end", "mktcap", "amihud"]].copy()
    df = factors.merge(ref, on=["instrument_id", "period_end"], how="left")
    df["log_mktcap"] = np.log(df["mktcap"].where(df["mktcap"] > 0))
    df["log_amihud"] = np.log(df["amihud"].where(df["amihud"] > 0))

    out_parts = []
    for period, grp in df.groupby("period_end", sort=True):
        g = grp.copy()
        for col in columns:
            v = g[col].astype(float)
            lo, hi = v.quantile(cfg.winsor_pct), v.quantile(1 - cfg.winsor_pct)
            v = v.clip(lo, hi)
            z = (v - v.mean()) / v.std(ddof=0)
            g[f"{col}_z"] = z.fillna(0.0)

            controls = [c for c in cfg.neutralise if c in g.columns]
            g[f"{col}_zn"] = _residualise(g[f"{col}_z"], g[controls]) if controls else g[f"{col}_z"]
        out_parts.append(g)
    return pd.concat(out_parts, ignore_index=True)


def _residualise(y: pd.Series, X: pd.DataFrame) -> pd.Series:
    """OLS residual with an intercept; rows with missing controls pass through."""
    ok = y.notna() & X.notna().all(axis=1)
    if ok.sum() < 20 or X.shape[1] == 0:
        return y
    A = np.column_stack([np.ones(ok.sum()), X.loc[ok].to_numpy(dtype=float)])
    b, *_ = np.linalg.lstsq(A, y.loc[ok].to_numpy(dtype=float), rcond=None)
    resid = y.copy()
    resid.loc[ok] = y.loc[ok].to_numpy() - A @ b
    s = resid.loc[ok].std(ddof=0)
    if s > 0:
        resid.loc[ok] = resid.loc[ok] / s
    return resid
