"""Point-in-time market-data characteristics for the Tier-0 factor set."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import ResearchConfig


@dataclass
class CharacteristicSnapshot:
    date: pd.Timestamp
    scores: pd.DataFrame
    raw: pd.DataFrame
    benchmark_weights: pd.Series
    benchmark_exposure: pd.Series
    quality: dict[str, float]


def winsor_z(s: pd.Series, low: float = 0.01, high: float = 0.99) -> pd.Series:
    """Finite-only winsorized cross-sectional z-score."""
    x = pd.to_numeric(s, errors="coerce").replace([np.inf, -np.inf], np.nan)
    ok = x.dropna()
    out = pd.Series(np.nan, index=s.index, dtype=float)
    if len(ok) < 20:
        return out
    lo, hi = ok.quantile([low, high])
    clipped = ok.clip(lo, hi)
    sd = clipped.std(ddof=1)
    if not np.isfinite(sd) or sd <= 0:
        return out
    out.loc[clipped.index] = (clipped - clipped.mean()) / sd
    return out


def _row_at_or_before(panel: pd.DataFrame, date: pd.Timestamp) -> tuple[int, pd.Series]:
    i = panel.index.searchsorted(pd.Timestamp(date), side="right") - 1
    if i < 0:
        raise ValueError(f"No market data at or before {date}")
    return i, panel.iloc[i]


def build_characteristics(
    date: pd.Timestamp | str,
    market_data,
    market_cap: pd.DataFrame,
    config: ResearchConfig,
) -> CharacteristicSnapshot:
    """Build SIZE/MOM/BETA/LOWVOL/LIQ using information through ``date``.

    Market-cap inputs from free Yahoo share histories contain split artifacts
    in the deep history.  Impossible values are rejected and benchmark caps
    are winsorized at the configured upper percentile.  Cross-sectional
    factor scores are winsorized independently, so one bad microcap cannot set
    either the factor coordinate or the benchmark.
    """
    date = pd.Timestamp(date)
    i, px = _row_at_or_before(market_data.prices, date)
    if i < config.min_history_days:
        raise ValueError(f"Insufficient market history for {date}")

    raw_px = market_data.prices_raw.iloc[i]
    cap = market_cap.reindex(index=market_data.prices.index).iloc[i]
    adv = (
        market_data.dollar_volume.iloc[max(0, i - 62) : i + 1]
        .median()
        .replace(0, np.nan)
    )
    mom = market_data.prices.iloc[i - 21] / market_data.prices.iloc[i - 252] - 1.0

    r = market_data.returns.iloc[i - 251 : i + 1].replace(
        [np.inf, -np.inf], np.nan
    )
    b = market_data.benchmark_returns.reindex(r.index).replace(
        [np.inf, -np.inf], np.nan
    )
    b_dm = b - b.mean()
    r_dm = r.subtract(r.mean(), axis=1)
    b_var = float((b_dm**2).sum())
    beta = r_dm.mul(b_dm, axis=0).sum() / b_var if b_var > 0 else pd.Series(
        np.nan, index=r.columns
    )
    fitted = pd.DataFrame(
        np.outer(b.to_numpy(float), beta.to_numpy(float)),
        index=r.index,
        columns=r.columns,
    )
    resid = r - fitted
    resid_vol = resid.std(ddof=1) * np.sqrt(252)

    history_ok = (
        market_data.prices.iloc[i - config.min_history_days + 1 : i + 1]
        .notna()
        .mean()
        .ge(0.90)
    )
    finite_cap = cap.where(np.isfinite(cap))
    cap_ok = finite_cap.between(config.market_cap_floor, config.market_cap_ceiling)
    eligible = (
        raw_px.ge(config.characteristic_min_price)
        & adv.ge(config.characteristic_min_adv)
        & history_ok
        & cap_ok
    ).fillna(False)

    raw = pd.DataFrame(
        {
            "size": -np.log(finite_cap.where(finite_cap > 0)),
            "momentum": mom,                         # positive = 12-1 winner
            "beta": beta,                            # positive = high beta
            "lowvol": -resid_vol,                    # positive = defensive
            "liquidity": np.log(adv.where(adv > 0)),
        }
    ).where(eligible)
    scores = pd.DataFrame(
        {
            c: winsor_z(raw[c], config.winsor_low, config.winsor_high)
            for c in config.factor_names
        }
    ).dropna(how="any")

    cap_b = finite_cap.reindex(scores.index).dropna()
    if len(cap_b) < 50:
        raise ValueError(f"Too few eligible stocks at {date}: {len(cap_b)}")
    cap_limit = cap_b.quantile(config.benchmark_cap_winsor)
    cap_b = cap_b.clip(upper=cap_limit)
    benchmark_weights = cap_b / cap_b.sum()
    benchmark_exposure = scores.mul(benchmark_weights, axis=0).sum()

    return CharacteristicSnapshot(
        date=market_data.prices.index[i],
        scores=scores,
        raw=raw.reindex(scores.index),
        benchmark_weights=benchmark_weights,
        benchmark_exposure=benchmark_exposure,
        quality={
            "n_scores": float(len(scores)),
            "n_cap_rejected": float((~cap_ok & cap.notna()).sum()),
            "benchmark_cap_limit": float(cap_limit),
        },
    )


def cross_sectional_z(s: pd.Series) -> pd.Series:
    """Small-K standardization used only across factors at one date."""
    x = s.replace([np.inf, -np.inf], np.nan)
    sd = x.std(ddof=1)
    return (x - x.mean()) / sd if np.isfinite(sd) and sd > 0 else x * 0.0


def factor_mimicking_return(scores: pd.DataFrame, forward: pd.Series) -> pd.Series:
    """Split-normalized long/short return for each characteristic."""
    out = {}
    for factor in scores:
        d = pd.concat([scores[factor].rename("z"), forward.rename("r")], axis=1).dropna()
        pos, neg = d["z"].clip(lower=0), -d["z"].clip(upper=0)
        if pos.sum() == 0 or neg.sum() == 0:
            out[factor] = np.nan
        else:
            w = pos / pos.sum() - neg / neg.sum()
            out[factor] = float((w * d["r"]).sum())
    return pd.Series(out, dtype=float)
