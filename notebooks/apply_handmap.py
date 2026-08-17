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
    # note: adding mappings changes the unique-ticker count, and the
    # market layer keys its price cache on that count - so the next
    # load after new additions triggers a (cheap, incremental-by-
    # design on fresh clones) re-fetch. Run this BEFORE the first
    # price fetch, which is what bootstrap.py does.
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
