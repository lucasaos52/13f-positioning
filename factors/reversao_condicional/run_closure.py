"""Two closures: (1) true CS reversal at long horizons; (2) the inverted
signal (distress momentum) under full production discipline + overlap."""
import sys, os
from pathlib import Path
import numpy as np, pandas as pd
from scipy import stats as sps
HERE = Path(__file__).resolve().parent
for sub in ("", "general_plan"): sys.path.insert(0, str(HERE.parent / sub))
from backtest_gp import forward_return, nw_tstat
from run_all import load_market, log

cmap, mdta = load_market()
dates = mdta.prices.index
cum = mdta.returns.cumsum()
panel = pd.read_parquet(HERE / "results" / "reversal_panel.parquet")
panel = panel[[c for c in panel.columns if c in mdta.prices.columns]]

# ---- (1) horizontes longos: a reversao CS verdadeira ---------------------- #
L = ["# Fechamentos da reversao condicional", "", "## 1. Horizontes longos (pressao alta - baixa)"]
horiz = {}
for k in (1, 2, 3, 4):
    sp = []
    for d, row in panel.iterrows():
        r = row.dropna()
        if len(r) < 100: continue
        hi, lo = r.index[r >= r.quantile(0.8)], r.index[r <= r.quantile(0.2)]
        a = d + pd.Timedelta(days=91 * (k - 1))
        b = min(d + pd.Timedelta(days=91 * k), dates[-1])
        if a >= dates[-1] - pd.Timedelta(days=10): continue
        f = forward_return(cum, dates, a, b)
        fh, fl = f.reindex(hi).dropna(), f.reindex(lo).dropna()
        if min(len(fh), len(fl)) >= 15:
            sp.append(fh.mean() - fl.mean())
    s = pd.Series(sp)
    horiz[k] = s
    L.append(f"- tri +{k}: {s.mean():+.4f}/tri t={nw_tstat(s):+.2f} (n={len(s)})")
L.append("CS preve: negativo perto, POSITIVO em +3/+4 se a reversao tardia existe.")

# ---- (2) invertido com disciplina completa -------------------------------- #
os.chdir(HERE.parent)
from backtest import Backtest
from filters import Filters
from portfolio import Portfolio
flt = Filters(mdta)
os.chdir(HERE)
inv = (1.0 - panel).reindex(dates).ffill(limit=75)
changed = (inv != inv.shift(1)).sum(axis=1)
has = inv.notna().sum(axis=1)
dec_idxs = np.flatnonzero((changed > max(20, int(has[has>0].median()*0.30))).values)
keep = [dec_idxs[0]]
for i in dec_idxs[1:]:
    if i - keep[-1] > 20: keep.append(i)
dec_idxs = np.array(keep)
first = dates[dec_idxs[0]]
p = Portfolio.from_indicator("distress_mom", inv, flt.universe, side="HML", pct=0.2, min_stocks=40)
p = p.normalize(type="split"); p.rebalance(dec_idxs, mdta.prices)
rr = Backtest([p]).get_returns(mdta, trading_fee=0.0005).iloc[:,0].dropna()
rr = rr[rr.index >= first]
ann, vol = rr.mean()*252, rr.std()*np.sqrt(252)
eq = rr.cumsum()
L += ["", "## 2. Invertido (distress momentum) no motor de producao",
      f"- LS net: {ann:+.2%} a.a. | Sharpe {ann/vol:.2f} | maxDD {(eq-eq.cummax()).min():+.2%} | rebals {len(dec_idxs)}"]

# overlap com sinais existentes
PS = HERE.parent / "production_suite" / "data" / "panels"
cors = {}
for other in ("champion_v1", "dio_2q", "copycat_flow"):
    f2 = PS / f"{other}.parquet"
    if not f2.exists(): continue
    o = pd.read_parquet(f2)
    cc = []
    for d, row in panel.iterrows():
        i2 = o.index.searchsorted(d)
        if i2 >= len(o.index): continue
        orow = o.iloc[i2].dropna()
        r = (1.0 - row.dropna())
        common = r.index.intersection(orow.index)
        if len(common) > 100:
            cc.append(sps.spearmanr(r[common], orow[common])[0])
    if cc: cors[other] = float(np.mean(cc))
L += ["", "## 3. Overlap (corr media cross-section do invertido com):"]
for k2, v in cors.items(): L.append(f"- {k2}: {v:+.2f}")
(HERE / "results" / "CLOSURE_REPORT.md").write_text("\n".join(L), encoding="utf-8")
print("\n".join(L))
