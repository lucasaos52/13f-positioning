"""Combo final: champion_v1 + distress_mom (corr ~0) no motor de producao."""
import sys, os
from pathlib import Path
import numpy as np, pandas as pd
HERE = Path(__file__).resolve().parent
for sub in ("", "general_plan"): sys.path.insert(0, str(HERE.parent / sub))
from run_all import load_market, log
cmap, mdta = load_market()
dates = mdta.prices.index
os.chdir(HERE.parent)
from backtest import Backtest
from filters import Filters
from portfolio import Portfolio
flt = Filters(mdta)
os.chdir(HERE)

ch = pd.read_parquet(HERE/"data/panels/champion_v1.parquet")
rv = 1.0 - pd.read_parquet(HERE.parent/"reversao_condicional/results/reversal_panel.parquet")
rv = rv.reindex(dates).ffill(limit=75)
ch = ch.reindex(dates)
cols = sorted(set(ch.columns) | set(rv.columns))
ch = ch.reindex(columns=cols); rv = rv.reindex(columns=cols)
combo = pd.concat([ch.rank(axis=1, pct=True), rv.rank(axis=1, pct=True)]).groupby(level=0).mean()
combo = combo[[c for c in combo.columns if c in mdta.prices.columns]]

def bt(inds, name):
    changed = (inds != inds.shift(1)).sum(axis=1)
    has = inds.notna().sum(axis=1)
    idx = np.flatnonzero((changed > max(20, int(has[has>0].median()*0.30))).values)
    keep=[idx[0]]
    for i in idx[1:]:
        if i-keep[-1]>20: keep.append(i)
    idx=np.array(keep); first=dates[idx[0]]
    p = Portfolio.from_indicator(name, inds, flt.universe, side="HML", pct=0.2, min_stocks=40)
    p = p.normalize(type="split"); p.rebalance(idx, mdta.prices)
    rr = Backtest([p]).get_returns(mdta, trading_fee=0.0005).iloc[:,0].dropna()
    rr = rr[rr.index>=first]
    ann,vol = rr.mean()*252, rr.std()*np.sqrt(252)
    eq=rr.cumsum()
    print(f"{name}: ann={ann:+.2%} Sharpe={ann/vol:.2f} maxDD={(eq-eq.cummax()).min():+.2%}")
    return rr

r = bt(combo, "COMBO champion+distress_mom")
