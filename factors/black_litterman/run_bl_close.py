"""Fechamento BL: painel m3, overlap com champion/distress, producao, combo 3 pernas."""
import sys, os
from collections import deque, defaultdict
from pathlib import Path
import numpy as np, pandas as pd
from scipy import stats as sps
HERE = Path(__file__).resolve().parent
for sub in ("", "general_plan"): sys.path.insert(0, str(HERE.parent / sub))
import panel as pn
import market_cap as mc
from run_all import load_market, log
cmap, mdta = load_market()
dates = mdta.prices.index
cum = mdta.returns.cumsum()
bench = mdta.benchmark_returns
shares = mc.shares_panel(dates, mdta.tickers, mdta.prices, mdta.prices_raw)
mcap = mc.mktcap_panel(mdta.prices_raw, shares)
qs = [q for q in pn.quarters() if pd.Timestamp("2013-06-30") <= q <= dates[-1] - pd.Timedelta(days=125)]

cache = HERE / "results" / "bl_m3_panel.parquet"
if cache.exists():
    panel = pd.read_parquet(cache)
else:
    cross = {}
    for qi in range(1, len(qs)):
        p = qs[qi]
        dec = p + pd.Timedelta(days=50)
        if dec >= dates[-1] - pd.Timedelta(days=95): break
        cur = pn.snapshot_as_of(p, dec)
        if len(cur) < 1000: continue
        di = dates.searchsorted(dec, side="right") - 1
        px = mdta.prices_raw.iloc[di]; mc_d = mcap.iloc[di]
        w0 = max(0, di - 252)
        rs = mdta.returns.iloc[w0:di]; rb = bench.iloc[w0:di]
        bvar = float(rb.var())
        beta = rs.apply(lambda c: c.cov(rb)) / max(bvar, 1e-10)
        s2e = (rs.var() - beta**2*bvar).clip(lower=1e-6)
        h = cur.copy(); h["tk"] = h["instrument_id"].map(cmap)
        h = h.dropna(subset=["tk"]); h = h[h["tk"].map(px).notna()]
        g = h.groupby("filer_id")["value_usd"]; aum = g.sum(); npos = g.size()
        h = h[h["filer_id"].isin(aum.index[(aum>=1e8)&(npos>=10)])]
        h["w"] = h["value_usd"]/h["filer_id"].map(aum)
        wmkt = mc_d/mc_d.sum()
        h["wa"] = h["w"] - h["tk"].map(wmkt).fillna(0.0)
        h["qidio"] = h["tk"].map(s2e)*h["wa"]
        agg = h.groupby("tk")["qidio"].sum()
        # vol-neutro (a versao conservadora, pre-comprometida p/ producao)
        rk = agg.rank(pct=True); vr = s2e.reindex(agg.index).rank(pct=True)
        ok = rk.notna()&vr.notna()
        X = np.column_stack([np.ones(ok.sum()), vr[ok].values])
        bb,*_ = np.linalg.lstsq(X, rk[ok].values, rcond=None)
        res = rk.copy(); res[ok] = rk[ok].values - X@bb
        cross[dates[min(di+1, len(dates)-1)]] = res.rank(pct=True)
        log(f"bl {p.date()}: {len(res)}")
    panel = pd.DataFrame(cross).T.sort_index()
    panel.to_parquet(cache)

# overlap
PS = HERE.parent/"production_suite"/"data"/"panels"
outs = ["# BL fechamento", ""]
for other in ("champion_v1", "dio_2q"):
    o = pd.read_parquet(PS/f"{other}.parquet"); cc=[]
    for d, row in panel.iterrows():
        i2 = o.index.searchsorted(d)
        if i2 >= len(o.index): continue
        orow = o.iloc[i2].dropna(); r = row.dropna()
        common = r.index.intersection(orow.index)
        if len(common) > 100: cc.append(sps.spearmanr(r[common], orow[common])[0])
    outs.append(f"- corr media com {other}: {np.mean(cc):+.2f}")
rvp = 1.0 - pd.read_parquet(HERE.parent/"reversao_condicional/results/reversal_panel.parquet")
cc=[]
for d, row in panel.iterrows():
    i2 = rvp.index.searchsorted(d)
    if i2 >= len(rvp.index): continue
    orow = rvp.iloc[i2].dropna(); r = row.dropna()
    common = r.index.intersection(orow.index)
    if len(common) > 100: cc.append(sps.spearmanr(r[common], orow[common])[0])
outs.append(f"- corr media com distress_mom: {np.mean(cc):+.2f}")

# producao: bl_m3v e combo 3 pernas
os.chdir(HERE.parent)
from backtest import Backtest
from filters import Filters
from portfolio import Portfolio
flt = Filters(mdta)
os.chdir(HERE)
def bt(inds, name):
    inds = inds[[c for c in inds.columns if c in mdta.prices.columns]].reindex(index=dates).ffill(limit=75)
    changed = (inds != inds.shift(1)).sum(axis=1)
    has = inds.notna().sum(axis=1)
    idx = np.flatnonzero((changed > max(20, int(has[has>0].median()*0.30))).values)
    keep=[idx[0]]
    for i in idx[1:]:
        if i-keep[-1]>20: keep.append(i)
    idx=np.array(keep); first=dates[idx[0]]
    p_ = Portfolio.from_indicator(name, inds, flt.universe, side="HML", pct=0.2, min_stocks=40)
    p_ = p_.normalize(type="split"); p_.rebalance(idx, mdta.prices)
    rr = Backtest([p_]).get_returns(mdta, trading_fee=0.0005).iloc[:,0].dropna()
    rr = rr[rr.index>=first]
    ann,vol = rr.mean()*252, rr.std()*np.sqrt(252)
    eq=rr.cumsum()
    return f"{name}: ann={ann:+.2%} Sharpe={ann/vol:.2f} maxDD={(eq-eq.cummax()).min():+.2%}", rr

s1,_ = bt(panel.copy(), "bl_m3v producao")
outs.append(s1)
ch = pd.read_parquet(PS/"champion_v1.parquet")
rv = rvp.reindex(dates).ffill(limit=75)
chf = ch.reindex(dates); blf = panel.reindex(dates).ffill(limit=75)
cols = sorted(set(chf.columns)|set(rv.columns)|set(blf.columns))
tri = (chf.reindex(columns=cols).rank(axis=1,pct=True)
       .add(rv.reindex(columns=cols).rank(axis=1,pct=True), fill_value=None))
tri = pd.concat([chf.reindex(columns=cols).rank(axis=1,pct=True),
                 rv.reindex(columns=cols).rank(axis=1,pct=True),
                 blf.reindex(columns=cols).rank(axis=1,pct=True)]).groupby(level=0).mean()
s2,_ = bt(tri, "COMBO 3 pernas (champ+distress+bl)")
outs.append(s2)
(HERE/"results"/"BL_CLOSE.md").write_text("\n".join(outs), encoding="utf-8")
print("\n".join(outs))
