"""Manager factor exposures, crowding state, and exact rotation decomposition."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .characteristics import CharacteristicSnapshot
from .config import ResearchConfig


@dataclass
class ManagerExposure:
    raw: pd.DataFrame
    active: pd.DataFrame
    metadata: pd.DataFrame


def holdings_to_pairs(
    snapshot: pd.DataFrame,
    ticker_map: pd.Series,
    values: pd.Series | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Map holdings to ticker while preserving total-book coverage.

    ``values`` optionally replaces reported quarter-end value with a drifted
    share-times-price value (used for the tradable exposure at decision date).
    """
    d = snapshot[["filer_id", "instrument_id", "shares", "value_usd"]].copy()
    d["ticker"] = d["instrument_id"].map(ticker_map)
    if values is not None:
        d["value"] = values.reindex(d.index)
    else:
        d["value"] = d["value_usd"]
    d["value"] = pd.to_numeric(d["value"], errors="coerce")
    total = d.groupby("filer_id").agg(
        book_value=("value", "sum"), n_positions=("instrument_id", "nunique")
    )
    pairs = (
        d.dropna(subset=["ticker", "value"])
        .query("value > 0")
        .groupby(["filer_id", "ticker"], as_index=False)
        .agg(value=("value", "sum"), shares=("shares", "sum"))
    )
    return pairs, total


def drift_snapshot_values(
    snapshot: pd.DataFrame,
    ticker_map: pd.Series,
    raw_prices: pd.Series,
) -> pd.Series:
    """Value disclosed shares at a later date without using future holdings."""
    ticker = snapshot["instrument_id"].map(ticker_map)
    return snapshot["shares"].astype(float) * ticker.map(raw_prices)


def manager_exposures(
    pairs: pd.DataFrame,
    manager_totals: pd.DataFrame,
    characteristic: CharacteristicSnapshot,
    config: ResearchConfig,
) -> ManagerExposure:
    """Compute E=W@X and active-vs-robust-cap-benchmark exposures."""
    x = characteristic.scores
    d = pairs[pairs["ticker"].isin(x.index)].copy()
    mapped_value = d.groupby("filer_id")["value"].sum().rename("mapped_value")
    meta = manager_totals.join(mapped_value, how="left").fillna({"mapped_value": 0.0})
    meta["coverage"] = meta["mapped_value"] / meta["book_value"].replace(0, np.nan)
    keep = meta.index[
        meta["book_value"].ge(config.min_manager_aum)
        & meta["n_positions"].ge(config.min_manager_positions)
        & meta["coverage"].ge(config.min_factor_coverage)
    ]
    d = d[d["filer_id"].isin(keep)]
    denom = d.groupby("filer_id")["value"].transform("sum")
    d["w"] = d["value"] / denom.replace(0, np.nan)
    z = x.reindex(d["ticker"]).set_axis(d.index)
    weighted = z.mul(d["w"], axis=0)
    raw = weighted.groupby(d["filer_id"]).sum(min_count=1)
    raw = raw.reindex(columns=list(config.factor_names)).dropna(how="any")
    active = raw.subtract(characteristic.benchmark_exposure, axis=1)
    meta = meta.reindex(raw.index).rename(columns={"book_value": "aum"})
    return ManagerExposure(raw=raw, active=active, metadata=meta)


def exposure_long_table(
    period: pd.Timestamp,
    decision_date: pd.Timestamp,
    qe: ManagerExposure,
    pit: ManagerExposure | None = None,
) -> pd.DataFrame:
    """Permanent manager-level product; never collapse the cross-section."""
    raw = qe.raw.stack().rename("exposure_raw")
    active = qe.active.stack().rename("exposure_active")
    out = pd.concat([raw, active], axis=1).reset_index()
    out.columns = ["filer_id", "factor", "exposure_raw", "exposure_active"]
    out["period_end"] = pd.Timestamp(period)
    out["decision_date"] = pd.Timestamp(decision_date)
    out = out.merge(qe.metadata.reset_index(), on="filer_id", how="left")
    if pit is not None:
        p = pit.active.stack().rename("exposure_pit").reset_index()
        p.columns = ["filer_id", "factor", "exposure_pit"]
        out = out.merge(p, on=["filer_id", "factor"], how="left")
    out["factor_percentile"] = out.groupby("factor")["exposure_active"].rank(pct=True)
    return out


def _aggregation_weights(meta: pd.DataFrame, scheme: str) -> pd.Series:
    if scheme == "equal":
        w = pd.Series(1.0, index=meta.index)
    elif scheme == "aum":
        w = meta["aum"].clip(lower=0)
    elif scheme == "sqrt_aum":
        w = np.sqrt(meta["aum"].clip(lower=0))
    else:
        raise ValueError(f"Unknown manager weighting scheme: {scheme}")
    return w / w.sum()


def positioning_dashboard(
    period: pd.Timestamp,
    exposure: ManagerExposure,
    threshold: float = 0.5,
) -> pd.DataFrame:
    """Position, breadth, dispersion, tails and side-specific HHI."""
    rows: list[dict] = []
    e = exposure.active
    for scheme in ("equal", "aum", "sqrt_aum"):
        w = _aggregation_weights(exposure.metadata.reindex(e.index), scheme)
        for factor in e.columns:
            x = e[factor].dropna()
            wf = w.reindex(x.index).fillna(0.0)
            wf = wf / wf.sum()
            mean = float((wf * x).sum())
            dispersion = float(np.sqrt((wf * (x - mean) ** 2).sum()))
            q25, q75 = x.quantile([0.25, 0.75])
            pos_cap = wf * x.clip(lower=0)
            neg_cap = wf * (-x.clip(upper=0))
            hhi_pos = float(((pos_cap / pos_cap.sum()) ** 2).sum()) if pos_cap.sum() else np.nan
            hhi_neg = float(((neg_cap / neg_cap.sum()) ** 2).sum()) if neg_cap.sum() else np.nan
            rows.append(
                {
                    "period_end": pd.Timestamp(period),
                    "factor": factor,
                    "weighting": scheme,
                    "position": mean,
                    "dispersion": dispersion,
                    "breadth_pos": float((wf * x.gt(threshold)).sum()),
                    "breadth_neg": float((wf * x.lt(-threshold)).sum()),
                    "tail_pos": float((wf * (x - q75).clip(lower=0)).sum()),
                    "tail_neg": float((wf * (q25 - x).clip(lower=0)).sum()),
                    "hhi_pos": hhi_pos,
                    "hhi_neg": hhi_neg,
                    "n_managers": int(len(x)),
                }
            )
    return pd.DataFrame(rows)


def _weighted_exposure(pairs: pd.DataFrame, scores: pd.DataFrame, value_col: str) -> pd.DataFrame:
    d = pairs[pairs["ticker"].isin(scores.index)].copy()
    denom = d.groupby("filer_id")[value_col].transform("sum")
    d["_w"] = d[value_col] / denom.replace(0, np.nan)
    z = scores.reindex(d["ticker"]).set_axis(d.index)
    return z.mul(d["_w"], axis=0).groupby(d["filer_id"]).sum(min_count=1)


def rotation_decomposition(
    previous_pairs: pd.DataFrame,
    current_pairs: pd.DataFrame,
    previous_exposure: ManagerExposure,
    current_exposure: ManagerExposure,
    previous_characteristic: CharacteristicSnapshot,
    current_characteristic: CharacteristicSnapshot,
    raw_price_growth: pd.Series,
) -> pd.DataFrame:
    """Exact price/characteristic/trading decomposition per manager-factor.

    The active benchmark changes only in the characteristic leg, making the
    components add exactly to the change in active exposure.
    """
    common = previous_exposure.active.index.intersection(current_exposure.active.index)
    prev = previous_pairs[previous_pairs["filer_id"].isin(common)].copy()
    prev["drift_value"] = prev["value"] * prev["ticker"].map(raw_price_growth).fillna(1.0)

    e_old = previous_exposure.raw.reindex(common)
    e_price = _weighted_exposure(prev, previous_characteristic.scores, "drift_value").reindex(common)
    e_char = _weighted_exposure(prev, current_characteristic.scores, "drift_value").reindex(common)
    e_actual = current_exposure.raw.reindex(common)

    a_old = e_old.subtract(previous_characteristic.benchmark_exposure, axis=1)
    a_price = e_price.subtract(previous_characteristic.benchmark_exposure, axis=1)
    a_char = e_char.subtract(current_characteristic.benchmark_exposure, axis=1)
    a_actual = e_actual.subtract(current_characteristic.benchmark_exposure, axis=1)

    components = {
        "price_drift": a_price - a_old,
        "characteristic_drift": a_char - a_price,
        "active_rotation": a_actual - a_char,
        "total_change": a_actual - a_old,
    }
    check = components["price_drift"] + components["characteristic_drift"] \
        + components["active_rotation"] - components["total_change"]
    max_error = float(np.nanmax(np.abs(check.to_numpy()))) if check.size else np.nan
    if np.isfinite(max_error) and max_error > 1e-9:
        raise AssertionError(f"Rotation decomposition is not exact: {max_error:g}")

    out = pd.concat(components, names=["component"]).stack().rename("value").reset_index()
    out.columns = ["component", "filer_id", "factor", "value"]
    out["aum_prev"] = out["filer_id"].map(previous_exposure.metadata["aum"])
    out["max_identity_error"] = max_error
    return out


def aggregate_rotation(
    rotation: pd.DataFrame,
    characteristic: CharacteristicSnapshot,
    adv: pd.Series,
) -> pd.DataFrame:
    """Aggregate manager rotation and express it in factor-ADV units."""
    cap = characteristic.scores.abs().mul(adv.reindex(characteristic.scores.index), axis=0).sum()
    rows = []
    for (component, factor), g in rotation.groupby(["component", "factor"]):
        aum = g["aum_prev"].clip(lower=0)
        sqrt_w = np.sqrt(aum)
        mean_sqrt = float((g["value"] * sqrt_w).sum() / sqrt_w.sum()) if sqrt_w.sum() else np.nan
        dollar = float((g["value"] * aum).sum())
        rows.append(
            {
                "component": component,
                "factor": factor,
                "aggregate_sqrt": mean_sqrt,
                "dollar_flow": dollar,
                "capacity_adv": float(cap.get(factor, np.nan)),
                "pressure": dollar / cap.get(factor, np.nan),
                "n_managers": int(g["filer_id"].nunique()),
            }
        )
    return pd.DataFrame(rows)


def implied_manager_funding_flow(
    current_snapshot: pd.DataFrame,
    previous_snapshot: pd.DataFrame,
    ticker_map: pd.Series,
    stock_total_return: pd.Series,
    min_positions: int = 15,
    min_aum: float = 100_000_000.0,
    min_coverage: float = 0.60,
) -> pd.DataFrame:
    """AUM growth minus the frozen previous book's total return."""
    ap = previous_snapshot.groupby("filer_id")["value_usd"].sum()
    ac = current_snapshot.groupby("filer_id")["value_usd"].sum()
    p = previous_snapshot.copy()
    p["ticker"] = p["instrument_id"].map(ticker_map)
    p["ret"] = p["ticker"].map(stock_total_return)
    p["covered_value"] = p["value_usd"].where(p["ret"].notna(), 0.0)
    p["return_dollar"] = p["value_usd"] * p["ret"].fillna(0.0)
    g = p.groupby("filer_id")
    total = g["value_usd"].sum().clip(lower=1.0)
    out = pd.DataFrame(
        {
            "aum_prev": ap,
            "aum_cur": ac,
            "book_return": g["return_dollar"].sum() / total,
            "coverage": g["covered_value"].sum() / total,
            "n_positions": g.size(),
        }
    ).dropna()
    out = out[
        out["n_positions"].ge(min_positions)
        & out["aum_prev"].ge(min_aum)
        & out["coverage"].ge(min_coverage)
    ]
    out["flow_pct"] = out["aum_cur"] / out["aum_prev"] - 1.0 - out["book_return"]
    out["flow_dollar"] = out["flow_pct"] * out["aum_prev"]
    return out


def funding_factor_pressure(
    flows: pd.DataFrame,
    previous_exposure: ManagerExposure,
    characteristic: CharacteristicSnapshot,
    adv: pd.Series,
) -> pd.Series:
    """Predicted funding demand sum(flow_dollar * previous active E)."""
    common = flows.index.intersection(previous_exposure.active.index)
    dollar = previous_exposure.active.loc[common].mul(flows.loc[common, "flow_dollar"], axis=0).sum()
    capacity = characteristic.scores.abs().mul(
        adv.reindex(characteristic.scores.index), axis=0
    ).sum()
    return dollar / capacity.replace(0, np.nan)
