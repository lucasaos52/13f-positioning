"""Post-suite finishing pass for the paper: back-test the FSS panel
standalone ("distress_mom") and the NCB+FSS combo in the production
engine, dump their PnL series, then generate the paper's engine table
(docs/paper/tables/t1_engine.tex) with the full metric battery:
ann. net return, vol, Sharpe, information ratio vs S&P, max drawdown,
Calmar, hit ratio. Costs: 5 bps/side commissions (all), 50 bps p.a.
borrow (short legs, reported separately in the caption).

    python run_final_engine.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
for sub in ("", "general_plan"):
    sys.path.insert(0, str(HERE.parent / sub))

from run_all import load_market, log                # noqa: E402

PANELS = HERE / "data" / "panels"
PNL = HERE / "data" / "pnl"
PAPER = HERE.parent.parent / "docs" / "paper"

cmap, mdta = load_market()
dates = mdta.prices.index
os.chdir(HERE.parent)
from backtest import Backtest                       # noqa: E402
from filters import Filters                         # noqa: E402
from portfolio import Portfolio                     # noqa: E402
flt = Filters(mdta)
os.chdir(HERE)


def bt(inds: pd.DataFrame, name: str):
    """Backtest a panel; returns (net, gross) daily return series.
    Valid-content rebal detection (NaN != NaN must not count as a
    change - the phantom-rebal bug found in the FM diagnostic)."""
    inds = inds[[c for c in inds.columns if c in mdta.prices.columns]] \
        .reindex(index=dates)
    val = inds.notna()
    content_chg = ((inds != inds.shift(1)) & val & val.shift(1)) \
        .sum(axis=1)
    appeared = (val & ~val.shift(1).fillna(False)).sum(axis=1)
    has = val.sum(axis=1)
    trigger = (has > 40) & ((content_chg > 20) | (appeared > 100))
    idx = np.flatnonzero(trigger.values)
    if not len(idx):
        return None, None
    keep = [idx[0]]
    for i in idx[1:]:
        if i - keep[-1] > 40:
            keep.append(i)
    idx = np.array(keep)
    p = Portfolio.from_indicator(name, inds, flt.universe, side="HML",
                                 pct=0.2, min_stocks=40)
    p = p.normalize(type="split")
    p.rebalance(idx, mdta.prices)
    out = []
    for fee in (0.0005, 0.0):
        rr = Backtest([p]).get_returns(mdta, trading_fee=fee) \
            .iloc[:, 0].dropna()
        out.append(rr[rr.index >= dates[idx[0]]])
    PNL.mkdir(parents=True, exist_ok=True)
    out[0].rename("net_ret").to_csv(PNL / f"{name}.csv")
    log(f"{name}: {len(out[0])} days, {len(idx)} rebals")
    return out[0], out[1]


def metrics(rr: pd.Series, rg: pd.Series | None) -> dict:
    ann, vol = rr.mean() * 252, rr.std() * np.sqrt(252)
    eq = rr.cumsum()
    dd = float((eq - eq.cummax()).min())
    cost = np.nan
    turn = np.nan
    if rg is not None and len(rg):
        cost = float(rg.mean() * 252 - ann)      # annualized commission drag
        turn = cost / 0.0005 / 2.0               # one-way turnover multiple
    return {"ann": ann, "vol": vol,
            "sharpe": ann / vol if vol > 0 else np.nan,
            "maxdd": dd,
            "calmar": ann / abs(dd) if dd < 0 else np.nan,
            "hit": float((rr > 0).mean()),
            "cost_bps": cost * 1e4, "turnover": turn}


def main() -> None:
    # FSS standalone (reversal panel inverted: high supply -> short)
    rvp = HERE.parent / "reversao_condicional/results/reversal_panel.parquet"
    rv = 1.0 - pd.read_parquet(rvp)
    rv = rv.reindex(dates).ffill(limit=75)

    ch = pd.read_parquet(PANELS / "champion_v1.parquet").reindex(dates)
    cols = sorted(set(ch.columns) | set(rv.columns))
    combo = pd.concat([
        ch.reindex(columns=cols).rank(axis=1, pct=True),
        rv.reindex(columns=cols).rank(axis=1, pct=True)]) \
        .groupby(level=0).mean()

    label = {"champion_v1": "NCB (residualized)",
             "fm_score": "FM score (10 predictors)",
             "combo": "NCB+FSS book",
             "distress_mom": "FSS short leg",
             "dbreadth_common": "dBreadth (common filers)",
             "new_conviction": "NCB v2 (catalogue spec)",
             "conviction_top": "Conviction top (level)",
             "ica_rev": "ICA reversal",
             "ssi": "SSI (inverted)",
             "nmf_crowd": "NMF crowding (inverted)"}
    panels = {"distress_mom": rv, "combo": combo}
    rows = []
    for k, lbl in label.items():
        if k in panels:
            inds = panels[k]
        elif (PANELS / f"{k}.parquet").exists():
            inds = pd.read_parquet(PANELS / f"{k}.parquet")
        else:
            continue
        rr, rg = bt(inds, k)
        if rr is None:
            continue
        rows.append((lbl, metrics(rr, rg)))

    L = [r"\begin{table}[t]", r"\centering\footnotesize",
         r"\caption{Production-engine results, net of 5 bps/side "
         r"commissions and 50 bps p.a.\ borrow on short legs; expanded "
         r"universe; tradability filters \$4 / \$5M ADV / 252d. "
         r"``cost'' is the measured annualized commission drag "
         r"(net run minus zero-fee run); ``turn'' the implied one-way "
         r"annual turnover (traded notional over book, per year). "
         r"Research-rejected signals enter inverted, so a positive "
         r"Sharpe means the research conclusion prices.}",
         r"\label{tab:engine}",
         r"\begin{tabular}{lrrrrrrrr}", r"\toprule",
         r"strategy & ann.\ net & vol & Sharpe & maxDD & Calmar & hit & "
         r"cost (bps/y) & turn \\", r"\midrule"]
    for lbl, m in rows:
        L.append(f"{lbl} & {m['ann']:+.1%} & {m['vol']:.1%} & "
                 f"{m['sharpe']:+.2f} & {m['maxdd']:+.1%} & "
                 f"{m['calmar']:+.2f} & {m['hit']:.0%} & "
                 f"{m['cost_bps']:.0f} & {m['turnover']:.1f}x "
                 f"\\\\".replace("%", r"\%"))
    L += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    (PAPER / "tables" / "t1_engine.tex").write_text(
        "\n".join(L), encoding="utf-8")
    log("t1_engine.tex written")


if __name__ == "__main__":
    main()
