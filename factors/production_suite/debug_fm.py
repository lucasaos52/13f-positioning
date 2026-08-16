"""Decompose the FM research->engine Sharpe gap (0.86 -> 0.24).

Three cuts isolate the cause:
  A. engine with trading_fee = 0            -> is it costs?
  B. quintile EW spread of the SAME panel   -> is it the tradable
     restricted to the engine's universe       universe (vs the wide
     at each decision date (no engine)         research universe)?
  C. engine long leg only vs short leg only -> is one leg (shorting
                                               mega-caps) the killer?
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

from backtest_gp import nw_tstat                    # noqa: E402
from run_all import load_market, log                # noqa: E402

cmap, mdta = load_market()
dates = mdta.prices.index
cum = mdta.returns.cumsum()
os.chdir(HERE.parent)
from backtest import Backtest                       # noqa: E402
from filters import Filters                         # noqa: E402
from portfolio import Portfolio                     # noqa: E402
flt = Filters(mdta)
os.chdir(HERE)

panel = pd.read_parquet(HERE / "data/panels/fm_score.parquet")
inds = panel[[c for c in panel.columns if c in mdta.prices.columns]] \
    .reindex(index=dates)
changed = (inds != inds.shift(1)).sum(axis=1)
has = inds.notna().sum(axis=1)
idx = np.flatnonzero(
    (changed > max(20, int(has[has > 0].median() * 0.30))).values)
keep = [idx[0]]
for i in idx[1:]:
    if i - keep[-1] > 20:
        keep.append(i)
idx = np.array(keep)
log(f"{len(idx)} rebal dates")


def engine(fee, side="HML"):
    p = Portfolio.from_indicator(f"fm_{side}_{fee}", inds, flt.universe,
                                 side=side, pct=0.2, min_stocks=40)
    p = p.normalize(type="split")
    p.rebalance(idx, mdta.prices)
    rr = Backtest([p]).get_returns(mdta, trading_fee=fee).iloc[:, 0] \
        .dropna()
    rr = rr[rr.index >= dates[idx[0]]]
    ann, vol = rr.mean() * 252, rr.std() * np.sqrt(252)
    eq = rr.cumsum()
    print(f"  {side} fee={fee}: ann={ann:+.2%} Sharpe={ann / vol:+.2f} "
          f"maxDD={(eq - eq.cummax()).min():+.2%}")
    return rr


print("A. costs on/off (HML):")
engine(0.0005)
engine(0.0)

print("C. legs (fee=0):")
for side in ("H", "L"):
    try:
        engine(0.0, side)
    except Exception as e:
        print(f"  side={side} unsupported: {e}")

print("B. quintile spread of the same panel, engine universe, no engine:")
uni_panel = flt.universe
rows = []
for k, i0 in enumerate(idx):
    d0 = dates[i0]
    i1 = idx[k + 1] if k + 1 < len(idx) else len(dates) - 1
    s = inds.iloc[i0].dropna()
    u = uni_panel.iloc[i0]
    s = s[s.index.isin(u.index[u > 0])]
    if len(s) < 200:
        continue
    fwd = (cum.iloc[i1] - cum.iloc[i0]).reindex(s.index)
    df = pd.concat([s.rename("s"), fwd.rename("f")], axis=1).dropna()
    q5 = pd.qcut(df["s"].rank(method="first"), 5, labels=False)
    g = df.groupby(q5)["f"].mean()
    rows.append({"d": d0, "spread": g.get(4, np.nan) - g.get(0, np.nan),
                 "n": len(df)})
E = pd.DataFrame(rows)
sp = E["spread"]
print(f"  engine-universe quintile spread: {sp.mean():+.4f}/q "
      f"t={nw_tstat(sp):+.2f} Sharpe={sp.mean() / sp.std() * 2:+.2f} "
      f"({len(E)} q, ~{E['n'].mean():.0f} names)")
