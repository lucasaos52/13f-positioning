"""Frozen choices for the ETF-positioning experiment.

The primary hypotheses and cutoffs are fixed here so the backtest report can
distinguish a pre-specified test from a diagnostic or an ablation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json


@dataclass(frozen=True)
class ResearchConfig:
    # 2013Q1 contains only a handful of late/amended filings in the local
    # source, so 2013Q2 cannot support a genuine adjacent-quarter trade.
    start_period: str = "2013-09-30"
    snapshot_lag_days: int = 70
    min_manager_book_usd: float = 100_000_000.0
    min_manager_positions: int = 10
    min_manager_return_coverage: float = 0.50
    min_released_managers: int = 100
    min_cross_section: int = 20
    churn_smoothing_quarters: int = 4
    persistence_cap_quarters: int = 4
    min_price: float = 4.0
    min_dollar_volume: float = 5_000_000.0
    liquidity_window_days: int = 63
    min_history_days: int = 126
    quantile_fraction: float = 0.20
    primary_cost_bps: int = 10
    fee_ladder_bps: tuple[int, ...] = (0, 5, 10, 20)
    forward_horizons_days: tuple[int, ...] = (5, 21, 63)
    # Research verdict gates. A trivially positive subperiod is not evidence
    # of economically persistent alpha.
    min_full_net_sharpe: float = 0.50
    min_subperiod_net_sharpe: float = 0.25
    min_ic_tstat: float = 1.96
    # A broad-index ETF is intentionally excluded from the primary
    # doubling-down test, following the memo's cash-management warning.
    specific_styles: tuple[str, ...] = ("sector", "industry", "country", "factor", "thematic")

    def fingerprint(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return sha256(payload.encode()).hexdigest()[:12]
