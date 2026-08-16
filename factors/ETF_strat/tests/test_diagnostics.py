import pandas as pd

from etf_strategies.diagnostics import scoped_signal_events


def test_scoped_signal_keeps_only_allowed_products_and_event_marker():
    events = pd.DataFrame(
        {
            "signal_name": ["ccp", "ccp", "ccp", "consensus"],
            "ticker": ["AAA", "BBB", "__EVENT__", "AAA"],
            "available_date": pd.to_datetime(["2024-01-01"] * 4),
            "signal": [1.0, 2.0, 0.0, 3.0],
        }
    )
    master = pd.DataFrame(
        {"ticker": ["AAA", "BBB"], "etf_style": ["sector", "broad_market"]}
    )
    out = scoped_signal_events(events, master, "ccp", "ccp_specific", ("sector",))
    assert out["signal_name"].eq("ccp_specific").all()
    assert set(out["ticker"]) == {"AAA", "__EVENT__"}


def test_scoped_signal_can_filter_passive_flag():
    events = pd.DataFrame(
        {
            "signal_name": ["ccp", "ccp", "ccp"],
            "ticker": ["AAA", "BBB", "__EVENT__"],
            "available_date": pd.to_datetime(["2024-01-01"] * 3),
            "signal": [1.0, 2.0, 0.0],
        }
    )
    master = pd.DataFrame(
        {
            "ticker": ["AAA", "BBB"],
            "etf_style": ["sector", "sector"],
            "is_passive_equity_etf": [True, False],
        }
    )
    out = scoped_signal_events(
        events, master, "ccp", "ccp_passive", require_column="is_passive_equity_etf"
    )
    assert set(out["ticker"]) == {"AAA", "__EVENT__"}
