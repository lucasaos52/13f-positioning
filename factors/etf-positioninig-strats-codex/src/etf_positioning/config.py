"""Small, frozen configuration surface for reproducible ETF research."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json


@dataclass(frozen=True)
class ResearchConfig:
    """Parameters chosen before seeing strategy returns.

    The defaults follow the blueprint: share changes, a conservative 70-day
    quarterly snapshot for the first empirical pass, lagged covariance, and
    several fixed horizons.  They are deliberately centralized so a result is
    never separated from the choices that produced it.
    """

    snapshot_lag_days: int = 70
    min_manager_book_usd: float = 100_000_000.0
    min_manager_positions: int = 10
    etf_specialist_threshold: float = 0.25
    direct_specialist_threshold: float = 0.05
    transient_turnover_quantile: float = 0.75
    covariance_lookback: int = 12
    covariance_min_periods: int = 8
    covariance_shrinkage: float = 0.50
    winsor_lower: float = 0.01
    winsor_upper: float = 0.99
    quantile_fraction: float = 0.20
    trading_cost_bps: float = 10.0
    horizons_days: tuple[int, ...] = (5, 21, 63, 126)

    def fingerprint(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return sha256(payload.encode()).hexdigest()[:12]

