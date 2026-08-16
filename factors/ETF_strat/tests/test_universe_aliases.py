"""CUSIP and FIGI aliases must not duplicate the ETF product cross-section."""

from __future__ import annotations

import pandas as pd

from etf_strategies.signals import score_event_state


def test_score_event_state_collapses_master_aliases(master):
    alias = master.iloc[[0]].copy()
    alias["instrument_id"] = "BBG001S72SM3"
    aliased = pd.concat([master, alias], ignore_index=True)
    state = pd.DataFrame({
        "state_value": [1.0, 1.0], "fragility_owner_value": [1.0, 1.0],
        "n_holders": [1.0, 1.0], "churn_value": [0.1, 0.2],
        "ccp_state": [0.0, 0.0], "consensus_state": [0.0, 0.0],
    }, index=["AAA", "BBB"])
    flow = pd.DataFrame(index=state.index)
    for column in [
        "sticky_raw", "sticky_quality", "sticky_specificity", "double_down_all",
        "double_down_specific", "new_holder_breadth",
    ]:
        flow[column] = 0.0
    public = pd.DataFrame(index=state.index)
    for column in [
        "momentum_63d", "volatility_63d", "beta_126d", "log_adv_63d",
        "log_price", "log_age",
    ]:
        public[column] = 0.0
    out = score_event_state(
        state, flow, public, pd.Series(0.0, index=state.index), False,
        pd.Series(float("nan"), index=state.index), aliased,
    )
    assert out.index.is_unique
    assert list(out.index) == ["AAA", "BBB"]
