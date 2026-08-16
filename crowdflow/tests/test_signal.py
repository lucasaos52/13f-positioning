"""Tests for the signal layer, including the invariants that guard lookahead."""

from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd
import pytest

from crowdflow.config import FactorCfg, UniverseCfg
from crowdflow.evaluate.calendar import assign_signal_periods, build_activation_schedule
from crowdflow.evaluate.metrics import deflated_sharpe, newey_west_tstat
from crowdflow.signal.factors import build_quarter_factors
from crowdflow.signal.footprint import compute_footprint
from crowdflow.signal.selection import score_managers, select_universe


# --------------------------------------------------------------------------- #
def _reference(ids, adv=1e8, vol=0.3, price=100.0, cap=1e10, split=1.0):
    return pd.DataFrame(
        {
            "instrument_id": ids,
            "period_end": pd.Timestamp("2020-03-31"),
            "price": price,
            "adv_usd": adv,
            "vol_ann": vol,
            "amihud": 1e-12,
            "mktcap": cap,
            "cum_split_factor": split,
        }
    )


def _holdings(rows, period="2020-03-31"):
    df = pd.DataFrame(rows, columns=["filer_id", "instrument_id", "shares", "value_usd"])
    df["period_end"] = pd.Timestamp(period)
    df["accession"] = df["filer_id"] + "-" + period
    df["put_call"] = pd.NA
    return df


# --------------------------------------------------------------------------- #
# Footprint
# --------------------------------------------------------------------------- #
def test_illiquid_book_scores_higher_impact_than_liquid_book_of_equal_size():
    """The central claim of the universe design: two $1bn books are not the
    same object if one of them is in names that take weeks to exit."""
    ref = pd.concat(
        [
            _reference(["LIQ"], adv=1e9),
            _reference(["ILL"], adv=1e7),
        ],
        ignore_index=True,
    )
    h = _holdings(
        [("BIG_LIQUID", "LIQ", 1e7, 1e9), ("BIG_ILLIQUID", "ILL", 1e7, 1e9)]
    )
    fp = compute_footprint(h, ref, None, UniverseCfg())
    fp = fp.set_index("filer_id")
    assert fp.loc["BIG_ILLIQUID", "impact_cost_usd"] > fp.loc["BIG_LIQUID", "impact_cost_usd"]
    assert np.isclose(fp.loc["BIG_LIQUID", "book_usd"], fp.loc["BIG_ILLIQUID", "book_usd"])


def test_centrality_rewards_shared_illiquid_positions():
    ref = _reference(["A", "B", "C"], adv=1e7)
    crowded = _holdings(
        [
            ("M1", "A", 1e6, 1e8),
            ("M2", "A", 1e6, 1e8),
            ("M3", "A", 1e6, 1e8),
            ("LONER", "C", 1e6, 1e8),
        ]
    )
    fp = compute_footprint(crowded, ref, None, dataclasses.replace(UniverseCfg(), centrality_log1p=False))
    fp = fp.set_index("filer_id")
    assert fp.loc["M1", "centrality"] > fp.loc["LONER", "centrality"]
    assert np.isclose(fp.loc["LONER", "centrality"], 0.0)


def test_centrality_identity_matches_the_naive_double_loop():
    """The O(M*N) shortcut must equal the O(M^2*N) definition exactly."""
    rng = np.random.default_rng(0)
    ids = [f"S{i}" for i in range(12)]
    ref = _reference(ids, adv=1e7)
    rows = []
    for m in range(6):
        for i, sid in enumerate(ids):
            v = float(rng.random() * 1e8)
            rows.append((f"M{m}", sid, v / 100, v))
    fp = compute_footprint(
        _holdings(rows), ref, None, dataclasses.replace(UniverseCfg(), centrality_log1p=False)
    ).set_index("filer_id")

    X = pd.DataFrame(rows, columns=["m", "i", "sh", "v"]).pivot_table(
        index="m", columns="i", values="v", aggfunc="sum", fill_value=0.0
    ) / 1e7
    naive = {}
    for m in X.index:
        naive[m] = sum((X.loc[m] * X.loc[n]).sum() for n in X.index if n != m)
    for m, expected in naive.items():
        assert np.isclose(fp.loc[m, "centrality"], expected, rtol=1e-9)


def test_turnover_is_immune_to_stock_splits():
    """A 4-for-1 split with no trading must produce zero turnover.

    Each leg is adjusted by its own quarter's cumulative factor. Using no
    adjustment reads this as a 300% purchase; using the current quarter's
    factor on both legs reads it as a 75% sale. Both errors are large and both
    land on widely held megacaps."""
    prev = _holdings([("M1", "A", 1_000_000.0, 1e8)], period="2019-12-31")
    cur = _holdings([("M1", "A", 4_000_000.0, 1e8)])
    ref = _reference(["A"], price=25.0, split=4.0)
    prev_ref = _reference(["A"], price=100.0, split=1.0)
    fp = compute_footprint(cur, ref, prev, UniverseCfg(), prev_reference=prev_ref).set_index("filer_id")
    assert abs(fp.loc["M1", "turnover"]) < 1e-9


def test_turnover_without_prev_reference_is_wrong_in_a_known_direction():
    """Documents the failure mode the previous test guards against, so that a
    future refactor dropping ``prev_reference`` fails loudly rather than
    quietly.

    Applying the post-split factor to both legs makes an untouched position
    read as a 75% sale, which lands as 9.4pp of phantom turnover on a single
    name - against a typical quarterly book turnover of roughly 20%, that is a
    large distortion from one corporate action."""
    prev = _holdings([("M1", "A", 1_000_000.0, 1e8)], period="2019-12-31")
    cur = _holdings([("M1", "A", 4_000_000.0, 1e8)])
    ref = _reference(["A"], price=25.0, split=4.0)
    fp = compute_footprint(cur, ref, prev, UniverseCfg()).set_index("filer_id")
    assert fp.loc["M1", "turnover"] == pytest.approx(0.09375, rel=1e-6)


def test_turnover_detects_a_real_trade():
    prev = _holdings([("M1", "A", 1_000_000.0, 1e8)], period="2019-12-31")
    cur = _holdings([("M1", "A", 1_500_000.0, 1.5e8)])
    ref = _reference(["A"], price=100.0)
    fp = compute_footprint(cur, ref, prev, UniverseCfg(), prev_reference=ref).set_index("filer_id")
    assert fp.loc["M1", "turnover"] == pytest.approx(0.25, rel=1e-6)


# --------------------------------------------------------------------------- #
# Selection
# --------------------------------------------------------------------------- #
def _footprint_panel(n_mgr=40, n_q=8, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    quality = rng.random(n_mgr)
    for q in range(n_q):
        for m in range(n_mgr):
            rows.append(
                {
                    "filer_id": f"M{m:02d}",
                    "period_end": pd.Timestamp("2019-03-31") + pd.DateOffset(months=3 * q),
                    "book_usd": 1e9 * (1 + quality[m] * 10),
                    "n_positions": 50,
                    "top1_weight": 0.1,
                    "hhi": 0.02,
                    "impact_cost_usd": 1e6 * (1 + quality[m] * 10) * np.exp(rng.normal(0, 0.3)),
                    "impact_bps": 10.0,
                    "centrality": quality[m] * 10 + rng.normal(0, 0.3),
                    "own_overlap": 1.0,
                    "turnover": 0.2,
                    "turnover_ewma": 0.2 + rng.normal(0, 0.02),
                    "synchrony": 0.5,
                    "n_quarters_history": q + 1,
                }
            )
    return pd.DataFrame(rows)


def test_universe_uses_lagged_scores_only():
    """Membership in quarter t must be justified by a strictly earlier quarter.
    This is the property that makes 'we did not select on the signal we then
    traded' a checkable claim rather than an assertion."""
    cfg = dataclasses.replace(UniverseCfg(), min_equity_book_usd=0.0, min_history_quarters=1)
    uni = select_universe(score_managers(_footprint_panel(), cfg), cfg)
    assert (uni["source_period_end"] < uni["period_end"]).all()


def test_hysteresis_reduces_churn():
    cfg_hard = dataclasses.replace(
        UniverseCfg(), min_equity_book_usd=0.0, min_history_quarters=1, target_size=15, buffer_size=15
    )
    cfg_buffered = dataclasses.replace(cfg_hard, buffer_size=25)
    fp = _footprint_panel(n_mgr=60, n_q=12, seed=7)

    def churn(cfg):
        uni = select_universe(score_managers(fp, cfg), cfg)
        return (uni["status"] == "new").sum()

    assert churn(cfg_buffered) < churn(cfg_hard)


def test_single_name_shell_is_excluded():
    """A filer whose entire disclosed book is one line - one ETF, one SPAC,
    one legacy position - is a wrapper, not a diversified equity manager.
    Under any within-book weighting it looks maximally concentrated and
    maximally high-conviction, so left in it dominates the ranking for
    reasons that have nothing to do with price pressure."""
    cfg = dataclasses.replace(UniverseCfg(), min_equity_book_usd=0.0, min_history_quarters=1)
    fp = _footprint_panel(n_mgr=10, n_q=6)
    fp.loc[fp["filer_id"] == "M00", "top1_weight"] = 1.0
    scored = score_managers(fp, cfg)
    assert not scored.loc[scored["filer_id"] == "M00", "eligible"].any()


# --------------------------------------------------------------------------- #
# Calendar
# --------------------------------------------------------------------------- #
def test_activation_waits_for_coverage_not_for_the_deadline():
    """Half the universe files on day 40 and half on day 120. An 80% coverage
    rule must wait for the stragglers rather than trading on day 45."""
    period = pd.Timestamp("2020-03-31")
    prompt = [f"P{i}" for i in range(5)]
    late = [f"L{i}" for i in range(5)]
    revisions = pd.DataFrame(
        {
            "filer_id": prompt + late,
            "period_end": [period] * 10,
            "accession": [f"a{i}" for i in range(10)],
            "form": ["13F-HR"] * 10,
            "knowledge_ts": [period + pd.Timedelta(days=40)] * 5
            + [period + pd.Timedelta(days=120)] * 5,
        }
    )
    universe = pd.DataFrame({"period_end": [period] * 10, "filer_id": prompt + late})
    dates = pd.bdate_range("2020-04-01", "2020-12-31", freq="BME")
    sched = build_activation_schedule(revisions, universe, dates, coverage_threshold=0.8)
    assert sched["lag_days"].iloc[0] > 110


def test_activation_is_monotone_in_period():
    period_a, period_b = pd.Timestamp("2020-03-31"), pd.Timestamp("2020-06-30")
    revisions = pd.DataFrame(
        {
            "filer_id": ["A", "A"],
            "period_end": [period_a, period_b],
            "accession": ["x", "y"],
            "form": ["13F-HR", "13F-HR"],
            # Q1 filed very late, after Q2 was filed on time.
            "knowledge_ts": [period_a + pd.Timedelta(days=140), period_b + pd.Timedelta(days=40)],
        }
    )
    universe = pd.DataFrame(
        {"period_end": [period_a, period_b], "filer_id": ["A", "A"]}
    )
    dates = pd.bdate_range("2020-04-01", "2021-06-30", freq="BME")
    sched = build_activation_schedule(revisions, universe, dates, coverage_threshold=0.8)
    assert sched["trade_date"].is_monotonic_increasing


def test_stale_signals_are_flagged_not_carried_forever():
    sched = pd.DataFrame(
        {
            "period_end": [pd.Timestamp("2020-03-31")],
            "trade_date": [pd.Timestamp("2020-06-01")],
        }
    )
    months = pd.bdate_range("2020-06-30", "2021-12-31", freq="BME")
    mapped = assign_signal_periods(months, sched, staleness_cap_days=200)
    assert mapped["stale"].any() and not mapped["stale"].all()


# --------------------------------------------------------------------------- #
# Factors and statistics
# --------------------------------------------------------------------------- #
def test_caf_sign_follows_net_buying():
    ref = _reference(["A", "B"], adv=1e7)
    prev = _holdings([("M1", "A", 1000.0, 1e5), ("M1", "B", 1000.0, 1e5)], period="2019-12-31")
    cur = _holdings([("M1", "A", 5000.0, 5e5), ("M1", "B", 100.0, 1e4)])
    flow = pd.DataFrame(columns=["filer_id", "period_end", "flow_rate"])
    f = build_quarter_factors(cur, prev, ["M1"], ref, flow, FactorCfg()).set_index("instrument_id")
    assert f.loc["A", "caf"] > 0 > f.loc["B", "caf"]


def test_managers_outside_the_universe_are_ignored():
    ref = _reference(["A"], adv=1e7)
    prev = _holdings([("IN", "A", 1000.0, 1e5), ("OUT", "A", 1000.0, 1e5)], period="2019-12-31")
    cur = _holdings([("IN", "A", 1000.0, 1e5), ("OUT", "A", 9e6, 9e8)])
    flow = pd.DataFrame(columns=["filer_id", "period_end", "flow_rate"])
    f = build_quarter_factors(cur, prev, ["IN"], ref, flow, FactorCfg()).set_index("instrument_id")
    assert abs(f.loc["A", "caf"]) < 1e-12


def test_newey_west_widens_errors_under_autocorrelation():
    rng = np.random.default_rng(3)
    e = rng.normal(0, 1, 400)
    ar = np.zeros(400)
    for t in range(1, 400):
        ar[t] = 0.7 * ar[t - 1] + e[t]
    t_nw, se_nw = newey_west_tstat(pd.Series(ar + 0.25), lags=12)
    se_ols = pd.Series(ar + 0.25).std(ddof=1) / np.sqrt(400)
    assert se_nw > se_ols


def test_deflated_sharpe_penalises_more_trials():
    assert deflated_sharpe(0.25, 120, 1) > deflated_sharpe(0.25, 120, 50)


# --------------------------------------------------------------------------- #
# Benchmark attribution
# --------------------------------------------------------------------------- #
def _bench(n=120, seed=7):
    rng = np.random.default_rng(seed)
    months = pd.period_range("2015-01", periods=n, freq="M")
    return pd.DataFrame(
        {
            "month": months,
            "mkt": rng.normal(0.006, 0.04, n),
            "smb": rng.normal(0.001, 0.02, n),
            "mom": rng.normal(0.002, 0.03, n),
            "strev": rng.normal(0.000, 0.02, n),
            "illiq": rng.normal(0.001, 0.02, n),
        }
    )


def test_attribution_strips_a_pure_momentum_clone():
    """A 'factor' that is 1.2x momentum plus noise must show a large momentum
    beta and an alpha indistinguishable from zero. This is the control that
    stops a repackaged known premium from being presented as a new one."""
    from crowdflow.evaluate.attribution import attribute

    b = _bench()
    rng = np.random.default_rng(11)
    y = pd.Series(
        1.2 * b["mom"].to_numpy() + rng.normal(0, 0.004, len(b)), index=b["month"]
    )
    out = attribute(y, b)
    assert out["beta_mom"] == pytest.approx(1.2, abs=0.1)
    assert abs(out["alpha_t_nw"]) < 2.0
    assert out["r2"] > 0.9


def test_attribution_keeps_alpha_that_is_genuinely_orthogonal():
    """A constant drift uncorrelated with every benchmark must survive."""
    from crowdflow.evaluate.attribution import attribute

    b = _bench()
    rng = np.random.default_rng(12)
    y = pd.Series(0.006 + rng.normal(0, 0.004, len(b)), index=b["month"])
    out = attribute(y, b)
    assert out["alpha_ann"] == pytest.approx(0.072, abs=0.02)
    assert out["alpha_t_nw"] > 3.0
    assert out["r2"] < 0.3


def test_newey_west_regression_se_exceeds_ols_under_autocorrelation():
    """The whole reason for HAC here: a quarterly signal held for three months
    makes consecutive monthly returns dependent, and an OLS standard error
    would overstate significance."""
    from crowdflow.evaluate.attribution import _ols_nw

    rng = np.random.default_rng(3)
    n = 240
    e = np.zeros(n)
    for t in range(1, n):
        e[t] = 0.75 * e[t - 1] + rng.normal(0, 0.01)
    X = np.column_stack([np.ones(n), rng.normal(0, 0.04, n)])
    y = 0.002 + 0.5 * X[:, 1] + e

    _, se_nw = _ols_nw(y, X, lags=6)
    _, se_ols = _ols_nw(y, X, lags=0)
    assert se_nw[0] > se_ols[0]
