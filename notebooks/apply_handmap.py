"""Apply the hand-curated CUSIP->ticker corrections to the crosswalk.

    python notebooks/apply_handmap.py

`prep_universe_wide.py` builds the crosswalk by exact normalized-name
matching against the exchange directory, which EDGAR's name
abbreviations defeat for a value-heavy tail ("LILLY ELI & CO",
"INTERNATIONAL BUSINESS MACHS", ...). The ~230 corrections in
`data-quality-check/fix_crosswalk_top.py::HAND_MAP` were verified by
hand and lift non-ETF value coverage from 63% to 85.4%. This script
merges them into cm_map_wide.csv (idempotent; pure map operation -
prices for any new tickers are fetched automatically by the market
layer on first use).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data-quality-check"))

from fix_crosswalk_top import HAND_MAP  # noqa: E402

NB = ROOT / "notebooks" / "data"


def main() -> None:
    f = NB / "cm_map_wide.csv"
    cmap = pd.read_csv(f, dtype=str).dropna().set_index("instrument_id")[
        "ticker"]
    add = {k: v for k, v in HAND_MAP.items() if k not in cmap.index}
    # CACHE GUARD: the market layer keys its price cache on the count
    # of unique tickers; adding a mapping whose ticker is not already
    # cached would silently trigger a full re-download. On a machine
    # with an existing cache, only add mappings to already-cached
    # tickers; from a clean clone (no cache) everything is added and
    # the first fetch covers it.
    caches = sorted((ROOT / "factors" / "data").glob("prices_*tk_*.csv"))
    if caches:
        cached = set(pd.read_csv(caches[-1], index_col=0, nrows=1).columns)
        add = {k: v for k, v in add.items() if v in cached}
    if not add:
        print("hand-map already applied (0 additions)")
        return
    new_map = pd.concat([cmap, pd.Series(add, dtype=str)])
    new_map = new_map[~new_map.index.duplicated(keep="first")]
    new_map.index.name = "instrument_id"      # concat can drop it
    new_map.rename("ticker").to_csv(f)
    print(f"hand-map applied: +{len(add)} mappings "
          f"({len(new_map)} total)")


if __name__ == "__main__":
    main()
