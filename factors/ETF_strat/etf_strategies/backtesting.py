"""Adapters to the repository's multifactor Portfolio/Backtest mechanics."""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from .signals import ZERO_BASED_SIGNALS


def _zero_tickers(name: str, master: pd.DataFrame | None) -> pd.Index | None:
    """Product scope whose omitted sparse observations mean economic zero."""

    if name not in ZERO_BASED_SIGNALS or master is None:
        return None
    products = master.drop_duplicates("ticker")
    if name.endswith("_specific"):
        products = products[products["is_specific"].fillna(False).astype(bool)]
    elif name.endswith("_passive"):
        products = products[
            products["is_passive_equity_etf"].fillna(False).astype(bool)
        ]
    return pd.Index(products["ticker"].dropna().astype(str).unique())


def build_tradable_universe(market, filters_cls, cfg):
    """Use the shared liquidity/history filter with ETF-sized thresholds."""

    return filters_cls(
        market,
        min_price=cfg.min_price,
        min_dollar_volume=cfg.min_dollar_volume,
        liquidity_window=cfg.liquidity_window_days,
        min_history_days=cfg.min_history_days,
        min_stocks=10,
    ).universe


def event_signal_to_portfolio(
    name: str,
    events: pd.DataFrame,
    market,
    universe: pd.DataFrame,
    indicator_cls,
    portfolio_cls,
    cfg,
    master: pd.DataFrame | None = None,
):
    """Release on first trading close after filing date, then earn next day."""

    subset = events[events["signal_name"].eq(name)].dropna(subset=["signal"]).copy()
    if subset.empty:
        return None
    dates = market.prices.index
    values, event_indices = prepare_event_values(
        name, subset, dates, market.prices.columns, _zero_tickers(name, master)
    )
    if not event_indices:
        return None
    indicator = indicator_cls(name, values=values)
    indicator.filter_values(universe).generate_z_scores().clip_scores(-3.0, 3.0)
    min_names = 4 if "double_down" in name else 8
    portfolio = portfolio_cls.from_indicator(
        name,
        indicator.scores,
        universe,
        side="HML",
        pct=cfg.quantile_fraction,
        min_stocks=min_names,
    )
    portfolio.rebalance(np.asarray(sorted(set(event_indices)), dtype=int), market.prices)
    return portfolio


def prepare_event_values(
    name: str,
    subset: pd.DataFrame,
    dates: pd.DatetimeIndex,
    columns: pd.Index,
    zero_tickers: pd.Index | None = None,
) -> tuple[pd.DataFrame, list[int]]:
    """Translate dated public signals into target dates and holding cohorts."""

    is_stress = name == "fragility_stress"
    values = pd.DataFrame(0.0 if is_stress else np.nan, index=dates, columns=columns)
    event_indices: list[int] = []
    for available, group in subset.groupby("available_date", sort=True):
        i = int(dates.searchsorted(pd.Timestamp(available), side="right"))
        if i >= len(dates):
            continue
        if zero_tickers is not None:
            baseline = zero_tickers.intersection(values.columns)
            values.loc[dates[i], baseline] = 0.0
        score = group[group["ticker"].ne("__EVENT__")].groupby("ticker")["signal"].last()
        common = score.index.intersection(values.columns)
        values.loc[dates[i], common] = score.reindex(common)
        event_indices.append(i)
    if not event_indices:
        return values, []
    values = values.ffill()
    if name == "fragility_reversal":
        # Overlapping 21-day cohorts align the portfolio with the memo's
        # 20-day post-selloff reversal horizon. Daily replacement would test
        # a different one-day hypothesis and manufacture turnover.
        values = values.rolling(21, min_periods=1).mean()
    if is_stress:
        first = min(event_indices)
        event_indices = list(range(first, len(dates)))
    return values, event_indices


def run_shared_backtest(
    events: pd.DataFrame,
    market,
    universe: pd.DataFrame,
    signal_names: list[str],
    indicator_cls,
    portfolio_cls,
    backtest_cls,
    cfg,
    master: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, list]:
    portfolios = []
    for name in signal_names:
        portfolio = event_signal_to_portfolio(
            name, events, market, universe, indicator_cls, portfolio_cls, cfg, master
        )
        if portfolio is not None:
            portfolios.append(portfolio)
    if not portfolios:
        return pd.DataFrame(), pd.DataFrame(), []
    engine = backtest_cls(portfolios)
    summaries, returns = [], []
    start = pd.Timestamp(events["available_date"].min())
    for bps in cfg.fee_ladder_bps:
        samples = [("full", start, None)]
        if start < pd.Timestamp("2022-01-01"):
            samples.extend(
                [
                    ("pre_2022", start, pd.Timestamp("2021-12-31")),
                    ("post_2021", pd.Timestamp("2022-01-01"), None),
                ]
            )
        for sample, sample_start, sample_end in samples:
            summary = engine.performance_analysis(
                market,
                trading_fee=bps / 10_000.0,
                cash_leg=market.treasury_yield,
                start=sample_start,
                end=sample_end,
            ).reset_index(names="strategy")
            summary["fee_bps"] = bps
            summary["sample"] = sample
            summaries.append(summary)
        r = engine.get_returns(
            market, trading_fee=bps / 10_000.0, cash_leg=market.treasury_yield
        ).loc[start:]
        long = r.stack().rename("return").reset_index()
        long.columns = ["date", "strategy", "return"]
        long["fee_bps"] = bps
        returns.append(long)
    return pd.concat(summaries, ignore_index=True), pd.concat(returns, ignore_index=True), portfolios


def _nw_t(values: pd.Series, maxlags: int) -> float:
    y = values.dropna().to_numpy(dtype=float)
    if len(y) < 8:
        return np.nan
    demeaned = y - y.mean()
    n = len(y)
    lags = min(maxlags, n - 2)
    long_run = float(demeaned @ demeaned / n)
    for lag in range(1, lags + 1):
        gamma = float(demeaned[lag:] @ demeaned[:-lag] / n)
        long_run += 2.0 * (1.0 - lag / (lags + 1.0)) * gamma
    variance_mean = long_run / n
    return float(y.mean() / np.sqrt(variance_mean)) if variance_mean > 0 else np.nan


def forward_ic_detail(
    events: pd.DataFrame,
    prices: pd.DataFrame,
    horizons: tuple[int, ...],
    master: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Event-time cross-sectional IC observations with no same-day return."""

    rows = []
    for (name, available), group in events.groupby(["signal_name", "available_date"], sort=True):
        observed = group[group["ticker"].ne("__EVENT__")].groupby("ticker")["signal"].last()
        zeros = _zero_tickers(name, master)
        if zeros is not None:
            signal = pd.Series(0.0, index=zeros, dtype=float)
            signal.update(observed)
        else:
            signal = observed
        signal = signal.dropna()
        i = int(prices.index.searchsorted(pd.Timestamp(available), side="right"))
        if i >= len(prices):
            continue
        for horizon in horizons:
            j = i + horizon
            if j >= len(prices):
                continue
            fwd = prices.iloc[j].div(prices.iloc[i]).sub(1.0).reindex(signal.index)
            both = pd.concat([signal.rename("signal"), fwd.rename("forward")], axis=1).dropna()
            if len(both) < 8 or both["signal"].nunique() < 4:
                continue
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                ic = float(spearmanr(both["signal"], both["forward"]).statistic)
            rows.append(
                {
                    "signal_name": name,
                    "available_date": pd.Timestamp(available),
                    "horizon_days": horizon,
                    "n_names": len(both),
                    "ic": ic,
                }
            )
    return pd.DataFrame(rows)


def summarize_forward_ic(raw: pd.DataFrame) -> pd.DataFrame:
    """Aggregate event ICs with a horizon-aware Newey-West t-statistic."""

    if raw.empty:
        return raw
    summary = (
        raw.groupby(["signal_name", "horizon_days"])
        .agg(n_events=("ic", "size"), median_names=("n_names", "median"), mean_ic=("ic", "mean"))
        .reset_index()
    )
    summary["ic_t_nw"] = [
        _nw_t(
            raw[(raw["signal_name"].eq(row.signal_name)) & (raw["horizon_days"].eq(row.horizon_days))]["ic"],
            max(1, int(row.horizon_days // 5)),
        )
        for row in summary.itertuples()
    ]
    return summary


def forward_ic(
    events: pd.DataFrame,
    prices: pd.DataFrame,
    horizons: tuple[int, ...],
    master: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Event-time cross-sectional IC summary with no same-day return."""

    return summarize_forward_ic(forward_ic_detail(events, prices, horizons, master))
