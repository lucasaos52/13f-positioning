"""Dynamic universe selection.

The alternative this replaces is a hand-picked static roster of managers,
chosen on today's reputation or assets. The reasons to replace it are not
aesthetic:

* **A static list embeds the present into the past.** Whoever is prominent
  today was selected by their survival and their returns. Running them through
  a 2015 backtest is selection on the dependent variable, and it is the single
  largest source of inflated performance in 13F studies.
* **Size is the wrong axis.** A manager with $100bn of bonds and $2bn of
  equities has a small equity footprint. A manager with $8bn concentrated in
  small caps has a large one. 13F only shows the equity sleeve, so a
  fame-based or AUM-based list systematically misranks the thing that matters.
* **The normalisation trap.** A fund whose entire disclosed 13F book is one
  ETF position looks maximally concentrated and maximally "high conviction"
  under any within-manager weighting scheme, and will dominate a crowding
  factor for reasons that have nothing to do with price pressure. Ranking on
  absolute liquidity footprint rather than on within-book weights removes this
  by construction.

Selection rule:

    Score(m, t) = 0.4 * pct_rank(Impact) + 0.4 * pct_rank(Centrality)
                + 0.2 * pct_rank(TurnoverEWMA)

    Universe(t) = top N by Score(m, t-1), with a hysteresis band

Two properties are load-bearing.

**The lag.** The universe for quarter t is chosen from quarter t-1 scores,
computed from filings already public. We never select managers using the same
filings we then extract a signal from, and we never select on realised
performance at all. The defensible sentence is: *managers are chosen ex ante
for their lagged capacity to transmit correlated demand into equities, not for
having been right.*

**The buffer.** A hard top-N cut makes membership flicker on rank noise near
the boundary, and every flicker is a spurious full-position turnover in the
factor. A manager enters at rank <= target and only leaves above a wider
threshold. This is standard index-construction practice and it materially
reduces factor turnover for no loss of economic content.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from ..config import UniverseCfg

log = logging.getLogger(__name__)

SCORE_INPUTS = {"impact": "impact_cost_usd", "centrality": "centrality", "turnover": "turnover_ewma"}


def apply_eligibility(footprints: pd.DataFrame, cfg: UniverseCfg) -> pd.DataFrame:
    """Hard filters, applied before ranking so they cannot be out-scored.

    Each is a statement about whether the filer is a meaningful equity
    decision-maker at all, not about how strong its footprint is.
    """
    df = footprints.copy()
    df["elig_history"] = df["n_quarters_history"] >= cfg.min_history_quarters
    df["elig_book"] = df["book_usd"] >= cfg.min_equity_book_usd
    df["elig_breadth"] = df["n_positions"] >= cfg.min_positions
    # A book dominated by one line is a wrapper, a single-stock vehicle, or a
    # filer whose real portfolio is not in scope of 13F.
    df["elig_diversified"] = df["top1_weight"] <= cfg.max_single_name_weight
    df["elig_turnover"] = df["turnover_ewma"].notna()

    flags = [c for c in df.columns if c.startswith("elig_")]
    df["eligible"] = df[flags].all(axis=1)
    return df


def _pct_rank(s: pd.Series) -> pd.Series:
    return s.rank(pct=True, na_option="keep")


def score_managers(footprints: pd.DataFrame, cfg: UniverseCfg) -> pd.DataFrame:
    """Cross-sectional percentile ranks within each quarter, then weighted sum."""
    df = apply_eligibility(footprints, cfg)
    weights = cfg.weights
    total_w = sum(weights.values())
    if not np.isclose(total_w, 1.0):
        log.warning("score weights sum to %.3f; renormalising", total_w)

    parts = []
    for period, grp in df.groupby("period_end", sort=True):
        elig = grp[grp["eligible"]].copy()
        if elig.empty:
            parts.append(grp.assign(score=np.nan, rank=np.nan))
            continue
        score = pd.Series(0.0, index=elig.index)
        for name, col in SCORE_INPUTS.items():
            r = _pct_rank(elig[col])
            elig[f"rank_{name}"] = r
            score += (weights.get(name, 0.0) / total_w) * r.fillna(r.median())
        elig["score"] = score
        elig["rank"] = elig["score"].rank(ascending=False, method="first")
        rest = grp[~grp["eligible"]].assign(score=np.nan, rank=np.nan)
        parts.append(pd.concat([elig, rest]))
    return pd.concat(parts, ignore_index=True).sort_values(["period_end", "rank"])


def select_universe(scored: pd.DataFrame, cfg: UniverseCfg) -> pd.DataFrame:
    """Walk quarters forward applying the lag and the hysteresis band.

    Returns one row per (period_end, filer_id) that is *in the universe for
    signal construction in that quarter*, together with the quarter whose
    scores justified the membership.
    """
    periods = sorted(scored["period_end"].unique())
    by_period = {p: g for p, g in scored.groupby("period_end")}

    incumbents: set[str] = set()
    rows: list[dict] = []

    for i, period in enumerate(periods):
        j = i - cfg.selection_lag_quarters
        if j < 0:
            continue
        source_period = periods[j]
        src = by_period[source_period]
        ranked = src[src["score"].notna()].sort_values("rank")
        if ranked.empty:
            continue

        rank_map = dict(zip(ranked["filer_id"], ranked["rank"]))

        # Hysteresis, in the order that makes the band actually bind:
        # incumbents keep their slot while they remain inside the wider buffer,
        # and only the slots they vacate are offered to newcomers, who must
        # clear the tighter target rank. Giving newcomers priority instead
        # would make the buffer decorative - there are always exactly
        # `target_size` names inside the tight band, so nothing would ever be
        # retained on the strength of incumbency.
        retained = sorted(
            (m for m in incumbents if rank_map.get(m, np.inf) <= cfg.buffer_size),
            key=lambda m: rank_map[m],
        )[: cfg.target_size]

        free_slots = cfg.target_size - len(retained)
        newcomers = [
            m
            for m in ranked.loc[ranked["rank"] <= cfg.target_size, "filer_id"]
            if m not in retained
        ][: max(free_slots, 0)]

        selected = set(retained) | set(newcomers)

        for m in selected:
            rows.append(
                {
                    "period_end": period,
                    "source_period_end": source_period,
                    "filer_id": m,
                    "rank": rank_map.get(m, np.nan),
                    "status": "new" if m not in incumbents else "retained",
                }
            )
        incumbents = selected

    out = pd.DataFrame(rows)
    if not out.empty:
        log.info(
            "universe: %d quarters, mean size %.1f, mean turnover %.1f names/quarter",
            out["period_end"].nunique(),
            out.groupby("period_end").size().mean(),
            out[out["status"] == "new"].groupby("period_end").size().reindex(
                out["period_end"].unique(), fill_value=0
            ).mean(),
        )
    return out


def universe_stability(universe: pd.DataFrame) -> pd.DataFrame:
    """Diagnostics on how much the universe churns.

    A universe that reconstitutes itself every quarter is not a universe, it is
    a signal - and an unstable one whose turnover the backtest must pay for.
    """
    rows = []
    prev: set[str] = set()
    for period, grp in universe.groupby("period_end", sort=True):
        cur = set(grp["filer_id"])
        rows.append(
            {
                "period_end": period,
                "size": len(cur),
                "entries": len(cur - prev),
                "exits": len(prev - cur),
                "jaccard_vs_prev": len(cur & prev) / max(len(cur | prev), 1),
            }
        )
        prev = cur
    out = pd.DataFrame(rows)
    if not out.empty:
        all_members = set(universe["filer_id"])
        tenure = universe.groupby("filer_id").size()
        out.attrs["n_distinct_managers"] = len(all_members)
        out.attrs["median_tenure_quarters"] = float(tenure.median())
    return out
