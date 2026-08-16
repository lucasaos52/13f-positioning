"""Frozen research configuration.

Every economic cut lives here so a run can be reproduced and reviewed.  The
defaults are hypotheses from the implementation memo, not values selected on
backtest performance.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path


@dataclass(frozen=True)
class ResearchConfig:
    decision_lag_days: int = 45
    start_quarter: str = "2013-06-30"
    characteristic_min_price: float = 1.0
    characteristic_min_adv: float = 100_000.0
    min_price: float = 5.0
    min_adv: float = 5_000_000.0
    min_history_days: int = 252
    min_manager_positions: int = 15
    min_manager_aum: float = 100_000_000.0
    min_factor_coverage: float = 0.80
    winsor_low: float = 0.01
    winsor_high: float = 0.99
    market_cap_floor: float = 10_000_000.0
    market_cap_ceiling: float = 10_000_000_000_000.0
    benchmark_cap_winsor: float = 0.99
    factor_names: tuple[str, ...] = (
        "size", "momentum", "beta", "lowvol", "liquidity"
    )
    portfolio_quantile: float = 0.20
    portfolio_min_stocks: int = 50
    fee_bps: tuple[int, ...] = (0, 5, 10, 20)
    borrow_rate: float = 0.005

    def fingerprint(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, default=list)
        return sha256(payload.encode("utf-8")).hexdigest()[:12]

    def write(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(asdict(self), indent=2, default=list), encoding="utf-8")
