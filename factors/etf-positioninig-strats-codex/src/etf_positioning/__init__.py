"""Research primitives for point-in-time 13F x ETF signals."""

from .config import ResearchConfig
from .signals import (
    conditioned_reversal,
    direct_vs_etf_conviction,
    etf_fragility,
    filing_time_demand_nowcast,
    lookthrough_pressure,
    overlap_network_shock,
    raw_etf_ownership_change,
    run_prone_pressure,
    specialized_pressure,
)
from .universe import build_manager_features, classify_etfs, manager_style_flags
from .universe import manager_quality_weights
from .evaluation import event_study

__all__ = [
    "ResearchConfig",
    "build_manager_features",
    "classify_etfs",
    "manager_style_flags",
    "manager_quality_weights",
    "event_study",
    "raw_etf_ownership_change",
    "lookthrough_pressure",
    "etf_fragility",
    "filing_time_demand_nowcast",
    "specialized_pressure",
    "run_prone_pressure",
    "direct_vs_etf_conviction",
    "overlap_network_shock",
    "conditioned_reversal",
]
