"""Version-folding tests pin bugs that silently rewrite manager books."""
from __future__ import annotations

import pandas as pd

from classical_positioning.pit import PITQuarterStore


def _row(cik, seq, instrument, value, filed, *, amendment=False, kind=None):
    return {
        "accession": f"{cik}-{seq}",
        "filer_id": "FAMILY",
        "cik": cik,
        "instrument_id": instrument,
        "cusip6": instrument[:6],
        "instrument_class": "common",
        "shares": int(value),
        "value_usd": float(value),
        "filing_date": pd.Timestamp(filed),
        "amendment_type": kind,
        "is_amendment": amendment,
        "seq": seq,
    }


def test_amendments_fold_by_cik_before_reporting_family(local_tmp):
    """A sibling CIK's later filing must not delete the other sibling book."""
    rows = [
        _row(1, 0, "A", 100, "2024-02-01"),
        _row(1, 1, "B", 20, "2024-02-05", amendment=True, kind="NEW HOLDINGS"),
        _row(1, 2, "A", 150, "2024-02-10", amendment=True, kind="RESTATEMENT"),
        _row(1, 3, "C", 30, "2024-02-12", amendment=True, kind="NEW HOLDINGS"),
        _row(2, 0, "D", 40, "2024-02-03"),
    ]
    pd.DataFrame(rows).to_parquet(local_tmp / "q_2023-12-31.parquet", index=False)
    store = PITQuarterStore(local_tmp)
    snap = store.snapshot("2023-12-31", "2024-02-15").set_index("instrument_id")
    assert set(snap.index) == {"A", "C", "D"}
    assert snap.loc["A", "value_usd"] == 150
    assert snap.loc["D", "value_usd"] == 40


def test_knowledge_cut_does_not_see_later_restatement(local_tmp):
    rows = [
        _row(1, 0, "A", 100, "2024-02-01"),
        _row(1, 1, "B", 20, "2024-02-05", amendment=True, kind="NEW HOLDINGS"),
        _row(1, 2, "A", 150, "2024-02-10", amendment=True, kind="RESTATEMENT"),
    ]
    pd.DataFrame(rows).to_parquet(local_tmp / "q_2023-12-31.parquet", index=False)
    snap = PITQuarterStore(local_tmp).snapshot("2023-12-31", "2024-02-07")
    values = snap.set_index("instrument_id")["value_usd"]
    assert values.to_dict() == {"A": 100.0, "B": 20.0}


def test_fund_wrappers_are_not_treated_as_stocks(local_tmp):
    row = _row(1, 0, "ETF", 100, "2024-02-01")
    row["instrument_class"] = "fund"
    pd.DataFrame([row]).to_parquet(local_tmp / "q_2023-12-31.parquet", index=False)
    assert PITQuarterStore(local_tmp).snapshot("2023-12-31", "2024-02-07").empty
