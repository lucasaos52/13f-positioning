"""The five ETF-positioning hypotheses and their causal ablations."""

from __future__ import annotations

import numpy as np
import pandas as pd


def cross_sectional_z(series: pd.Series) -> pd.Series:
    x = series.astype(float).replace([np.inf, -np.inf], np.nan)
    if x.notna().sum() < 3:
        return pd.Series(np.nan, index=x.index)
    lo, hi = x.quantile([0.01, 0.99])
    x = x.clip(lo, hi)
    std = x.std(ddof=1)
    return (x - x.mean()) / std if std and np.isfinite(std) else pd.Series(np.nan, index=x.index)


def abnormal_breadth(
    state: pd.DataFrame,
    public_features: pd.DataFrame,
    master: pd.DataFrame,
) -> pd.Series:
    """Cross-sectional OLS residual of log breadth on mechanical ETF traits.

    Controls are public and lag-free as of the filing event: disclosed ETF
    position value, momentum, volatility, beta, ADV, price, age and style.
    Regressors are standardized after 1/99 winsorization. No future breadth or
    return is used to fit the quarter/event regression.
    """

    x = state[["n_holders", "state_value"]].join(public_features, how="left")
    products = master.drop_duplicates("ticker").set_index("ticker")
    x = x.join(products[["etf_style"]], how="left")
    x["log_breadth"] = np.log1p(x["n_holders"].clip(lower=0.0))
    x["log_ownership_value"] = np.log1p(x["state_value"].clip(lower=0.0))
    numeric = [
        "log_ownership_value",
        "momentum_63d",
        "volatility_63d",
        "beta_126d",
        "log_adv_63d",
        "log_price",
        "log_age",
    ]
    controls = pd.DataFrame(index=x.index)
    for col in numeric:
        s = x[col].replace([np.inf, -np.inf], np.nan)
        if s.notna().sum() >= 3:
            lo, hi = s.quantile([0.01, 0.99])
            s = s.clip(lo, hi)
            std = s.std(ddof=1)
            controls[col] = (s - s.mean()) / std if std and np.isfinite(std) else 0.0
    styles = pd.get_dummies(x["etf_style"], prefix="style", dtype=float, drop_first=True)
    controls = controls.join(styles)
    valid = x["log_breadth"].notna() & controls.notna().all(axis=1)
    if valid.sum() < max(12, controls.shape[1] + 5):
        return pd.Series(np.nan, index=x.index)
    design = np.column_stack([np.ones(valid.sum()), controls.loc[valid].to_numpy(dtype=float)])
    y = x.loc[valid, "log_breadth"].to_numpy(dtype=float)
    fitted = design @ np.linalg.lstsq(design, y, rcond=None)[0]
    out = pd.Series(np.nan, index=x.index, dtype=float)
    out.loc[valid] = y - fitted
    return out


def score_event_state(
    state: pd.DataFrame,
    flow: pd.DataFrame,
    public_features: pd.DataFrame,
    residual_shock: pd.Series,
    market_stress: bool,
    previous_abnormal: pd.Series,
    master: pd.DataFrame,
) -> pd.DataFrame:
    """Return all primary scores and pre-specified ablations for one event."""

    products = master.drop_duplicates("ticker").set_index("ticker")
    out = state.join(flow, how="outer").reindex(products.index).fillna(
        {
            "state_value": 0.0,
            "fragility_owner_value": 0.0,
            "n_holders": 0.0,
            "churn_value": 0.0,
            "ccp_state": 0.0,
            "consensus_state": 0.0,
            "sticky_raw": 0.0,
            "sticky_quality": 0.0,
            "sticky_specificity": 0.0,
            "double_down_all": 0.0,
            "double_down_specific": 0.0,
            "new_holder_breadth": 0.0,
        }
    )
    if "fragility_owner_value" not in out:
        out["fragility_owner_value"] = out["state_value"]
    abnormal = abnormal_breadth(out, public_features, master)
    out["abnormal_level"] = abnormal
    out["abnormal_adoption"] = abnormal - previous_abnormal.reindex(out.index)
    specific = products["is_specific"].reindex(out.index).fillna(False)
    out["double_down_specific"] = out["double_down_specific"].where(specific)
    out["ccp"] = out["ccp_state"]
    out["consensus"] = out["consensus_state"]
    out["fragility"] = out["churn_value"] / out["fragility_owner_value"].replace(0.0, np.nan)
    frag_z = cross_sectional_z(out["fragility"])
    shock_z = cross_sectional_z(residual_shock.reindex(out.index))
    out["fragility_unconditional"] = frag_z
    out["fragility_stress"] = -frag_z if market_stress else np.nan
    out["fragility_reversal"] = frag_z * (-shock_z).clip(lower=0.0)
    return out


PRIMARY_SIGNALS = (
    "sticky_quality",
    "double_down_specific",
    "abnormal_adoption",
    "ccp",
    "fragility_stress",
    "fragility_reversal",
)

ABLATION_SIGNALS = (
    "sticky_raw",
    "sticky_specificity",
    "double_down_all",
    "abnormal_level",
    "new_holder_breadth",
    "consensus",
    "fragility_unconditional",
)

# These signals define absence of a qualifying manager action as an economic
# zero, rather than missing information.  Event storage can omit those zeros
# as long as portfolio/IC reconstruction restores the appropriate product
# universe at each filing event.
ZERO_BASED_SIGNALS = (
    "sticky_quality",
    "sticky_raw",
    "sticky_specificity",
    "double_down_all",
    "double_down_specific",
    "ccp",
    "ccp_specific",
    "ccp_passive",
    "consensus",
    "consensus_specific",
    "consensus_passive",
    "new_holder_breadth",
)
