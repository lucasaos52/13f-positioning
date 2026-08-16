from __future__ import annotations

import numpy as np
import pandas as pd

from etf_strategies.signals import abnormal_breadth, score_event_state


def test_abnormal_breadth_is_orthogonal_to_design():
    n = 30
    tickers = [f"E{i:02d}" for i in range(n)]
    state = pd.DataFrame(
        {"n_holders": np.arange(1, n + 1), "state_value": np.exp(np.linspace(10, 15, n))},
        index=tickers,
    )
    features = pd.DataFrame(
        {
            "momentum_63d": np.linspace(-0.2, 0.3, n),
            "volatility_63d": np.linspace(0.1, 0.5, n),
            "beta_126d": np.linspace(0.5, 1.5, n),
            "log_adv_63d": np.linspace(12, 18, n),
            "log_price": np.linspace(2, 5, n),
            "log_age": np.linspace(4, 8, n),
        },
        index=tickers,
    )
    master = pd.DataFrame({"ticker": tickers, "etf_style": ["broad"] * n})
    residual = abnormal_breadth(state, features, master).dropna()
    assert abs(residual.mean()) < 1e-10
    assert abs(np.dot(residual, np.ones(len(residual)))) < 1e-9


def test_fragility_is_conditional_and_specific_mask(master):
    idx = pd.Index(master["ticker"])
    state = pd.DataFrame(
        {"state_value": [100.0, 100.0], "n_holders": [10, 10], "churn_value": [10, 80],
         "ccp_state": [1, 2], "consensus_state": [1, 1]}, index=idx
    )
    flow = pd.DataFrame(
        {"sticky_raw": [1, 1], "sticky_quality": [1, 1], "sticky_specificity": [1, 1],
         "double_down_all": [2, 2], "double_down_specific": [2, 2],
         "new_holder_breadth": [0, 1]}, index=idx
    )
    features = pd.DataFrame(index=idx)
    for c in ["momentum_63d", "volatility_63d", "beta_126d", "log_adv_63d", "log_price", "log_age"]:
        features[c] = [0.0, 1.0]
    scored = score_event_state(
        state, flow, features, pd.Series([-1.0, -2.0], index=idx), False,
        pd.Series(np.nan, index=idx), master,
    )
    assert scored["fragility_stress"].isna().all()
    assert pd.isna(scored.loc["AAA", "double_down_specific"])
    assert scored.loc["BBB", "double_down_specific"] == 2

