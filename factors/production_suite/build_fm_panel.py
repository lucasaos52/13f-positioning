"""Build the FM-score daily indicator panel (expanding-lambda E[r]
from run_score.build_panels) and back-test it in the production
engine, dumping the net PnL series for the paper.

    python build_fm_panel.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
for sub in ("", "general_plan", "score_model", "fire_calendar",
            "manager_factor_positioning"):
    sys.path.insert(0, str(HERE.parent / sub))

from run_all import load_market, log                # noqa: E402
from run_score import (                             # noqa: E402
    MIN_HIST, PREDICTORS, build_panels)

PANELS = HERE / "data" / "panels"
PNL = HERE / "data" / "pnl"


def main() -> None:
    cmap, mdta = load_market()
    dates = mdta.prices.index
    panels = build_panels()
    log(f"{len(panels)} quarters")

    # per-quarter lambdas
    lams = []
    for p, X, fwd in panels:
        df = pd.concat([X, fwd.rename("f")], axis=1).dropna()
        A = np.column_stack([np.ones(len(df)), df[PREDICTORS].values])
        lam, *_ = np.linalg.lstsq(A, df["f"].values, rcond=None)
        lams.append(pd.Series(lam[1:], index=PREDICTORS, name=p))
    LAM = pd.DataFrame(lams)

    # expanding-mean E[r] stamped at each decision date, ffilled ~1 quarter
    cross = {}
    for ti in range(MIN_HIST, len(panels)):
        p, X, _ = panels[ti]
        lam_bar = LAM.iloc[:ti].mean()
        er = (X[PREDICTORS] * lam_bar).sum(axis=1)
        dec = p + pd.Timedelta(days=45)
        di = dates.searchsorted(dec, side="right") - 1
        cross[dates[di]] = er
    panel = pd.DataFrame(cross).T.sort_index()
    panel = panel.reindex(index=dates).ffill(limit=70)
    panel = panel[[c for c in panel.columns if c in mdta.prices.columns]]
    PANELS.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(PANELS / "fm_score.parquet")
    log(f"panel saved: {panel.shape}")

    os.chdir(HERE.parent)
    from backtest import Backtest
    from filters import Filters
    from portfolio import Portfolio
    flt = Filters(mdta)
    os.chdir(HERE)

    inds = panel.reindex(index=dates)
    changed = (inds != inds.shift(1)).sum(axis=1)
    has = inds.notna().sum(axis=1)
    idx = np.flatnonzero(
        (changed > max(20, int(has[has > 0].median() * 0.30))).values)
    keep = [idx[0]]
    for i in idx[1:]:
        if i - keep[-1] > 20:
            keep.append(i)
    idx = np.array(keep)
    p_ = Portfolio.from_indicator("fm_score", inds, flt.universe,
                                  side="HML", pct=0.2, min_stocks=40)
    p_ = p_.normalize(type="split")
    p_.rebalance(idx, mdta.prices)
    rr = Backtest([p_]).get_returns(mdta, trading_fee=0.0005).iloc[:, 0] \
        .dropna()
    rr = rr[rr.index >= dates[idx[0]]]
    PNL.mkdir(parents=True, exist_ok=True)
    rr.rename("net_ret").to_csv(PNL / "fm_score.csv")
    ann, vol = rr.mean() * 252, rr.std() * np.sqrt(252)
    eq = rr.cumsum()
    log(f"fm_score: ann={ann:+.2%} Sharpe={ann / vol:.2f} "
        f"maxDD={(eq - eq.cummax()).min():+.2%}")


if __name__ == "__main__":
    main()
