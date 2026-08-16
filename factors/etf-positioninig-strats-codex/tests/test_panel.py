import pandas as pd
from unittest.mock import patch

from etf_positioning.panel import snapshot_as_of


def test_restatement_replaces_earlier_additive_and_keeps_sibling():
    rows = [
        ("a0", "family", 1, "A", 10, 100, "2023-04-10", None, False, 0),
        ("a1", "family", 1, "B", 5, 50, "2023-04-20", "NEW HOLDINGS", True, 1),
        ("a2", "family", 1, "A", 20, 200, "2023-05-01", "RESTATEMENT", True, 2),
        ("b0", "family", 2, "A", 3, 30, "2023-04-15", None, False, 0),
    ]
    df = pd.DataFrame(rows, columns=[
        "accession", "filer_id", "cik", "instrument_id", "shares", "value_usd",
        "filing_date", "amendment_type", "is_amendment", "seq",
    ])
    df["instrument_class"] = "common"
    df["cusip6"] = df["instrument_id"]
    with patch("etf_positioning.panel.pd.read_parquet", return_value=df):
        out = snapshot_as_of("q_2023-03-31.parquet", "2023-05-10")
    assert set(out["instrument_id"]) == {"A"}
    assert out.loc[out["instrument_id"].eq("A"), "shares"].iloc[0] == 23
