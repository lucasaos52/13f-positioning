import numpy as np
import pandas as pd
import pytest

from etf_positioning.signals import (
    direct_vs_etf_conviction,
    etf_fragility,
    lookthrough_pressure,
    overlap_network_shock,
    pressure_scaled_by_fragility,
    raw_etf_ownership_change,
    filing_time_demand_nowcast,
)


def test_filing_nowcast_releases_only_at_each_event():
    p = pd.Timestamp("2023-03-31")
    x = pd.DataFrame({
        "filer_id": ["a", "b"], "period_end": p, "etf_id": "SPY",
        "available_ts": ["2023-05-01 12:00", "2023-05-02 12:00"],
        "delta_shares": [10.0, -3.0],
    })
    out = filing_time_demand_nowcast(x)
    assert out["demand_nowcast_shares"].tolist() == [10.0, 7.0]


def test_raw_ownership_is_share_based_not_value_based():
    q1, q2 = pd.Timestamp("2023-03-31"), pd.Timestamp("2023-06-30")
    h = pd.DataFrame({
        "filer_id": ["a", "b", "a", "b"],
        "period_end": [q1, q1, q2, q2],
        "etf_id": "SPY",
        "shares": [10.0, 20.0, 20.0, 30.0],
    })
    ref = pd.DataFrame({
        "period_end": [q1, q2], "etf_id": "SPY", "shares_outstanding": [100.0, 100.0]
    })
    out = raw_etf_ownership_change(h, ref).set_index("period_end")
    assert out.loc[q1, "own_13f"] == pytest.approx(0.30)
    assert out.loc[q2, "d_own_13f"] == pytest.approx(0.20)


def test_lookthrough_pressure_matches_blueprint_formula():
    p = pd.Timestamp("2023-06-30")
    d = pd.DataFrame({"period_end": [p], "etf_id": ["E"], "d_own_13f": [0.10], "aum": [1000.0]})
    b = pd.DataFrame({
        "period_end": [p, p], "effective_date": [p, p], "etf_id": ["E", "E"],
        "instrument_id": ["A", "B"], "basket_weight": [0.6, 0.4],
    })
    r = pd.DataFrame({"period_end": [p, p], "instrument_id": ["A", "B"], "market_cap": [1200.0, 400.0]})
    _, c = lookthrough_pressure(d, b, r)
    vals = c.set_index("instrument_id")["pressure_contribution"]
    assert vals["A"] == pytest.approx(0.05)
    assert vals["B"] == pytest.approx(0.10)


def test_future_effective_basket_is_rejected():
    p = pd.Timestamp("2023-06-30")
    d = pd.DataFrame({"period_end": [p], "etf_id": ["E"], "d_own_13f": [0.1], "aum": [1.0]})
    b = pd.DataFrame({
        "period_end": [p], "effective_date": [p + pd.Timedelta(days=1)], "etf_id": ["E"],
        "instrument_id": ["A"], "basket_weight": [1.0],
    })
    r = pd.DataFrame({"period_end": [p], "instrument_id": ["A"], "market_cap": [1.0]})
    with pytest.raises(ValueError, match="lookahead"):
        lookthrough_pressure(d, b, r)


def test_fragility_uses_only_flows_available_by_period():
    p = pd.Timestamp("2023-06-30")
    dates = pd.date_range("2023-06-01", periods=8)
    b = pd.DataFrame({
        "period_end": [p, p], "etf_id": ["E1", "E2"], "instrument_id": ["A", "A"],
        "basket_weight": [0.5, 0.5],
    })
    flows = pd.DataFrame({
        "date": list(dates) * 2 + [p + pd.Timedelta(days=1)] * 2,
        "etf_id": ["E1"] * 8 + ["E2"] * 8 + ["E1", "E2"],
        "dollar_flow": list(range(8)) + list(range(8)) + [1e12, -1e12],
    })
    ref = pd.DataFrame({"period_end": [p], "instrument_id": ["A"], "market_cap": [100.0]})
    a = etf_fragility(b, flows, ref, lookback=8, min_periods=8)
    clean = flows[flows["date"] <= p]
    z = etf_fragility(b, clean, ref, lookback=8, min_periods=8)
    assert a.loc[0, "fragility"] == pytest.approx(z.loc[0, "fragility"])


def test_direct_vs_etf_residual_removes_broad_sleeve():
    p = pd.Timestamp("2023-06-30")
    direct = pd.DataFrame({
        "filer_id": ["m", "m"], "period_end": [p, p], "instrument_id": ["A", "B"],
        "value_usd": [80.0, 20.0],
    })
    etf_h = pd.DataFrame({"filer_id": ["m"], "period_end": [p], "etf_id": ["E"], "value_usd": [100.0]})
    baskets = pd.DataFrame({
        "period_end": [p, p], "etf_id": ["E", "E"], "instrument_id": ["A", "B"],
        "basket_weight": [0.8, 0.2],
    })
    out = direct_vs_etf_conviction(direct, etf_h, baskets)
    assert np.allclose(out["idio13f"], 0.0)


def test_overlap_shock_uses_minimum_weights_and_excludes_self():
    p = pd.Timestamp("2023-06-30")
    b = pd.DataFrame({
        "period_end": [p] * 4, "etf_id": ["E1", "E1", "E2", "E2"],
        "instrument_id": ["A", "B", "A", "C"], "basket_weight": [0.6, 0.4, 0.5, 0.5],
    })
    d = pd.DataFrame({"period_end": [p, p], "etf_id": ["E1", "E2"], "d_own_13f": [0.2, 0.0]})
    out = overlap_network_shock(b, d).set_index("etf_id")
    assert out.loc["E2", "network_shock"] == pytest.approx(0.5 * 0.2)
    assert out.loc["E1", "network_shock"] == 0.0


def test_fragility_scaler_preserves_reversal_direction():
    p = pd.Timestamp("2023-06-30")
    pressure = pd.DataFrame({"period_end": [p], "instrument_id": ["A"], "pressure_z": [2.0]})
    frag = pd.DataFrame({"period_end": [p], "instrument_id": ["A"], "fragility_z": [1.5]})
    out = pressure_scaled_by_fragility(pressure, frag)
    assert out.loc[0, "pressure_fragility_alpha"] == pytest.approx(-5.0)
