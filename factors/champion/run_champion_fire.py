"""Champion V4: V1 (nc+copycat filter) + distressed-holder supply filter.

Paired test: does excluding long-leg names with heavy DISTRESSED ownership
(the M5 implied-flow machine, validated at t=+13.8 against realized sales)
improve the champion? Distressed books shed 34%/quarter - names they hold
heavily face predictable supply during our holding window. Pro-rata
allocation (pecking was rejected for equities). Direction pre-registered:
filter should RAISE the long leg.
"""
import sys
from collections import defaultdict
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
for sub in ("", "general_plan", "general_predictive_signals", "ssi", "fire_calendar"):
    sys.path.insert(0, str(HERE.parent / sub))
import panel as pn
import market_cap as mc
from backtest_gp import forward_return, nw_tstat
from run_all import load_market, log
from run_signals import residualise
from run_ssi import new_conviction_signal
from run_fire import implied_flows

RESULTS = HERE / "results"
LAG = 50

cmap, mdta = load_market()
dates = mdta.prices.index
cum = mdta.returns.cumsum()
adv = mdta.dollar_volume.rolling(63, min_periods=20).median()
shares = mc.shares_panel(dates, mdta.tickers, mdta.prices, mdta.prices_raw)
mcap = mc.mktcap_panel(mdta.prices_raw, shares)
qs = [q for q in pn.quarters() if pd.Timestamp("2013-06-30") <= q <= dates[-1] - pd.Timedelta(days=125)]

excess_hist = defaultdict(list)
lead_new, lead_prev = None, []
rows = []
for qi in range(1, len(qs)):
    p, p1 = qs[qi], qs[qi - 1]
    dec = p + pd.Timedelta(days=LAG)
    if dec >= dates[-1] - pd.Timedelta(days=95):
        break
    cur = pn.snapshot_as_of(p, dec)
    prev = pn.snapshot_as_of(p1, dec)
    if min(len(cur), len(prev)) < 1000:
        continue
    di = dates.searchsorted(dec, side="right") - 1
    px, adv_d, mc_d = mdta.prices_raw.iloc[di], adv.iloc[di], mcap.iloc[di]

    # copycat filter (as in V1)
    g = cur.groupby("filer_id")["value_usd"]
    stats = pd.DataFrame({"aum": g.sum(), "n": g.size()})
    elig = stats[(stats["n"].between(15, 500)) & (stats["aum"] >= 250e6)]
    leaders = elig.nlargest(300, "aum").index.tolist()
    cs = cur.groupby("filer_id")["instrument_id"].agg(frozenset)
    ps = prev.groupby("filer_id")["instrument_id"].agg(frozenset)
    new = {f: cs[f] - ps.get(f, frozenset()) for f in cs.index}
    if lead_new:
        for B in (f for f in elig.index if f not in lead_prev):
            nb = new.get(B, frozenset())
            if len(nb) < 3:
                continue
            raw = {A: len(nb & la) / len(nb) for A, la in lead_new.items() if la}
            if raw:
                base = np.mean(list(raw.values()))
                for A, v in raw.items():
                    if v - base > 0:
                        excess_hist[(B, A)].append((qi, v - base))
    saum = defaultdict(float)
    for (B, A), h in excess_hist.items():
        rec = [v for (qq, v) in h if qi - 4 <= qq <= qi]
        if rec and B in elig.index:
            saum[A] += float(elig.loc[B, "aum"]) * float(np.mean(rec))
    saum = pd.Series(saum, dtype=float)
    cc_hi = set()
    if len(saum) >= 30:
        hi = saum.quantile(2 / 3)
        flow = defaultdict(float)
        for A in leaders:
            if float(saum.get(A, 0.0)) >= hi:
                for j in new.get(A, frozenset()):
                    flow[j] += float(saum[A])
        fs = pd.Series(flow, dtype=float)
        ft = fs.groupby(fs.index.to_series().map(cmap)).sum()
        if len(ft) > 10:
            cc_hi = set(ft.nlargest(max(int(len(ft) / 3), 1)).index)

    # fire filter: distressed-holder supply per ticker (pro-rata)
    i_p1 = dates.searchsorted(p1, side="right") - 1
    i_p = dates.searchsorted(p, side="right") - 1
    ret_q = cum.iloc[i_p] - cum.iloc[i_p1]
    fl = implied_flows(cur, prev, cmap, ret_q)
    dis = fl.index[fl["flow"] < -0.10]
    fire_hi = set()
    if len(dis) >= 15:
        s = cur[cur["filer_id"].isin(dis)].copy()
        s["ticker"] = s["instrument_id"].map(cmap)
        s = s.dropna(subset=["ticker"])
        fmag = fl["flow"].abs().reindex(s["filer_id"]).values
        s["sup"] = fmag * s["value_usd"]
        sup = s.groupby("ticker")["sup"].sum()
        sup = (sup / adv_d.reindex(sup.index)).dropna()
        if len(sup) > 30:
            fire_hi = set(sup.nlargest(max(int(len(sup) / 3), 1)).index)

    nc = new_conviction_signal(cur, prev, cmap)
    nc = nc[px.reindex(nc.index) >= 1.0]
    ctrl = pd.DataFrame({"log_mktcap": np.log(mc_d.reindex(nc.index)),
                         "log_adv": np.log(adv_d.reindex(nc.index))})
    r = residualise(nc.rank(pct=True), ctrl).rank(pct=True).dropna()
    if len(r) < 300:
        lead_new = {A: new.get(A, frozenset()) for A in leaders}
        lead_prev = leaders
        continue
    nxt = qs[qi + 1] + pd.Timedelta(days=LAG) if qi + 1 < len(qs) else dates[-1]
    fwd = forward_return(cum, dates, dec, min(nxt, dates[-1])).reindex(r.index)
    long_all = r.index[r >= r.quantile(0.8)]
    short_names = r.index[r <= r.quantile(0.2)]
    v1 = [n for n in long_all if n not in cc_hi]
    v4 = [n for n in v1 if n not in fire_hi]

    def leg(names):
        f = fwd.reindex(list(names)).dropna()
        return float(f.mean()) if len(f) >= 20 else np.nan
    rows.append({"period": p, "short": leg(short_names),
                 "v1_long": leg(v1), "v4_long": leg(v4),
                 "n_v1": len(v1), "n_fire_removed": len(v1) - len(v4)})
    lead_new = {A: new.get(A, frozenset()) for A in leaders}
    lead_prev = leaders
    log(f"{p.date()}: fire removed {rows[-1]['n_fire_removed']} of {len(v1)}")

e = pd.DataFrame(rows).dropna()
d = e["v4_long"] - e["v1_long"]
s1 = e["v1_long"] - e["short"]
s4 = e["v4_long"] - e["short"]
L = ["# Champion V4 = V1 + filtro de holders distressed (fluxo implicito)", "",
     f"- V1 spread: {s1.mean():+.4f}/tri t={nw_tstat(s1):+.2f} Sharpe {s1.mean()/s1.std()*2:.2f}",
     f"- V4 spread: {s4.mean():+.4f}/tri t={nw_tstat(s4):+.2f} Sharpe {s4.mean()/s4.std()*2:.2f}",
     f"- DELTA pareado V4-V1: {d.mean():+.4f}/tri t(NW)={nw_tstat(d):+.2f}",
     f"- removidos pelo fire/tri: {e.n_fire_removed.mean():.0f} de {e.n_v1.mean():.0f}",
     f"- eventos: {len(e)}"]
(RESULTS / "CHAMPION_FIRE_REPORT.md").write_text("\n".join(L), encoding="utf-8")
print("\n".join(L))
