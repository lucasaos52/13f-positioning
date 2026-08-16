"""Typed configuration for the crowdflow pipeline.

Every tunable lives here so that a run is fully described by one YAML file plus
a git SHA. Nothing in the pipeline reads a magic number from the body of a
function.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------------- #
# Sections
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class EdgarCfg:
    """SEC EDGAR access.

    ``user_agent`` is not optional politeness: SEC blocks (403) any client that
    does not declare a contact address. ``max_rps`` must stay <= 10.
    """

    user_agent: str = "crowdflow-research contact@example.com"
    max_rps: float = 6.0
    max_retries: int = 5
    backoff_base_s: float = 1.5
    timeout_s: float = 30.0
    first_quarter: str = "2013Q2"  # XML information tables become universal
    last_quarter: str = "2024Q4"


@dataclass(frozen=True)
class CurateCfg:
    """Holdings normalisation and the bitemporal store."""

    # 13F line items we refuse to treat as an equity position.
    drop_option_overlays: bool = True  # putCall in {PUT, CALL}
    drop_principal_amounts: bool = True  # sshPrnamtType == PRN (debt)
    repair_cusip_check_digit: bool = True
    max_cusip_repair_distance: int = 1

    # Value units changed from USD thousands to whole USD for filings made on
    # or after 2023-01-03 (SEC Release 34-95148). Detected, not assumed.
    thousands_cutover_date: str = "2023-01-03"
    unit_sniff_median_threshold: float = 50_000.0

    # Amended filings.
    honour_restatement_flag: bool = True
    treat_unflagged_amendment_as: str = "restatement"  # conservative default


@dataclass(frozen=True)
class UniverseCfg:
    """Dynamic manager-universe selection."""

    min_history_quarters: int = 4
    min_equity_book_usd: float = 5e8
    min_positions: int = 15
    max_single_name_weight: float = 0.60  # kills single-ticker shells

    impact_exponent: float = 0.5  # square-root law; 1.0 => linear
    impact_use_dollar_cost: bool = True

    centrality_mode: str = "degree"  # {"degree", "eigenvector"}
    centrality_log1p: bool = True

    turnover_halflife_q: float = 3.0
    turnover_lookback_q: int = 8

    weights: dict[str, float] = field(
        default_factory=lambda: {"impact": 0.40, "centrality": 0.40, "turnover": 0.20}
    )

    target_size: int = 25
    buffer_size: int = 35  # hysteresis: enter at <=target, leave only above this
    selection_lag_quarters: int = 1


@dataclass(frozen=True)
class FactorCfg:
    """Stock-level positioning factors."""

    quarter_trading_days: int = 63
    winsor_pct: float = 0.01
    min_holders_for_consensus: int = 3
    fragility_flow_lookback_q: int = 12
    fragility_shrinkage: float = 0.25  # Ledoit-Wolf style pull to diagonal
    neutralise: tuple[str, ...] = ("log_mktcap", "log_amihud")


@dataclass(frozen=True)
class BacktestCfg:
    """Portfolio construction and evaluation."""

    rebalance: str = "M"
    price_floor_usd: float = 5.0
    max_names: int = 3000
    quantiles: int = 5

    gross_leverage: float = 1.0
    dollar_neutral: bool = True
    max_weight: float = 0.02
    signal_staleness_cap_days: int = 200

    spread_bps: float = 4.0
    impact_coef_bps: float = 12.0  # cost = coef * sigma_ann * sqrt(trade/ADV)
    borrow_bps_ann: float = 40.0

    horizons_months: tuple[int, ...] = (1, 3, 6, 12)
    newey_west_lags: int = 6


@dataclass(frozen=True)
class PathsCfg:
    root: str = str(REPO_ROOT / "data")

    def layer(self, name: str) -> Path:
        p = Path(self.root) / name
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def raw(self) -> Path:
        return self.layer("00_raw")

    @property
    def parsed(self) -> Path:
        return self.layer("10_parsed")

    @property
    def curated(self) -> Path:
        return self.layer("20_curated")

    @property
    def features(self) -> Path:
        return self.layer("30_features")

    @property
    def results(self) -> Path:
        return self.layer("40_results")


@dataclass(frozen=True)
class Config:
    edgar: EdgarCfg = field(default_factory=EdgarCfg)
    curate: CurateCfg = field(default_factory=CurateCfg)
    universe: UniverseCfg = field(default_factory=UniverseCfg)
    factor: FactorCfg = field(default_factory=FactorCfg)
    backtest: BacktestCfg = field(default_factory=BacktestCfg)
    paths: PathsCfg = field(default_factory=PathsCfg)
    seed: int = 20240614
    offline: bool = False

    # ------------------------------------------------------------------ #
    @classmethod
    def load(cls, path: str | Path | None = None) -> Config:
        if path is None:
            path = REPO_ROOT / "config" / "default.yaml"
        path = Path(path)
        blob: dict[str, Any] = {}
        if path.exists():
            blob = yaml.safe_load(path.read_text()) or {}

        # Environment wins over YAML for the two things that are machine-local.
        if ua := os.environ.get("CROWDFLOW_USER_AGENT"):
            blob.setdefault("edgar", {})["user_agent"] = ua
        if root := os.environ.get("CROWDFLOW_DATA_ROOT"):
            blob.setdefault("paths", {})["root"] = root
        if os.environ.get("CROWDFLOW_OFFLINE", "").lower() in {"1", "true", "yes"}:
            blob["offline"] = True

        sections = {
            "edgar": EdgarCfg,
            "curate": CurateCfg,
            "universe": UniverseCfg,
            "factor": FactorCfg,
            "backtest": BacktestCfg,
            "paths": PathsCfg,
        }
        kwargs: dict[str, Any] = {}
        for key, klass in sections.items():
            payload = blob.get(key) or {}
            fields = {f.name for f in dataclasses.fields(klass)}
            unknown = set(payload) - fields
            if unknown:
                raise ValueError(f"unknown keys in config section '{key}': {sorted(unknown)}")
            coerced = {
                k: tuple(v) if isinstance(getattr(klass(), k, None), tuple) else v
                for k, v in payload.items()
            }
            kwargs[key] = klass(**coerced)
        for scalar in ("seed", "offline"):
            if scalar in blob:
                kwargs[scalar] = blob[scalar]
        return cls(**kwargs)

    def fingerprint(self) -> str:
        """Stable hash of the config, stamped onto every artefact."""
        payload = json.dumps(dataclasses.asdict(self), sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()[:12]
