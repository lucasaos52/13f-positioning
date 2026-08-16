from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd
import pytest

HERE = Path(__file__).resolve().parents[1]
FACTORS = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(FACTORS))


@pytest.fixture
def master() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "instrument_id": ["ETF1", "ETF2"],
            "ticker": ["AAA", "BBB"],
            "name": ["A ETF", "B ETF"],
            "asset_class": ["equity", "equity"],
            "etf_style": ["broad", "sector"],
            "specialized_score": [0.0, 1.0],
            "is_etf": [True, True],
            "verification_source": ["official", "official"],
            "is_specific": [False, True],
        }
    )

