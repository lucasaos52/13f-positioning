"""Diagnostics that distinguish a positioning mechanism from its naive baseline."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .backtesting import _nw_t


def scoped_signal_events(
    events: pd.DataFrame,
    master: pd.DataFrame,
    source: str,
    target: str,
    styles: tuple[str, ...] | None = None,
    require_column: str | None = None,
) -> pd.DataFrame:
    """Create a pre-specified ETF-style variant without changing event timing.

    Economic zeros remain sparse.  One ``__EVENT__`` marker per filing date is
    retained so the backtest reconstructs the target style universe before
    applying the observed non-zero scores.
    """

    products = master.drop_duplicates("ticker").copy()
    if styles is not None:
        products = products[products["etf_style"].isin(styles)]
    if require_column is not None:
        products = products[products[require_column].fillna(False).astype(bool)]
    allowed = set(products["ticker"].dropna().astype(str))
    source_rows = events[events["signal_name"].eq(source)].copy()
    keep = source_rows["ticker"].eq("__EVENT__") | source_rows["ticker"].isin(allowed)
    out = source_rows.loc[keep].copy()
    out["signal_name"] = target
    return out


def controlled_signal_events(
    events: pd.DataFrame,
    master: pd.DataFrame,
    market,
    mappings: dict[str, str],
) -> pd.DataFrame:
    """Residualize positioning scores on public ETF characteristics.

    This implements the blueprint's evaluation control rather than fitting a
    return model.  Each filing-date cross-section uses contemporaneously
    public price history only; no future return enters the regression.
    """

    products = master.drop_duplicates("ticker").set_index("ticker")
    tickers = products.index.intersection(market.prices.columns)
    prices = market.prices[tickers]
    raw_prices = market.prices_raw[tickers]
    returns = market.returns[tickers]
    spy = market.returns["SPY"]

    momentum = prices.div(prices.shift(63)).sub(1.0)
    volatility = market.volatility[tickers]
    mean_x = returns.rolling(126, min_periods=60).mean()
    mean_y = spy.rolling(126, min_periods=60).mean()
    mean_xy = returns.mul(spy, axis=0).rolling(126, min_periods=60).mean()
    beta = (mean_xy - mean_x.mul(mean_y, axis=0)).div(
        spy.rolling(126, min_periods=60).var(ddof=0), axis=0
    )
    log_adv = np.log1p(
        market.dollar_volume[tickers].rolling(63, min_periods=40).median()
    )
    log_price = np.log(raw_prices.where(raw_prices.gt(0.0)))
    log_age = np.log1p(prices.notna().cumsum())
    numeric_panels = {
        "momentum_63d": momentum,
        "volatility_63d": volatility,
        "beta_126d": beta,
        "log_adv_63d": log_adv,
        "log_price": log_price,
        "log_age": log_age,
    }
    styles = pd.get_dummies(
        products.reindex(tickers)["etf_style"], prefix="style", dtype=float, drop_first=True
    )
    selected = events[
        events["signal_name"].isin(mappings) & events["ticker"].ne("__EVENT__")
    ].copy()
    rows: list[pd.DataFrame] = []
    for available, date_group in selected.groupby("available_date", sort=True):
        available = pd.Timestamp(available)
        i = int(prices.index.searchsorted(available, side="right") - 1)
        if i < 0:
            continue
        controls = pd.DataFrame(
            {name: panel.iloc[i].reindex(tickers) for name, panel in numeric_panels.items()},
            index=tickers,
        )
        for column in controls:
            value = controls[column].replace([np.inf, -np.inf], np.nan)
            if value.notna().sum() < 3:
                controls[column] = np.nan
                continue
            lo, hi = value.quantile([0.01, 0.99])
            value = value.clip(lo, hi)
            std = value.std(ddof=1)
            controls[column] = (value - value.mean()) / std if std > 0 else 0.0
        controls = controls.join(styles)
        period_end = date_group["period_end"].dropna().max()
        for source, target in mappings.items():
            observed = (
                date_group[date_group["signal_name"].eq(source)]
                .groupby("ticker")["signal"]
                .last()
            )
            score = pd.Series(0.0, index=tickers, dtype=float)
            score.update(observed)
            y = np.log1p(score.clip(lower=0.0))
            valid = y.notna() & controls.notna().all(axis=1)
            if valid.sum() < max(20, controls.shape[1] + 5):
                continue
            design = np.column_stack(
                [np.ones(valid.sum()), controls.loc[valid].to_numpy(dtype=float)]
            )
            fitted = design @ np.linalg.lstsq(
                design, y.loc[valid].to_numpy(dtype=float), rcond=None
            )[0]
            residual = y.loc[valid].to_numpy(dtype=float) - fitted
            rows.append(
                pd.DataFrame(
                    {
                        "period_end": period_end,
                        "available_date": available,
                        "ticker": y.index[valid],
                        "signal_name": target,
                        "signal": residual,
                    }
                )
            )
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def paired_return_diagnostics(
    returns: pd.DataFrame,
    pairs: tuple[tuple[str, str], ...],
    fee_bps: int,
) -> pd.DataFrame:
    """Test whether a structural score adds return beyond its naive baseline."""

    selected = returns[returns["fee_bps"].eq(fee_bps)].pivot(
        index="date", columns="strategy", values="return"
    )
    selected.index = pd.to_datetime(selected.index)
    rows: list[dict[str, float | str]] = []
    first = selected.index.min()
    samples = (
        ("full", first, None),
        ("pre_2022", first, pd.Timestamp("2021-12-31")),
        ("post_2021", pd.Timestamp("2022-01-01"), None),
    )
    for structural, baseline in pairs:
        if structural not in selected or baseline not in selected:
            continue
        for sample, start, end in samples:
            block = selected.loc[start:end, [structural, baseline]].dropna()
            if block.empty:
                continue
            spread = block[structural] - block[baseline]
            vol = float(spread.std(ddof=1) * np.sqrt(252))
            ann_mean = float(spread.mean() * 252)
            rows.append(
                {
                    "structural": structural,
                    "baseline": baseline,
                    "sample": sample,
                    "n_days": len(block),
                    "return_correlation": float(block.corr().iloc[0, 1]),
                    "incremental_ann_return": ann_mean,
                    "incremental_ann_vol": vol,
                    "incremental_sharpe": ann_mean / vol if vol > 0 else np.nan,
                    "incremental_mean_t_nw": _nw_t(spread, 5),
                }
            )
    return pd.DataFrame(rows)


def paired_ic_diagnostics(
    raw_ic: pd.DataFrame,
    pairs: tuple[tuple[str, str], ...],
) -> pd.DataFrame:
    """Paired event test of structural IC minus naive-baseline IC."""

    rows: list[dict[str, float | str]] = []
    for structural, baseline in pairs:
        left = raw_ic[raw_ic["signal_name"].eq(structural)]
        right = raw_ic[raw_ic["signal_name"].eq(baseline)]
        paired = left.merge(
            right,
            on=["available_date", "horizon_days"],
            suffixes=("_structural", "_baseline"),
        )
        for horizon, block in paired.groupby("horizon_days"):
            delta = block["ic_structural"] - block["ic_baseline"]
            rows.append(
                {
                    "structural": structural,
                    "baseline": baseline,
                    "horizon_days": int(horizon),
                    "n_paired_events": len(delta),
                    "mean_incremental_ic": float(delta.mean()),
                    "incremental_ic_t_nw": _nw_t(delta, max(1, int(horizon // 5))),
                }
            )
    return pd.DataFrame(rows)


def portfolio_exposure_diagnostics(portfolios: list) -> pd.DataFrame:
    """Summarize legs and realized exposure on actual rebalance dates."""

    rows = []
    for portfolio in portfolios:
        idx = np.asarray(portfolio.rb_dates, dtype=int)
        weights = portfolio.weights.iloc[idx]
        active = weights.abs().sum(axis=1).gt(0)
        weights = weights.loc[active]
        if weights.empty:
            continue
        long = weights.clip(lower=0.0)
        short = weights.clip(upper=0.0)
        rows.append(
            {
                "strategy": portfolio.name,
                "n_rebalances": len(weights),
                "median_long_names": float(long.gt(0).sum(axis=1).median()),
                "median_short_names": float(short.lt(0).sum(axis=1).median()),
                "mean_long_exposure": float(long.sum(axis=1).mean()),
                "mean_short_exposure": float(-short.sum(axis=1).mean()),
                "mean_net_exposure": float(weights.sum(axis=1).mean()),
                "max_abs_net_exposure": float(weights.sum(axis=1).abs().max()),
            }
        )
    return pd.DataFrame(rows)


def factor_regressions(
    returns: pd.DataFrame,
    market_returns: pd.DataFrame,
    fee_bps: int,
) -> pd.DataFrame:
    """OLS attribution to market, small-cap and technology ETF factors."""

    strategies = returns[returns["fee_bps"].eq(fee_bps)].pivot(
        index="date", columns="strategy", values="return"
    )
    strategies.index = pd.to_datetime(strategies.index)
    factors = pd.DataFrame(
        {
            "market_beta": market_returns["SPY"],
            "small_tilt": market_returns["IWM"] - market_returns["SPY"],
            "tech_tilt": market_returns["QQQ"] - market_returns["SPY"],
        }
    )
    rows = []
    first = strategies.index.min()
    samples = (
        ("full", first, None),
        ("pre_2022", first, pd.Timestamp("2021-12-31")),
        ("post_2021", pd.Timestamp("2022-01-01"), None),
    )
    for strategy in strategies:
        joined = pd.concat([strategies[strategy].rename("y"), factors], axis=1).dropna()
        for sample, start, end in samples:
            block = joined.loc[start:end]
            if len(block) < 60:
                continue
            x = np.column_stack([np.ones(len(block)), block[factors.columns].to_numpy()])
            beta = np.linalg.lstsq(x, block["y"].to_numpy(), rcond=None)[0]
            residual = block["y"].to_numpy() - x @ beta
            rows.append(
                {
                    "strategy": strategy,
                    "sample": sample,
                    "n_days": len(block),
                    "annual_alpha_arithmetic": float(beta[0] * 252),
                    "residual_ann_vol": float(np.std(residual, ddof=1) * np.sqrt(252)),
                    "market_beta": float(beta[1]),
                    "small_tilt": float(beta[2]),
                    "tech_tilt": float(beta[3]),
                    "r_squared": float(1.0 - np.var(residual) / np.var(block["y"])),
                }
            )
    return pd.DataFrame(rows)


def calendar_returns(returns: pd.DataFrame, fee_bps: int) -> pd.DataFrame:
    """Compounded strategy returns by calendar year."""

    selected = returns[returns["fee_bps"].eq(fee_bps)].copy()
    selected["date"] = pd.to_datetime(selected["date"])
    selected["year"] = selected["date"].dt.year
    return (
        selected.groupby(["strategy", "year"])["return"]
        .apply(lambda x: float((1.0 + x).prod() - 1.0))
        .rename("return")
        .reset_index()
    )
