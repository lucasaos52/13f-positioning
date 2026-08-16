"""Point-in-time quarter store with explicit 13F amendment semantics.

The source parquet contains every filing version.  Folding versions by
``filer_id`` is unsafe because a reporting family can contain several CIKs;
one sibling's later filing would delete another sibling's table.  Versions
are therefore resolved per CIK first and only then aggregated to filer_id.

RESTATEMENT (and an amendment with missing type) replaces the CIK's table.
NEW HOLDINGS is additive, but only when it is later than the currently visible
replacement.  This prevents an old confidential-treatment release from being
carried through a later full restatement.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd


class PITQuarterStore:
    def __init__(self, quarter_dir: str | Path):
        self.quarter_dir = Path(quarter_dir)
        if not self.quarter_dir.exists():
            raise FileNotFoundError(self.quarter_dir)

    def quarters(self) -> list[pd.Timestamp]:
        return sorted(
            pd.Timestamp(p.stem[2:])
            for p in self.quarter_dir.glob("q_*.parquet")
            if p.stem != "filings_meta"
        )

    @lru_cache(maxsize=8)
    def _load(self, period_text: str) -> pd.DataFrame:
        path = self.quarter_dir / f"q_{period_text}.parquet"
        if not path.exists():
            raise FileNotFoundError(f"Missing 13F quarter: {path}")
        return pd.read_parquet(path)

    def snapshot(
        self,
        period: pd.Timestamp | str,
        knowledge_date: pd.Timestamp | str,
        equity_only: bool = True,
    ) -> pd.DataFrame:
        """Return one row per (filer_id, instrument_id) known by the date.

        ``knowledge_date`` is an actual filing cut, never a synthetic
        assumption that every filer reported at the statutory deadline.
        """
        period = pd.Timestamp(period)
        knowledge_date = pd.Timestamp(knowledge_date)
        raw = self._load(str(period.date()))
        d = raw.loc[raw["filing_date"] <= knowledge_date].copy()
        if equity_only:
            # ETFs/funds are excluded: applying issuer size and stock beta to
            # an ETF would describe the wrapper, not its underlying exposure.
            d = d[d["instrument_class"].isin(["common", "other_security"])]
        if d.empty:
            return pd.DataFrame(
                columns=["filer_id", "instrument_id", "shares", "value_usd", "cusip6"]
            )

        amendment = d["amendment_type"].fillna("").str.upper()
        is_new = d["is_amendment"] & amendment.eq("NEW HOLDINGS")
        base = d.loc[~is_new].copy()
        if base.empty:
            return pd.DataFrame(
                columns=["filer_id", "instrument_id", "shares", "value_usd", "cusip6"]
            )

        # A CIK is the filing entity/version owner.  Resolve it before any
        # reporting-family aggregation.
        last_base_seq = base.groupby("cik")["seq"].max().rename("base_seq")
        chosen = base.join(last_base_seq, on="cik")
        chosen = chosen[chosen["seq"] == chosen["base_seq"]].drop(columns="base_seq")

        additive = d.loc[is_new].join(last_base_seq, on="cik")
        additive = additive[
            additive["base_seq"].notna() & (additive["seq"] > additive["base_seq"])
        ].drop(columns="base_seq")
        visible = pd.concat([chosen, additive], ignore_index=True)

        return (
            visible.groupby(["filer_id", "instrument_id"], as_index=False)
            .agg(
                shares=("shares", "sum"),
                value_usd=("value_usd", "sum"),
                cusip6=("cusip6", "first"),
            )
            .sort_values(["filer_id", "instrument_id"], ignore_index=True)
        )
