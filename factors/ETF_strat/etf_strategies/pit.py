"""13F bitemporal folding with explicit amendment semantics."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd


EMPTY_COLUMNS = [
    "filer_id",
    "instrument_id",
    "shares",
    "value_usd",
    "cusip6",
    "instrument_class",
    "available_date",
]


class PITQuarterStore:
    """Materialize only filing versions known by a real calendar date.

    Versions are resolved by CIK before sibling CIKs are aggregated to the
    repository's filer family.  A restatement replaces the CIK table; a later
    ``NEW HOLDINGS`` amendment is additive.  The upstream store retains dates,
    not SEC acceptance timestamps, so the whole selected manager book is
    conservatively released at that manager's latest selected filing date.
    """

    def __init__(self, quarter_dir: str | Path):
        self.quarter_dir = Path(quarter_dir)

    def quarters(self) -> list[pd.Timestamp]:
        return sorted(pd.Timestamp(p.stem[2:]) for p in self.quarter_dir.glob("q_*.parquet"))

    @lru_cache(maxsize=3)
    def _load(self, period_text: str) -> pd.DataFrame:
        path = self.quarter_dir / f"q_{period_text}.parquet"
        if not path.exists():
            raise FileNotFoundError(path)
        out = pd.read_parquet(path)
        out["filing_date"] = pd.to_datetime(out["filing_date"])
        return out

    def snapshot(self, period: str | pd.Timestamp, knowledge_date: str | pd.Timestamp) -> pd.DataFrame:
        period = pd.Timestamp(period)
        cut = pd.Timestamp(knowledge_date)
        raw = self._load(str(period.date()))
        return fold_visible_filings(raw, period, cut)


def fold_visible_filings(
    raw: pd.DataFrame,
    period: str | pd.Timestamp,
    knowledge_date: str | pd.Timestamp,
) -> pd.DataFrame:
        """Pure folding function, exposed so amendment invariants are testable."""

        period = pd.Timestamp(period)
        cut = pd.Timestamp(knowledge_date)
        raw = raw.copy()
        raw["filing_date"] = pd.to_datetime(raw["filing_date"])
        d = raw[raw["filing_date"].le(cut)].copy()
        if d.empty:
            return pd.DataFrame(columns=EMPTY_COLUMNS)

        amendment = d["amendment_type"].fillna("").str.upper()
        is_new = d["is_amendment"].astype(bool) & amendment.eq("NEW HOLDINGS")
        base = d[~is_new].copy()
        if base.empty:
            return pd.DataFrame(columns=EMPTY_COLUMNS)

        last_base = base.groupby("cik")["seq"].max().rename("last_base_seq")
        chosen = base.join(last_base, on="cik")
        chosen = chosen[chosen["seq"].eq(chosen["last_base_seq"])].drop(columns="last_base_seq")
        additive = d[is_new].join(last_base, on="cik")
        additive = additive[
            additive["last_base_seq"].notna() & additive["seq"].gt(additive["last_base_seq"])
        ].drop(columns="last_base_seq")
        visible = pd.concat([chosen, additive], ignore_index=True)

        # The max selected date is used for every instrument in the manager
        # book. This can delay information, but cannot release a later
        # amendment early.
        release = visible.groupby("filer_id")["filing_date"].max().rename("available_date")
        out = (
            visible.groupby(["filer_id", "instrument_id"], as_index=False)
            .agg(
                shares=("shares", "sum"),
                value_usd=("value_usd", "sum"),
                cusip6=("cusip6", "first"),
                instrument_class=("instrument_class", "first"),
            )
            .join(release, on="filer_id")
        )
        out["period_end"] = period
        return out.sort_values(["filer_id", "instrument_id"], ignore_index=True)
