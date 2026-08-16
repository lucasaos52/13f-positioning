"""High-precision ETF universe and auditable candidate quarantine.

``instrument_class == fund`` is a high-recall SEC-title classification, not
an ETF identifier.  It also contains closed-end funds, BDCs, trusts and some
ordinary shares misclassified by noisy titles.  The primary strategies use
only CUSIPs independently verified as exchange-traded products.  The broad
``fund`` set is retained solely as a coverage audit; regex candidates are
never silently promoted into the tradable backtest.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


REQUIRED_MASTER_COLUMNS = {
    "instrument_id",
    "ticker",
    "name",
    "asset_class",
    "etf_style",
    "specialized_score",
    "is_etf",
    "verification_source",
}


def load_verified_master(
    path: str | Path,
    equity_only: bool = True,
    passive_only: bool = False,
) -> pd.DataFrame:
    """Load verified identifiers while allowing CUSIP/FIGI aliases per ticker.

    The same ETF can enter SEC holdings under its CUSIP or its share-class
    FIGI.  Those are valid identity aliases, not duplicate products.  Metadata
    must nevertheless agree within ticker; conflicting aliases fail closed.
    """

    master = pd.read_csv(path, dtype={"instrument_id": str})
    missing = REQUIRED_MASTER_COLUMNS - set(master)
    if missing:
        raise ValueError(f"ETF master missing columns: {sorted(missing)}")
    if master["instrument_id"].duplicated().any():
        dupes = master.loc[master["instrument_id"].duplicated(), "instrument_id"].tolist()
        raise ValueError(f"duplicate ETF CUSIPs in master: {dupes[:5]}")
    master["is_etf"] = master["is_etf"].astype(bool)
    master = master[master["is_etf"]].copy()
    if equity_only:
        master = master[master["asset_class"].eq("equity")].copy()
    if passive_only:
        if "is_passive_equity_etf" not in master:
            raise ValueError("passive_only requires is_passive_equity_etf")
        master = master[master["is_passive_equity_etf"].astype(bool)].copy()
    # Names can legitimately differ across filings/vendors (for example a
    # legal series name versus the exchange display name).  Product traits,
    # unlike display names, must agree across aliases.
    metadata = ["asset_class", "etf_style", "specialized_score"]
    conflicts = master.groupby("ticker")[metadata].nunique(dropna=True).gt(1).any(axis=1)
    if conflicts.any():
        raise ValueError(
            f"conflicting metadata across ticker aliases: {conflicts[conflicts].index[:5].tolist()}"
        )
    master["is_specific"] = master["etf_style"].isin(
        ["sector", "industry", "country", "factor", "thematic"]
    )
    master["universe_status"] = "verified_primary"
    return master.reset_index(drop=True)


def build_universe_audit(
    fund_candidate_audit: str | Path,
    master: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return instrument and aggregate coverage audits.

    Coverage is reported both in dollars and instrument counts.  The dollar
    measure is descriptive because values are summed over time; it is not AUM.
    """

    candidates = pd.read_csv(fund_candidate_audit, dtype={"instrument_id": str})
    verified_ids = set(master["instrument_id"])
    candidates["universe_status"] = np.where(
        candidates["instrument_id"].isin(verified_ids),
        "verified_primary",
        "quarantined_fund_candidate",
    )
    candidates["exclusion_reason"] = np.where(
        candidates["instrument_id"].isin(verified_ids),
        "",
        "fund flag alone does not prove ETF identity/ticker",
    )
    total_value = float(candidates["disclosed_value_usd"].sum())
    verified_value = float(
        candidates.loc[candidates["instrument_id"].isin(verified_ids), "disclosed_value_usd"].sum()
    )
    summary = pd.DataFrame(
        [
            {
                "candidate_instruments": len(candidates),
                "verified_equity_etfs": master["ticker"].nunique(),
                "verified_instrument_aliases": len(master),
                "candidate_historical_value_usd": total_value,
                "verified_historical_value_usd": verified_value,
                "verified_value_coverage": verified_value / total_value if total_value else np.nan,
                "universe_rule": "verified CUSIP+ticker+asset class; current price must exist as-of event",
            }
        ]
    )
    return candidates, summary
