"""Run the classical 13F factor-positioning research pipeline.

Usage
-----
    python run_research.py --smoke
    python run_research.py

Chosen hypotheses (pre-registered from the memo):

H1  aggregate factor position is persistent (measurement/state);
H2  active manager rotation is persistent one quarter ahead;
H3  active factor-flow pressure predicts short-horizon continuation;
H4  static crowding alone has no stable directional return sign (placebo);
H5  adverse funding flow is more damaging when aligned against a crowded
    factor position.

H6 rebalancing mismatch is intentionally deferred: another local experiment
already finds its trading mechanism but no return edge, while the foundational
exposure/flow layer still needed a PIT-safe, costed implementation.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from datetime import datetime

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
FACTORS_ROOT = HERE.parent
REPO_ROOT = FACTORS_ROOT.parent
sys.path[:0] = [str(HERE), str(FACTORS_ROOT), str(FACTORS_ROOT / "general_plan")]

from classical_positioning.backtesting import event_scores_to_portfolio, run_cost_ladder
from classical_positioning.characteristics import (
    build_characteristics,
    cross_sectional_z,
    factor_mimicking_return,
)
from classical_positioning.config import ResearchConfig
from classical_positioning.exposures import (
    aggregate_rotation,
    drift_snapshot_values,
    exposure_long_table,
    funding_factor_pressure,
    holdings_to_pairs,
    implied_manager_funding_flow,
    manager_exposures,
    positioning_dashboard,
    rotation_decomposition,
)
from classical_positioning.inference import (
    circular_block_bootstrap_mean,
    clustered_panel_ols,
)
from classical_positioning.pit import PITQuarterStore

from backtest import Backtest
from filters import Filters
from indicator import Indicator
from market_data import MarketData
from portfolio import Portfolio
import market_cap as market_cap_tools


DATA = HERE / "data"
RESULTS = HERE / "results"
QUARTERS = FACTORS_ROOT / "general_plan" / "data" / "quarters"
MAP_FILE = REPO_ROOT / "notebooks" / "data" / "cm_map_wide.csv"


def log(message: str) -> None:
    print(f"{datetime.now():%H:%M:%S} - {message}", flush=True)


def load_inputs(config: ResearchConfig):
    ticker_map = (
        pd.read_csv(MAP_FILE, dtype=str)
        .dropna(subset=["instrument_id", "ticker"])
        .drop_duplicates("instrument_id", keep="last")
        .set_index("instrument_id")["ticker"]
    )
    old_cwd = Path.cwd()
    try:
        os.chdir(FACTORS_ROOT)
        market = MarketData(
            sorted(ticker_map.unique()),
            start="2012-06-01",
            benchmark="SPY",
            borrow_rate=config.borrow_rate,
            cache_dir=FACTORS_ROOT / "data",
        )
    finally:
        os.chdir(old_cwd)
    shares = market_cap_tools.shares_panel(
        market.prices.index,
        market.tickers,
        market.prices,
        market.prices_raw,
    )
    market_cap = market_cap_tools.mktcap_panel(market.prices_raw, shares)
    return ticker_map, market, market_cap


def total_returns_between(prices: pd.DataFrame, start, end) -> pd.Series:
    """Compounded stock return from the first cut close to the second cut."""
    i0 = prices.index.searchsorted(pd.Timestamp(start), side="right")
    i1 = prices.index.searchsorted(pd.Timestamp(end), side="right")
    if i0 >= len(prices) or i1 >= len(prices) or i1 <= i0:
        return pd.Series(dtype=float)
    return prices.iloc[i1] / prices.iloc[i0] - 1.0


def price_growth_between(prices: pd.DataFrame, start, end) -> pd.Series:
    i0 = prices.index.searchsorted(pd.Timestamp(start), side="right") - 1
    i1 = prices.index.searchsorted(pd.Timestamp(end), side="right") - 1
    if i0 < 0 or i1 <= i0:
        return pd.Series(1.0, index=prices.columns)
    return prices.iloc[i1] / prices.iloc[i0]


def _manager_synthetic_check(characteristic, config, period) -> list[dict]:
    checks = []
    for factor in ("momentum", "size", "lowvol"):
        names = characteristic.scores[factor].nlargest(
            max(int(len(characteristic.scores) * 0.10), 20)
        ).index
        value = float(characteristic.scores.loc[names, factor].mean())
        checks.append(
            {
                "period_end": pd.Timestamp(period),
                "book": f"top_decile_{factor}",
                "factor": factor,
                "exposure": value,
                # A top-decile standardized basket need not exceed exactly
                # one sigma when the distribution is skewed/winsorized; the
                # test pins direction and economically material magnitude.
                "passed": bool(value > 0.75),
            }
        )
    return checks


def _write_report(
    config: ResearchConfig,
    exposures: pd.DataFrame,
    dashboard: pd.DataFrame,
    panel: pd.DataFrame,
    tests: pd.DataFrame,
    backtests: pd.DataFrame,
    validations: pd.DataFrame,
    coverage_audit: pd.DataFrame,
    diagnostics: dict,
) -> None:
    primary_terms = tests.set_index(["hypothesis", "term"])
    verdicts = []
    verdict_specs = [
        ("H1_position_persistence", "position", "positive", "state persistence"),
        ("H2_rotation_persistence", "rotation", "positive", "rotation persistence"),
        ("H3_flow_continuation", "pressure_cs_z", "positive", "flow continuation"),
        ("H4_static_crowding_placebo", "position_cs_z", "null", "static-crowding placebo"),
        (
            "H5_adverse_flow_x_crowding",
            "adverse_x_vulnerability",
            "negative",
            "adverse flow x crowding",
        ),
    ]
    for hypothesis, term, expected, label in verdict_specs:
        row = primary_terms.loc[(hypothesis, term)]
        coef, tstat = float(row["coef"]), float(row["t"])
        supported = (
            (expected == "positive" and coef > 0 and tstat > 2)
            or (expected == "negative" and coef < 0 and tstat < -2)
            or (expected == "null" and abs(tstat) < 2)
        )
        verdicts.append(
            f"- {label}: {'SUPPORTED' if supported else 'NOT SUPPORTED'} "
            f"(b={coef:+.4f}, t={tstat:+.2f}; expected {expected})."
        )

    audit_summary = coverage_audit.groupby("threshold").agg(
        quarters_ge_50=("n_managers", lambda s: int((s >= 50).sum())),
        median_managers=("n_managers", "median"),
    )
    n_panel_quarters = int(panel["period_end"].nunique() - 1)  # final row has no fwd return
    lines = [
        "# Classical 13F factor positioning — results",
        "",
        f"Run `{config.fingerprint()}`. Holdings are folded by CIK and observed at "
        f"quarter-end + {config.decision_lag_days} calendar days; trading starts on "
        "the next market date. Static crowding is a placebo/risk state, not a short rule.",
        "",
        "## Scope chosen before looking at returns",
        "",
        "Implemented H1–H5 using SIZE, MOMENTUM, BETA, LOWVOL and LIQUIDITY. "
        "Accounting factors and sector-neutral variants are excluded because no "
        "point-in-time fundamentals/sector history exists locally. H3 and H5 are "
        "the directional hypotheses; H1 measures state and H4 is the required placebo.",
        "",
        "## Data and measurement validation",
        "",
        f"- Exposure infrastructure: {exposures['period_end'].nunique()} quarter snapshots; "
        f"{exposures['filer_id'].nunique()} managers; "
        f"median {exposures.groupby('period_end')['filer_id'].nunique().median():.0f} managers/quarter.",
        f"- Directional flow panel: {panel['period_end'].nunique()} quarter snapshots; "
        f"median {panel.groupby('period_end')['n_managers'].max().median():.0f} managers/quarter "
        "after requiring both adjacent quarters to have >=50 eligible managers.",
        f"- Synthetic sign checks passed: {int(validations['passed'].sum())}/"
        f"{len(validations)}.",
        f"- Maximum rotation identity error: {diagnostics.get('max_rotation_identity_error', np.nan):.3e}.",
        f"- Mean rejected impossible market caps/date: "
        f"{diagnostics.get('mean_cap_rejected', np.nan):.1f}.",
        "- Coverage sensitivity (quarters with >=50 eligible managers | median managers): "
        + "; ".join(
            f"{int(100 * threshold)}%: {int(row.quarters_ge_50)} | {row.median_managers:.0f}"
            for threshold, row in audit_summary.iterrows()
        )
        + ".",
        "",
        "The market-cap benchmark uses a 99th-percentile cap because the free Yahoo "
        "share history contains split artifacts. This is preferable to allowing "
        "multi-quadrillion-dollar phantom firms to dominate the baseline, but it is "
        "still a documented data-quality approximation.",
        "",
        "## Pre-registered hypothesis tests",
        "",
        tests.round(5).to_markdown(index=False),
        "",
        "### Verdict at the registered sign",
        "",
        *verdicts,
        "",
        "Interpret signs as registered: H1/H2/H3 positive; H4 near zero; H5 "
        f"interaction negative. Statistical evidence is descriptive with only {n_panel_quarters} "
        "forward-return quarters; all panel errors are clustered by quarter.",
        "",
        "## Tradable composite backtests (shared multifactor engine)",
        "",
    ]
    cols = [
        "strategy", "fee_bps", "ann_return", "ann_vol", "sharpe",
        "max_drawdown", "ann_turnover",
    ]
    lines.append(backtests[cols].round(4).to_markdown(index=False))
    lines += [
        "",
        "`flow_continuation` maps active rotation pressure back to stocks through "
        "current factor scores. `funding_x_crowding` trades only adverse funding "
        "shocks against the direction of crowded positioning. "
        "`static_crowding_placebo` tests the tempting but unsupported "
        "crowded-means-short shortcut; it is never promoted based on its realized return.",
        "",
        "## Latest positioning dashboard (sqrt-AUM manager weights)",
        "",
    ]
    latest = dashboard.loc[
        (dashboard["period_end"] == dashboard["period_end"].max())
        & (dashboard["weighting"] == "sqrt_aum")
    ]
    lines.append(
        latest[
            ["factor", "position", "dispersion", "breadth_pos", "breadth_neg", "hhi_pos", "hhi_neg"]
        ].round(4).to_markdown(index=False)
    )
    lines += [
        "",
        "## Limitations",
        "",
        "- The label is **13F long-equity exposure**, not the manager's total fund exposure; shorts, swaps and cash are absent.",
        "- The ticker/price universe is survivor-biased. Results are research diagnostics, not production evidence.",
        "- Sector-neutral exposures are not fabricated from today's sector map. Add them only with a PIT SIC/GICS history.",
        f"- The factor-flow tests have K=5 and only {n_panel_quarters} usable forward-return quarters; no multiple-testing search was performed.",
        "",
    ]
    (RESULTS / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def main(smoke: bool = False) -> None:
    config = ResearchConfig()
    DATA.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    config.write(RESULTS / "run_config.json")
    ticker_map, market, market_cap = load_inputs(config)
    store = PITQuarterStore(QUARTERS)
    dates = market.prices.index
    adv_panel = market.dollar_volume.rolling(63, min_periods=20).median()

    quarters = [
        q for q in store.quarters()
        if q >= pd.Timestamp(config.start_quarter)
        and q + pd.Timedelta(days=config.decision_lag_days) < dates[-1]
    ]
    if smoke:
        quarters = quarters[-14:]
    if len(quarters) < 3:
        raise RuntimeError("Too few quarters for exposure-flow research")
    log(f"{len(quarters)} quarters; factors={config.factor_names}; run={config.fingerprint()}")

    characteristic_cache = {}
    exposure_rows, dashboard_rows, rotation_rows, factor_rows = [], [], [], []
    validations, quality_rows, coverage_rows, skipped_quarters = [], [], [], []
    signal_events: dict[str, dict[pd.Timestamp, pd.Series]] = {
        "flow_continuation": {},
        "funding_x_crowding": {},
        "static_crowding_placebo": {},
    }

    for qi in range(1, len(quarters)):
        previous_period, period = quarters[qi - 1], quarters[qi]
        decision = period + pd.Timedelta(days=config.decision_lag_days)
        current = store.snapshot(period, decision)
        previous = store.snapshot(previous_period, decision)
        if min(len(current), len(previous)) < 1_000:
            log(f"LOUD SKIP {period.date()}: thin snapshots {len(current)}/{len(previous)}")
            skipped_quarters.append(
                {"period_end": str(period.date()), "reason": "thin_snapshot",
                 "current_rows": len(current), "previous_rows": len(previous)}
            )
            continue

        for p in (previous_period, period):
            if p not in characteristic_cache:
                characteristic_cache[p] = build_characteristics(p, market, market_cap, config)
        x_prev, x_cur = characteristic_cache[previous_period], characteristic_cache[period]
        quality_rows.append({"period_end": period, **x_cur.quality})
        if qi in {1, len(quarters) // 2, len(quarters) - 1}:
            validations.extend(_manager_synthetic_check(x_cur, config, period))

        cur_pairs, cur_totals = holdings_to_pairs(current, ticker_map)
        prev_pairs, prev_totals = holdings_to_pairs(previous, ticker_map)
        mapped = (
            cur_pairs[cur_pairs["ticker"].isin(x_cur.scores.index)]
            .groupby("filer_id")["value"].sum()
        )
        audit = cur_totals.join(mapped.rename("mapped"), how="left").fillna({"mapped": 0.0})
        audit["coverage"] = audit["mapped"] / audit["book_value"].replace(0, np.nan)
        audit = audit[
            audit["book_value"].ge(config.min_manager_aum)
            & audit["n_positions"].ge(config.min_manager_positions)
        ]
        for threshold in (0.50, 0.70, 0.80, 0.90):
            coverage_rows.append(
                {
                    "period_end": period,
                    "threshold": threshold,
                    "n_managers": int(audit["coverage"].ge(threshold).sum()),
                    "median_coverage": float(audit["coverage"].median()),
                }
            )
        cur_exp = manager_exposures(cur_pairs, cur_totals, x_cur, config)
        prev_exp = manager_exposures(prev_pairs, prev_totals, x_prev, config)

        # E_t is infrastructure and remains useful even while the early
        # manager cross-section is too thin for directional inference.  Store
        # it before applying the >=50 managers requirement used by H2-H5.
        x_dec = build_characteristics(decision, market, market_cap, config)
        di = dates.searchsorted(decision, side="right") - 1
        pit_values = drift_snapshot_values(current, ticker_map, market.prices_raw.iloc[di])
        pit_pairs, pit_totals = holdings_to_pairs(current, ticker_map, pit_values)
        pit_exp = manager_exposures(pit_pairs, pit_totals, x_dec, config)
        exposure_rows.append(exposure_long_table(period, decision, cur_exp, pit_exp))
        dash = positioning_dashboard(period, cur_exp)
        dashboard_rows.append(dash)

        if min(len(cur_exp.active), len(prev_exp.active)) < 50:
            log(
                f"LOUD SKIP {period.date()}: eligible managers "
                f"{len(cur_exp.active)}/{len(prev_exp.active)} < 50"
            )
            skipped_quarters.append(
                {"period_end": str(period.date()), "reason": "manager_ramp",
                 "current_managers": len(cur_exp.active),
                 "previous_managers": len(prev_exp.active)}
            )
            continue

        headline = dash[dash["weighting"] == "sqrt_aum"].set_index("factor")

        growth = price_growth_between(market.prices_raw, previous_period, period)
        rotation = rotation_decomposition(
            prev_pairs, cur_pairs, prev_exp, cur_exp, x_prev, x_cur, growth
        )
        rotation["period_end"] = period
        rotation_rows.append(rotation)
        agg = aggregate_rotation(rotation, x_cur, adv_panel.iloc[dates.searchsorted(period, side="right") - 1])
        active = agg[agg["component"] == "active_rotation"].set_index("factor")

        stock_ret_q = price_growth_between(market.prices, previous_period, period) - 1.0
        flows = implied_manager_funding_flow(current, previous, ticker_map, stock_ret_q)
        funding = funding_factor_pressure(
            flows,
            prev_exp,
            x_cur,
            adv_panel.iloc[dates.searchsorted(period, side="right") - 1],
        )

        position = headline["position"].reindex(config.factor_names)
        dispersion = headline["dispersion"].reindex(config.factor_names).clip(lower=0.05)
        direction = np.sign(position).replace(0, 1.0)
        aligned_breadth = pd.Series(
            np.where(
                direction >= 0,
                headline["breadth_pos"].reindex(config.factor_names),
                headline["breadth_neg"].reindex(config.factor_names),
            ),
            index=config.factor_names,
        )
        vulnerability = (position.abs() / dispersion) * aligned_breadth
        vulnerability_rank = vulnerability.rank(pct=True)
        pressure = active["pressure"].reindex(config.factor_names)
        aggregate_rotation_sqrt = active["aggregate_sqrt"].reindex(config.factor_names)
        pressure_z = cross_sectional_z(pressure)
        funding_z = cross_sectional_z(funding.reindex(config.factor_names))
        position_z = cross_sectional_z(position)
        adverse = (-direction * funding_z).clip(lower=0)
        adverse_mask = adverse.gt(0).astype(float)
        h5_factor_coefficient = funding_z * vulnerability_rank * adverse_mask

        flow_score = x_cur.scores.mul(pressure_z, axis=1).sum(axis=1)
        h5_score = x_cur.scores.mul(h5_factor_coefficient, axis=1).sum(axis=1)
        static_score = x_cur.scores.mul(position_z, axis=1).sum(axis=1)
        signal_events["flow_continuation"][decision] = flow_score
        signal_events["funding_x_crowding"][decision] = h5_score
        signal_events["static_crowding_placebo"][decision] = static_score

        next_decision = (
            quarters[qi + 1] + pd.Timedelta(days=config.decision_lag_days)
            if qi + 1 < len(quarters)
            else None
        )
        fwd_factor = pd.Series(np.nan, index=config.factor_names)
        if next_decision is not None and next_decision < dates[-1]:
            forward_stock = total_returns_between(market.prices, decision, next_decision)
            fwd_factor = factor_mimicking_return(x_cur.scores, forward_stock)

        for factor in config.factor_names:
            factor_rows.append(
                {
                    "period_end": period,
                    "decision_date": decision,
                    "factor": factor,
                    "position": position[factor],
                    "position_cs_z": position_z[factor],
                    "dispersion": dispersion[factor],
                    "vulnerability": vulnerability[factor],
                    "vulnerability_rank": vulnerability_rank[factor],
                    "rotation": aggregate_rotation_sqrt[factor],
                    "pressure": pressure[factor],
                    "pressure_cs_z": pressure_z[factor],
                    "funding": funding.get(factor, np.nan),
                    "funding_cs_z": funding_z.get(factor, np.nan),
                    "direction": direction[factor],
                    "adverse_shock": adverse[factor],
                    "adverse_x_vulnerability": adverse[factor] * vulnerability_rank[factor],
                    "fwd_factor_return": fwd_factor.get(factor, np.nan),
                    "aligned_fwd_return": direction[factor] * fwd_factor.get(factor, np.nan),
                    "n_managers": int(active.loc[factor, "n_managers"]),
                }
            )

        log(
            f"{period.date()}: {len(cur_exp.active)} managers, {len(x_cur.scores)} stocks, "
            f"rotation identity={rotation['max_identity_error'].max():.2e}"
        )

    exposures = pd.concat(exposure_rows, ignore_index=True)
    dashboard = pd.concat(dashboard_rows, ignore_index=True)
    rotations = pd.concat(rotation_rows, ignore_index=True)
    panel = pd.DataFrame(factor_rows).sort_values(["factor", "period_end"])
    validation = pd.DataFrame(validations)
    coverage_audit = pd.DataFrame(coverage_rows)
    if exposures.empty or panel.empty:
        raise RuntimeError("Pipeline produced no exposure/flow observations")

    panel["position_next"] = panel.groupby("factor")["position"].shift(-1)
    panel["rotation_next"] = panel.groupby("factor")["rotation"].shift(-1)
    test_specs = [
        ("H1_position_persistence", "position_next", ["position"], False),
        ("H2_rotation_persistence", "rotation_next", ["rotation"], False),
        ("H3_flow_continuation", "fwd_factor_return", ["pressure_cs_z"], True),
        ("H4_static_crowding_placebo", "fwd_factor_return", ["position_cs_z"], True),
        (
            "H5_adverse_flow_x_crowding",
            "aligned_fwd_return",
            ["adverse_shock", "vulnerability_rank", "adverse_x_vulnerability"],
            True,
        ),
    ]
    test_rows = []
    for hypothesis, y, xs, time_fe in test_specs:
        result = clustered_panel_ols(panel, y, xs, factor_fe=True, time_fe=time_fe)
        result["hypothesis"] = hypothesis
        test_rows.append(result)
    tests = pd.concat(test_rows, ignore_index=True)[
        ["hypothesis", "term", "coef", "se", "t", "n", "clusters"]
    ]

    filters = Filters(
        market,
        min_price=config.min_price,
        min_dollar_volume=config.min_adv,
        min_history_days=config.min_history_days,
        min_stocks=config.portfolio_min_stocks,
    )
    portfolios = [
        event_scores_to_portfolio(
            name,
            events,
            market,
            filters.universe,
            Portfolio,
            Indicator,
            pct=config.portfolio_quantile,
            min_stocks=config.portfolio_min_stocks,
        )
        for name, events in signal_events.items()
    ]
    first_signal = min(min(events) for events in signal_events.values())
    backtests, backtest_returns = run_cost_ladder(
        portfolios, market, Backtest, config.fee_bps, start=first_signal
    )
    bootstrap = {}
    for strategy, g in backtest_returns[backtest_returns["fee_bps"] == 10].groupby("strategy"):
        bootstrap[strategy] = circular_block_bootstrap_mean(g.set_index("date")["return"])

    exposures.to_parquet(DATA / "manager_factor_exposure.parquet", index=False)
    dashboard.to_csv(DATA / "factor_positioning_dashboard.csv", index=False)
    rotations.to_parquet(DATA / "manager_factor_rotation.parquet", index=False)
    panel.to_csv(DATA / "factor_flow_panel.csv", index=False)
    tests.to_csv(RESULTS / "hypothesis_tests.csv", index=False)
    backtests.to_csv(RESULTS / "backtest_summary.csv", index=False)
    backtest_returns.to_csv(RESULTS / "backtest_returns.csv", index=False)
    validation.to_csv(RESULTS / "measurement_validation.csv", index=False)
    coverage_audit.to_csv(DATA / "coverage_sensitivity.csv", index=False)
    diagnostics = {
        "run_fingerprint": config.fingerprint(),
        "max_rotation_identity_error": float(rotations["max_identity_error"].max()),
        "mean_cap_rejected": float(pd.DataFrame(quality_rows)["n_cap_rejected"].mean()),
        "bootstrap_10bps_daily_mean": bootstrap,
        "skipped_quarters": skipped_quarters,
        "deferred": ["PIT accounting factors", "PIT sectors", "factor stress matrix", "H6 mismatch"],
    }
    (RESULTS / "diagnostics.json").write_text(
        json.dumps(diagnostics, indent=2), encoding="utf-8"
    )
    _write_report(
        config, exposures, dashboard, panel, tests, backtests, validation,
        coverage_audit, diagnostics
    )
    log(f"done -> {RESULTS}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    main(**vars(parser.parse_args()))
