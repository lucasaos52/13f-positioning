from __future__ import annotations

import numpy as np
import pandas as pd

from classical_positioning.characteristics import CharacteristicSnapshot
from classical_positioning.config import ResearchConfig
from classical_positioning.exposures import (
    aggregate_rotation,
    manager_exposures,
    rotation_decomposition,
)


FACTORS = ["size", "momentum", "beta", "lowvol", "liquidity"]


def _char(scores, date):
    x = pd.DataFrame(scores, index=["A", "B", "C"], columns=FACTORS, dtype=float)
    bw = pd.Series(1 / 3, index=x.index)
    return CharacteristicSnapshot(
        pd.Timestamp(date), x, x, bw, x.mul(bw, axis=0).sum(), {"n_scores": 3}
    )


def _exp(pairs, characteristic):
    totals = pairs.groupby("filer_id").agg(
        book_value=("value", "sum"), n_positions=("ticker", "nunique")
    )
    cfg = ResearchConfig(
        min_manager_positions=1,
        min_manager_aum=0,
        min_factor_coverage=0,
    )
    return manager_exposures(pairs, totals, characteristic, cfg)


def test_manager_exposure_renormalizes_only_after_reporting_coverage():
    x = _char([[2, 0, 0, 0, 0], [-2, 0, 0, 0, 0], [0, 0, 0, 0, 0]], "2024-03-31")
    pairs = pd.DataFrame(
        {"filer_id": ["M", "M"], "ticker": ["A", "B"], "value": [75.0, 25.0], "shares": [1, 1]}
    )
    e = _exp(pairs, x)
    assert e.raw.loc["M", "size"] == 1.0
    assert e.metadata.loc["M", "coverage"] == 1.0


def test_rotation_decomposition_is_exact_under_entries_and_exits():
    prev_x = _char(
        [[2, 1, 0.5, -1, 0], [-2, -1, 1, 1, 0.5], [0, 0, -1, 0, -0.5]],
        "2024-03-31",
    )
    cur_x = _char(
        [[1, -1, 0, -0.5, 0.5], [-1, 2, 0.5, 0.5, 1], [0.5, 0, -0.5, 1, -1]],
        "2024-06-30",
    )
    prev = pd.DataFrame(
        {"filer_id": ["M", "M"], "ticker": ["A", "B"], "value": [60.0, 40.0], "shares": [6, 4]}
    )
    cur = pd.DataFrame(
        {"filer_id": ["M", "M"], "ticker": ["A", "C"], "value": [30.0, 70.0], "shares": [3, 7]}
    )
    rot = rotation_decomposition(
        prev, cur, _exp(prev, prev_x), _exp(cur, cur_x), prev_x, cur_x,
        pd.Series({"A": 1.10, "B": 0.90, "C": 1.0}),
    )
    assert rot["max_identity_error"].max() < 1e-12
    wide = rot.pivot_table(index=["filer_id", "factor"], columns="component", values="value")
    np.testing.assert_allclose(
        wide["price_drift"] + wide["characteristic_drift"] + wide["active_rotation"],
        wide["total_change"],
        atol=1e-12,
    )


def test_factor_pressure_has_correct_dollar_over_adv_units():
    x = _char([[1, 1, 1, 1, 1], [-1, -1, -1, -1, -1], [0, 0, 0, 0, 0]], "2024-06-30")
    rot = pd.DataFrame(
        {
            "component": ["active_rotation", "active_rotation"],
            "filer_id": ["M1", "M2"],
            "factor": ["size", "size"],
            "value": [0.10, -0.05],
            "aum_prev": [1000.0, 1000.0],
            "max_identity_error": [0.0, 0.0],
        }
    )
    out = aggregate_rotation(rot, x, pd.Series(100.0, index=x.scores.index)).iloc[0]
    # dollar flow = 50; capacity = |1|100 + |-1|100 = 200
    assert out["pressure"] == 0.25
