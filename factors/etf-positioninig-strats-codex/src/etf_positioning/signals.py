"""The nine blueprint signals, separated into replications and adaptations.

No function below claims that quarterly 13F ownership change is an ETF
creation/redemption flow.  Where a published paper uses primary-market flow,
the argument is named ``etf_flow``.  Passing a 13F-derived demand measure is an
explicit adaptation and should be labelled as such in results.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _require(df: pd.DataFrame, columns: set[str], name: str) -> None:
    missing = columns - set(df)
    if missing:
        raise ValueError(f"{name} missing columns: {sorted(missing)}")


def _winsor_z(s: pd.Series, lower: float = 0.01, upper: float = 0.99) -> pd.Series:
    if s.notna().sum() < 3:
        return pd.Series(np.nan, index=s.index)
    lo, hi = s.quantile([lower, upper])
    w = s.clip(lo, hi)
    sd = w.std(ddof=0)
    return (w - w.mean()) / sd if sd > 0 else pd.Series(0.0, index=s.index)


def raw_etf_ownership_change(
    manager_etf_state: pd.DataFrame,
    etf_reference: pd.DataFrame,
    manager_weights: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Strategy #9 and the demand input to #1.

    ``manager_etf_state`` is a point-in-time quarterly snapshot with shares.
    Aggregate shares are divided by ETF shares outstanding, then differenced.
    This is disclosed institutional ownership change, *not* primary-market ETF
    flow (Brown, Davies & Ringgenberg, 2021).
    """

    _require(manager_etf_state, {"filer_id", "period_end", "etf_id", "shares"}, "state")
    _require(etf_reference, {"period_end", "etf_id", "shares_outstanding"}, "etf_reference")
    h = manager_etf_state.copy()
    h["period_end"] = pd.to_datetime(h["period_end"])
    if manager_weights is not None:
        _require(manager_weights, {"filer_id", "period_end", "manager_weight"}, "manager_weights")
        h = h.merge(manager_weights, on=["filer_id", "period_end"], how="left")
        h["manager_weight"] = h["manager_weight"].fillna(0.0)
    else:
        h["manager_weight"] = 1.0
    h["weighted_shares"] = h["shares"] * h["manager_weight"]
    agg = h.groupby(["period_end", "etf_id"], as_index=False).agg(
        institutional_shares=("weighted_shares", "sum"),
        n_managers=("filer_id", "nunique"),
    )
    ref = etf_reference.copy()
    ref["period_end"] = pd.to_datetime(ref["period_end"])
    out = agg.merge(ref, on=["period_end", "etf_id"], how="left", validate="one_to_one")
    out["own_13f"] = out["institutional_shares"] / out["shares_outstanding"].replace(0, np.nan)
    out = out.sort_values(["etf_id", "period_end"])
    out["d_own_13f"] = out.groupby("etf_id")["own_13f"].diff()
    return out


def filing_time_demand_nowcast(manager_changes: pd.DataFrame) -> pd.DataFrame:
    """Release manager ETF changes on their actual public timestamps.

    This is the event-time alternative to a fixed ``q + 70`` snapshot. Input
    changes must already reflect amendment semantics and split adjustments.
    The function never carries information across quarters and emits the
    cumulative, within-quarter demand nowcast after each filing event.
    """

    required = {"filer_id", "period_end", "available_ts", "etf_id", "delta_shares"}
    _require(manager_changes, required, "manager_changes")
    x = manager_changes.copy()
    x["period_end"] = pd.to_datetime(x["period_end"])
    x["available_ts"] = pd.to_datetime(x["available_ts"])
    if (x["available_ts"] < x["period_end"]).any():
        raise ValueError("available_ts precedes report period")
    if "manager_weight" not in x:
        x["manager_weight"] = 1.0
    x["weighted_delta_shares"] = x["delta_shares"] * x["manager_weight"].fillna(0.0)
    events = x.groupby(["period_end", "etf_id", "available_ts"], as_index=False).agg(
        event_delta_shares=("weighted_delta_shares", "sum"),
        n_filers_event=("filer_id", "nunique"),
    ).sort_values(["period_end", "etf_id", "available_ts"])
    by = events.groupby(["period_end", "etf_id"], sort=False)
    events["demand_nowcast_shares"] = by["event_delta_shares"].cumsum()
    events["n_filers_cumulative"] = by["n_filers_event"].cumsum()
    return events


def lookthrough_pressure(
    etf_demand: pd.DataFrame,
    baskets: pd.DataFrame,
    stock_reference: pd.DataFrame,
    demand_col: str = "d_own_13f",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Strategy #1 adaptation: map ETF demand into constituent pressure.

    Returns stock-level pressure and an auditable ETF-stock contribution table.
    Historical basket rows must be stamped by ``period_end``; the function
    rejects duplicate ETF-stock-period keys and future-effective constituents.
    """

    _require(etf_demand, {"period_end", "etf_id", demand_col, "aum"}, "etf_demand")
    _require(baskets, {"period_end", "etf_id", "instrument_id", "basket_weight"}, "baskets")
    _require(stock_reference, {"period_end", "instrument_id", "market_cap"}, "stock_reference")
    d, b, r = etf_demand.copy(), baskets.copy(), stock_reference.copy()
    for frame in (d, b, r):
        frame["period_end"] = pd.to_datetime(frame["period_end"])
    if b.duplicated(["period_end", "etf_id", "instrument_id"]).any():
        raise ValueError("baskets contain duplicate ETF-stock-period keys")
    if "effective_date" in b:
        b["effective_date"] = pd.to_datetime(b["effective_date"])
        if (b["effective_date"] > b["period_end"]).any():
            raise ValueError("basket effective_date is after its labelled period_end (lookahead)")
    contrib = b.merge(
        d[["period_end", "etf_id", demand_col, "aum"]],
        on=["period_end", "etf_id"], how="inner", validate="many_to_one",
    ).merge(
        r[["period_end", "instrument_id", "market_cap"]],
        on=["period_end", "instrument_id"], how="left", validate="many_to_one",
    )
    contrib["pressure_contribution"] = (
        contrib["basket_weight"] * contrib[demand_col] * contrib["aum"]
        / contrib["market_cap"].replace(0, np.nan)
    )
    stock = contrib.groupby(["period_end", "instrument_id"], as_index=False).agg(
        pressure=("pressure_contribution", "sum"),
        n_etfs=("etf_id", "nunique"),
    )
    stock["pressure_z"] = stock.groupby("period_end")["pressure"].transform(_winsor_z)
    stock["reversal_alpha"] = -stock["pressure_z"]
    return stock, contrib


def _shrunk_cov(x: pd.DataFrame, shrinkage: float) -> np.ndarray:
    s = np.atleast_2d(np.cov(x.to_numpy(dtype=float), rowvar=False))
    d = np.diag(np.diag(s))
    s = (1.0 - shrinkage) * s + shrinkage * d
    vals, vecs = np.linalg.eigh(s)
    return (vecs * np.clip(vals, 0.0, None)) @ vecs.T


def etf_fragility(
    baskets: pd.DataFrame,
    etf_flows: pd.DataFrame,
    stock_reference: pd.DataFrame,
    lookback: int = 12,
    min_periods: int = 8,
    shrinkage: float = 0.50,
) -> pd.DataFrame:
    """Strategy #2 risk state, Greenwood-Thesmar / Galindo-Gil-Lazo-Paz.

    For each period ``t``, Omega is estimated only with flows dated before or
    at ``t`` and after the trailing lookback boundary.  The quadratic form is
    ``W_i Omega W_i' / market_cap_i^2``.  This is close to the published ETF
    fragility specification only when ``etf_flows`` are primary-market dollar
    flows and baskets are historical; with 13F demand it is an adaptation.
    """

    _require(baskets, {"period_end", "etf_id", "instrument_id", "basket_weight"}, "baskets")
    _require(etf_flows, {"date", "etf_id", "dollar_flow"}, "etf_flows")
    _require(stock_reference, {"period_end", "instrument_id", "market_cap"}, "stock_reference")
    b, f, ref = baskets.copy(), etf_flows.copy(), stock_reference.copy()
    b["period_end"] = pd.to_datetime(b["period_end"])
    f["date"] = pd.to_datetime(f["date"])
    ref["period_end"] = pd.to_datetime(ref["period_end"])
    rows = []
    for p, bp in b.groupby("period_end", sort=True):
        hist_dates = sorted(f.loc[f["date"] <= p, "date"].unique())[-lookback:]
        hist = f[f["date"].isin(hist_dates)].pivot_table(
            index="date", columns="etf_id", values="dollar_flow", aggfunc="sum"
        )
        etfs = sorted(set(bp["etf_id"]) & set(hist.columns))
        if len(hist) < min_periods or len(etfs) < 2:
            continue
        hist = hist[etfs].fillna(0.0)
        omega = _shrunk_cov(hist, shrinkage)
        w = bp.pivot_table(
            index="instrument_id", columns="etf_id", values="basket_weight", fill_value=0.0
        ).reindex(columns=etfs, fill_value=0.0)
        q = np.einsum("ij,jk,ik->i", w.to_numpy(), omega, w.to_numpy())
        cap = ref[ref["period_end"].eq(p)].set_index("instrument_id")["market_cap"].reindex(w.index)
        frag = q / cap.to_numpy(dtype=float) ** 2
        rows.append(pd.DataFrame({"period_end": p, "instrument_id": w.index, "fragility": frag}))
    out = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(
        columns=["period_end", "instrument_id", "fragility"]
    )
    if not out.empty:
        out["fragility_z"] = out.groupby("period_end")["fragility"].transform(_winsor_z)
    return out


def pressure_scaled_by_fragility(pressure: pd.DataFrame, fragility: pd.DataFrame) -> pd.DataFrame:
    """Blueprint #2 alpha: direction from pressure, magnitude from fragility."""

    out = pressure.merge(fragility, on=["period_end", "instrument_id"], how="inner")
    out["pressure_fragility_alpha"] = (
        -out["pressure_z"] * (1.0 + out["fragility_z"].clip(lower=0.0))
    )
    return out


def specialized_pressure(
    contributions: pd.DataFrame, etf_master: pd.DataFrame
) -> pd.DataFrame:
    """Strategy #3: pressure routed through specialized/active ETFs."""

    _require(contributions, {"period_end", "etf_id", "instrument_id", "pressure_contribution"}, "contrib")
    _require(etf_master, {"etf_id", "specialized_score"}, "etf_master")
    c = contributions.merge(
        etf_master[["etf_id", "specialized_score"]].drop_duplicates("etf_id"),
        on="etf_id", how="left", validate="many_to_one",
    )
    c["specialized_contribution"] = c["pressure_contribution"] * c["specialized_score"].fillna(0.0)
    out = c.groupby(["period_end", "instrument_id"], as_index=False)["specialized_contribution"].sum()
    out["specialized_pressure_z"] = out.groupby("period_end")["specialized_contribution"].transform(_winsor_z)
    out["specialized_reversal_alpha"] = -out["specialized_pressure_z"]
    return out


def run_prone_pressure(
    contributions: pd.DataFrame, run_prone_share: pd.DataFrame
) -> pd.DataFrame:
    """Strategy #4: look-through pressure weighted by transient ownership."""

    _require(run_prone_share, {"period_end", "etf_id", "run_prone_share"}, "run_prone_share")
    c = contributions.merge(run_prone_share, on=["period_end", "etf_id"], how="left")
    c["run_pressure_contribution"] = (
        c["pressure_contribution"] * c["run_prone_share"].fillna(0.0)
    )
    return c.groupby(["period_end", "instrument_id"], as_index=False)[
        "run_pressure_contribution"
    ].sum()


def direct_vs_etf_conviction(
    direct_holdings: pd.DataFrame,
    manager_etf_holdings: pd.DataFrame,
    baskets: pd.DataFrame,
    manager_quality: pd.DataFrame | None = None,
    kappa: str | float = "projection",
) -> pd.DataFrame:
    """Strategy #5: manager stock exposure residual to the ETF-implied sleeve.

    ``projection`` estimates a non-negative scalar independently for every
    manager-quarter.  ``1.0`` implements the simple blueprint version.  The
    output is standardized within each manager-quarter before aggregation so
    a large filer cannot dominate merely because its book is large.
    """

    _require(direct_holdings, {"filer_id", "period_end", "instrument_id", "value_usd"}, "direct")
    _require(manager_etf_holdings, {"filer_id", "period_end", "etf_id", "value_usd"}, "manager_etfs")
    _require(baskets, {"period_end", "etf_id", "instrument_id", "basket_weight"}, "baskets")
    implied = manager_etf_holdings.merge(baskets, on=["period_end", "etf_id"], how="inner")
    implied["etf_implied_usd"] = implied["value_usd"] * implied["basket_weight"]
    implied = implied.groupby(["filer_id", "period_end", "instrument_id"], as_index=False)[
        "etf_implied_usd"
    ].sum()
    direct = direct_holdings.groupby(
        ["filer_id", "period_end", "instrument_id"], as_index=False
    )["value_usd"].sum()
    x = direct.merge(implied, on=["filer_id", "period_end", "instrument_id"], how="outer").fillna(0.0)

    def residual(g: pd.DataFrame) -> pd.DataFrame:
        d = g["value_usd"].to_numpy(dtype=float)
        e = g["etf_implied_usd"].to_numpy(dtype=float)
        if kappa == "projection":
            denom = float(e @ e)
            kap = max(float(d @ e) / denom, 0.0) if denom > 0 else 0.0
        else:
            kap = float(kappa)
        g = g.copy()
        g["kappa"] = kap
        g["idio_conviction"] = d - kap * e
        g["idio_z_manager"] = _winsor_z(g["idio_conviction"])
        return g

    # pandas 2.2 changed whether grouping columns are included in ``apply``.
    # Keep the keys explicit so results are stable across the research and CI
    # environments (and so a manager identifier can never be silently lost).
    pieces: list[pd.DataFrame] = []
    for (filer_id, period_end), group in x.groupby(["filer_id", "period_end"], sort=False):
        piece = residual(group.drop(columns=["filer_id", "period_end"]))
        piece["filer_id"] = filer_id
        piece["period_end"] = period_end
        pieces.append(piece)
    x = pd.concat(pieces, ignore_index=True) if pieces else x.assign(
        kappa=np.nan, idio_conviction=np.nan, idio_z_manager=np.nan
    )
    if manager_quality is not None:
        _require(manager_quality, {"filer_id", "period_end", "quality_weight"}, "quality")
        x = x.merge(manager_quality, on=["filer_id", "period_end"], how="left")
        x["quality_weight"] = x["quality_weight"].fillna(0.0)
    else:
        x["quality_weight"] = 1.0
    x["weighted_idio"] = x["idio_z_manager"] * x["quality_weight"]
    out = x.groupby(["period_end", "instrument_id"], as_index=False).agg(
        idio13f=("weighted_idio", "sum"), n_managers=("filer_id", "nunique")
    )
    out["idio13f_z"] = out.groupby("period_end")["idio13f"].transform(_winsor_z)
    return out


def overlap_network_shock(baskets: pd.DataFrame, etf_demand: pd.DataFrame) -> pd.DataFrame:
    """Strategy #6: ETF peer shock using sum of minimum basket weights."""

    _require(baskets, {"period_end", "etf_id", "instrument_id", "basket_weight"}, "baskets")
    _require(etf_demand, {"period_end", "etf_id", "d_own_13f"}, "demand")
    rows = []
    for p, bp in baskets.groupby("period_end"):
        w = bp.pivot_table(index="etf_id", columns="instrument_id", values="basket_weight", fill_value=0.0)
        ids = list(w.index)
        arr = w.to_numpy(dtype=float)
        overlap = np.minimum(arr[:, None, :], arr[None, :, :]).sum(axis=2)
        np.fill_diagonal(overlap, 0.0)
        d = etf_demand[etf_demand["period_end"].eq(p)].set_index("etf_id")["d_own_13f"].reindex(ids).fillna(0.0)
        rows.append(pd.DataFrame({"period_end": p, "etf_id": ids, "network_shock": overlap.T @ d.to_numpy()}))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(
        columns=["period_end", "etf_id", "network_shock"]
    )


def conditioned_reversal(
    short_term_returns: pd.DataFrame, etf_footprint: pd.DataFrame
) -> pd.DataFrame:
    """Strategy #7: fast reversal trigger scaled by slow ETF footprint."""

    _require(short_term_returns, {"date", "instrument_id", "short_return"}, "returns")
    _require(etf_footprint, {"date", "instrument_id", "etf_ownership"}, "footprint")
    out = short_term_returns.merge(etf_footprint, on=["date", "instrument_id"], how="inner")
    out["etf_ownership_z"] = out.groupby("date")["etf_ownership"].transform(_winsor_z)
    out["conditioned_reversal"] = -out["short_return"] * out["etf_ownership_z"].clip(lower=0.0)
    return out
