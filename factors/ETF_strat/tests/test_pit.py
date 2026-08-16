from __future__ import annotations

import pandas as pd

from etf_strategies.pit import fold_visible_filings


def test_restatement_replaces_and_later_new_holdings_adds():
    rows = [
        ("F", 1, "A", 10.0, 100.0, "2024-05-01", False, None, 0),
        ("F", 1, "B", 5.0, 50.0, "2024-05-03", True, "NEW HOLDINGS", 1),
        ("F", 1, "A", 7.0, 70.0, "2024-05-05", True, "RESTATEMENT", 2),
        ("F", 1, "A", 2.0, 20.0, "2024-05-06", True, "NEW HOLDINGS", 3),
        # Sibling CIK under the same reporting family is independently valid.
        ("F", 2, "A", 3.0, 30.0, "2024-05-02", False, None, 0),
    ]
    d = pd.DataFrame(
        rows,
        columns=["filer_id", "cik", "instrument_id", "shares", "value_usd", "filing_date",
                 "is_amendment", "amendment_type", "seq"],
    )
    d["cusip6"] = d["instrument_id"]
    d["instrument_class"] = "fund"
    snap = fold_visible_filings(d, "2024-03-31", "2024-05-10")
    # CIK1 restatement A=7, later NEW A=2, sibling CIK2 A=3.
    assert snap.set_index("instrument_id").loc["A", "shares"] == 12.0
    assert "B" not in set(snap["instrument_id"])
    assert snap["available_date"].nunique() == 1
    assert snap["available_date"].iloc[0] == pd.Timestamp("2024-05-06")


def test_cut_never_uses_later_restatement():
    d = pd.DataFrame(
        {
            "filer_id": ["F", "F"], "cik": [1, 1], "instrument_id": ["A", "A"],
            "shares": [10.0, 99.0], "value_usd": [100.0, 990.0], "cusip6": ["A", "A"],
            "instrument_class": ["fund", "fund"],
            "filing_date": pd.to_datetime(["2024-05-01", "2024-05-20"]),
            "is_amendment": [False, True], "amendment_type": [None, "RESTATEMENT"], "seq": [0, 1],
        }
    )
    snap = fold_visible_filings(d, "2024-03-31", "2024-05-10")
    assert snap["shares"].iloc[0] == 10.0
