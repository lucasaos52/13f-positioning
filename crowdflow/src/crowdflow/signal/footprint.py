"""Manager-level footprint metrics: the inputs to dynamic universe selection.

The question this module answers is not "who is famous" or "who is big" but:

    which 13F filers, as of this moment, have the greatest capacity to
    transmit a correlated demand shock into equity prices?

Three orthogonal ingredients, each with its own literature:

**Impact** - how expensive is this book to move? A $10bn book in megacaps and a
$10bn book in small caps are not the same object. Using the square-root impact
law, the dollar cost of liquidating a position scales as
``sigma * sqrt(Q/ADV) * Q``, so illiquid concentration is penalised
super-linearly. This is the Kyle/Almgren/Bouchaud formulation, and Bucci et al.
show that for institutional metaorders the *joint* impact of several managers
depends on aggregate order flow and the correlation of their order signs.

**Centrality** - is this manager in the same trades as everyone else? Define a
liquidity-scaled exposure ``x_mi = position_mi / ADV_i`` and take the
inner-product overlap between managers. A manager's centrality is its total
overlap with all others. Anton and Polk show that stocks connected by common
active ownership co-move in excess of what factors, industry and style explain,
which is the cross-sectional footprint of exactly this network.

**Turnover** - does the manager actually trade? A large, permanent, never-moved
book is not a source of demand shocks. Greenwood and Thesmar's fragility measure
makes this explicit: fragility rises with concentrated ownership *and* with
volatile or correlated trading needs of the holders. A buy-and-hold giant scores
high on concentration and low on fragility, correctly.

A fourth metric, **synchrony**, is computed as a diagnostic: the probability
that a manager's position changes share sign with the aggregate change of its
peers. This is the Sias herding statistic in manager-level form. It is reported
rather than scored by default, because it is mechanically correlated with
centrality and double counts if both are given weight.

Scale note: impact and centrality are dollar-denominated and heavy-tailed
across managers, so they enter the score as cross-sectional percentile ranks,
never as raw sums. Ranking is also what makes the score comparable through
time as the industry's asset base grows.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from ..config import UniverseCfg

log = logging.getLogger(__name__)

TRADING_DAYS_Y = 252.0

FOOTPRINT_COLS = [
    "filer_id",
    "period_end",
    "book_usd",
    "n_positions",
    "top1_weight",
    "hhi",
    "impact_cost_usd",
    "impact_bps",
    "centrality",
    "own_overlap",
    "turnover",
    "turnover_ewma",
    "synchrony",
    "n_quarters_history",
]


def _position_matrix(
    holdings: pd.DataFrame, value_col: str = "value_usd"
) -> tuple[np.ndarray, pd.Index, pd.Index]:
    """Dense (manager x instrument) matrix. Sparse-friendly sizes in practice."""
    pivot = holdings.pivot_table(
        index="filer_id", columns="instrument_id", values=value_col, aggfunc="sum", fill_value=0.0
    )
    return pivot.to_numpy(dtype=float), pivot.index, pivot.columns


def compute_footprint(
    holdings: pd.DataFrame,
    reference: pd.DataFrame,
    prev_holdings: pd.DataFrame | None,
    cfg: UniverseCfg,
    prev_reference: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """All manager metrics for one quarter.

    ``holdings`` and ``prev_holdings`` must both be materialised from the
    bitemporal store at the *same* vantage date, otherwise the turnover term
    silently mixes information from two different points in time.

    ``reference`` needs: instrument_id, adv_usd, vol_ann, price, cum_split_factor
    for the quarter end of ``holdings``. ``prev_reference`` is the same for the
    prior quarter and is required for a correct split adjustment; when omitted
    the current quarter's factors are reused, which is correct only if no
    security in the book split between the two dates.
    """
    if holdings.empty:
        return pd.DataFrame(columns=FOOTPRINT_COLS)

    ref = reference.set_index("instrument_id")
    df = holdings.copy()
    df["adv_usd"] = df["instrument_id"].map(ref["adv_usd"])
    df["vol_ann"] = df["instrument_id"].map(ref["vol_ann"])
    df["price"] = df["instrument_id"].map(ref["price"])
    df["split"] = df["instrument_id"].map(ref["cum_split_factor"]).fillna(1.0)

    # Positions we cannot price or size are dropped from the metrics but the
    # coverage loss is logged, because silently shrinking a manager's book
    # would bias it toward looking liquid.
    usable = df["adv_usd"].gt(0) & df["vol_ann"].gt(0)
    coverage = df.loc[usable, "value_usd"].sum() / max(df["value_usd"].sum(), 1.0)
    if coverage < 0.85:
        log.warning("reference data covers only %.1f%% of holdings value", 100 * coverage)
    df = df[usable].copy()
    if df.empty:
        return pd.DataFrame(columns=FOOTPRINT_COLS)

    # ---------------- impact ------------------------------------------- #
    sigma_d = df["vol_ann"] / np.sqrt(TRADING_DAYS_Y)
    participation = (df["value_usd"] / df["adv_usd"]).clip(lower=0)
    # Square-root law by default; exponent 1.0 recovers the linear (Kyle) form.
    df["pos_impact_usd"] = df["value_usd"] * sigma_d * participation.pow(cfg.impact_exponent)

    # ---------------- concentration ------------------------------------ #
    grp = df.groupby("filer_id", sort=False)
    book = grp["value_usd"].sum().rename("book_usd")
    weights = df["value_usd"] / df["filer_id"].map(book)
    df["_w2"] = weights.pow(2)

    out = pd.DataFrame(
        {
            "book_usd": book,
            "n_positions": grp["instrument_id"].nunique(),
            "top1_weight": grp["value_usd"].max() / book,
            "hhi": df.groupby("filer_id")["_w2"].sum(),
            "impact_cost_usd": grp["pos_impact_usd"].sum(),
        }
    )
    out["impact_bps"] = 1e4 * out["impact_cost_usd"] / out["book_usd"]

    # ---------------- centrality --------------------------------------- #
    # x_mi = position value in days of ADV. Overlap_mn = <x_m, x_n>.
    # Centrality_m = sum_{n != m} Overlap_mn = <x_m, s> - ||x_m||^2, where
    # s = sum_n x_n. Computing it this way is O(M*N) instead of O(M^2*N),
    # which is the difference between seconds and hours at 4,000 filers.
    df["x"] = df["value_usd"] / df["adv_usd"]
    X, mgr_idx, _ = _position_matrix(df, value_col="x")
    s = X.sum(axis=0)
    own = (X**2).sum(axis=1)
    degree = X @ s - own

    if cfg.centrality_mode == "eigenvector":
        # Power iteration on G = X X^T with a zeroed diagonal, never forming G.
        v = np.ones(len(mgr_idx)) / np.sqrt(len(mgr_idx))
        for _ in range(100):
            w = X @ (X.T @ v) - own * v
            nrm = np.linalg.norm(w)
            if nrm < 1e-30:
                break
            w = w / nrm
            if np.linalg.norm(w - v) < 1e-10:
                v = w
                break
            v = w
        centrality = np.abs(v) * np.abs(degree).sum()
    else:
        centrality = degree

    cent = pd.Series(centrality, index=mgr_idx, name="centrality")
    out = out.join(cent).join(pd.Series(own, index=mgr_idx, name="own_overlap"))
    if cfg.centrality_log1p:
        out["centrality"] = np.log1p(out["centrality"].clip(lower=0))

    # ---------------- turnover ----------------------------------------- #
    out["turnover"] = np.nan
    out["synchrony"] = np.nan
    if prev_holdings is not None and not prev_holdings.empty:
        pref = prev_reference.set_index("instrument_id") if prev_reference is not None else None
        turn, sync = _turnover_and_synchrony(df, prev_holdings, ref, pref)
        out["turnover"] = out.index.map(turn)
        out["synchrony"] = out.index.map(sync)

    out = out.reset_index().rename(columns={"index": "filer_id"})
    out["period_end"] = holdings["period_end"].iloc[0]
    return out


def _turnover_and_synchrony(
    cur: pd.DataFrame, prev: pd.DataFrame, ref: pd.DataFrame, prev_ref: pd.DataFrame | None
) -> tuple[pd.Series, pd.Series]:
    """Two-sided turnover on split-adjusted shares, plus peer-sign agreement.

    Share counts in 13F are as-filed and unadjusted. A 4-for-1 split between
    quarters turns an untouched position into an apparent 300% purchase, so
    both sides are put on a common basis first.

    The subtlety that makes this easy to get wrong: each leg must be divided by
    the cumulative split factor **as of its own quarter**, not by the current
    quarter's factor. Using the current factor on both legs re-introduces the
    error with the opposite sign - the untouched position then reads as a 75%
    sale. This is not a marginal refinement; splits cluster in exactly the
    large, liquid, widely held names that dominate the overlap network.

    Both legs are valued at the *current* quarter's price so that the measure
    reflects trading rather than price drift.
    """
    cur_s = cur.assign(shares_adj=cur["shares"] / cur["split"])[
        ["filer_id", "instrument_id", "shares_adj"]
    ]
    prev_factor = (
        prev["instrument_id"].map(prev_ref["cum_split_factor"])
        if prev_ref is not None
        else prev["instrument_id"].map(ref["cum_split_factor"])
    ).fillna(1.0)
    prev_s = prev.assign(shares_adj=prev["shares"] / prev_factor)[
        ["filer_id", "instrument_id", "shares_adj"]
    ]

    merged = cur_s.merge(
        prev_s, on=["filer_id", "instrument_id"], how="outer", suffixes=("_t", "_p")
    ).fillna({"shares_adj_t": 0.0, "shares_adj_p": 0.0})
    merged["price"] = merged["instrument_id"].map(ref["price"])
    merged = merged.dropna(subset=["price"])
    merged["d_shares"] = merged["shares_adj_t"] - merged["shares_adj_p"]
    merged["d_usd"] = merged["d_shares"] * merged["price"]

    prev_book = prev.groupby("filer_id")["value_usd"].sum()
    traded = merged.groupby("filer_id")["d_usd"].apply(lambda s: 0.5 * s.abs().sum())
    turnover = (traded / prev_book).replace([np.inf, -np.inf], np.nan)

    # Synchrony: does the manager move with the crowd? For each position,
    # compare its sign to the sign of the aggregate change of *other* managers
    # in the same name. Leave-one-out is essential, otherwise a manager large
    # enough to dominate the aggregate agrees with itself by construction.
    total = merged.groupby("instrument_id")["d_usd"].transform("sum")
    peers = total - merged["d_usd"]
    active = merged["d_shares"].abs().gt(0) & peers.abs().gt(0)
    agree = (np.sign(merged.loc[active, "d_usd"]) == np.sign(peers[active])).astype(float)
    synchrony = agree.groupby(merged.loc[active, "filer_id"]).mean()

    return turnover, synchrony


def stack_footprints(frames: list[pd.DataFrame], cfg: UniverseCfg) -> pd.DataFrame:
    """Concatenate quarterly footprints and add the history-dependent columns."""
    if not frames:
        return pd.DataFrame(columns=FOOTPRINT_COLS)
    df = pd.concat([f for f in frames if not f.empty], ignore_index=True)
    df = df.sort_values(["filer_id", "period_end"])

    df["n_quarters_history"] = df.groupby("filer_id").cumcount() + 1

    # EWMA of turnover: a single quarter's turnover is noisy and inflated by
    # entries and exits, so the score uses a smoothed version. Expanding mean
    # of the exponential weights keeps early observations usable rather than
    # discarding the first eight quarters of every filer.
    alpha = 1.0 - 0.5 ** (1.0 / cfg.turnover_halflife_q)
    df["turnover_ewma"] = (
        df.groupby("filer_id")["turnover"]
        .transform(lambda s: s.ewm(alpha=alpha, min_periods=1, adjust=True).mean())
    )
    return df.reset_index(drop=True)
