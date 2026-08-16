"""Indicator: raw values -> cross-sectional scores, multifactor conventions.

`values` is a dates x tickers DataFrame where cell (t, i) uses ONLY
information available at t. That is the whole point-in-time contract and
nothing downstream can repair a violation here — the backtest lags weights
by one day, so an honest indicator can never look ahead.

The raw `inds_raw` matrices plug in exactly here:

    ind = Indicator("meu_sinal", values=inds_raw["meu_sinal"])
    ind.filter_values(universe).generate_z_scores().clip_scores(-3, 3)
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd


class Indicator:
    def __init__(self, name: str, values: Optional[pd.DataFrame] = None):
        self.name = name
        self.values: Optional[pd.DataFrame] = values
        self.scores: Optional[pd.DataFrame] = None

    def filter_values(self, universe: pd.DataFrame) -> "Indicator":
        """Eligibility BEFORE scoring: z-scores must be computed relative to
        the tradable cross-section, or untradable outliers set the scale."""
        univ = universe.reindex_like(self.values).fillna(False)
        self.values = self.values.where(univ)
        return self

    def generate_z_scores(self) -> "Indicator":
        mean = self.values.mean(axis=1)
        std = self.values.std(axis=1)
        self.scores = self.values.subtract(mean, axis=0).divide(std, axis=0)
        return self

    def clip_scores(self, lower: float = -3.0, upper: float = 3.0) -> "Indicator":
        if self.scores is not None:
            self.scores = self.scores.clip(lower=lower, upper=upper)
        return self

    def inverted(self) -> "Indicator":
        inv = Indicator(f"{self.name}-inv", 1.0 / self.values)
        inv.values = inv.values.replace([np.inf, -np.inf], np.nan)
        return inv

    def negated(self) -> "Indicator":
        return Indicator(f"{self.name}-neg", -self.values)
