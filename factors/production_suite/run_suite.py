"""Production suite: EVERY idea from the research night, re-tested in the
real engine (factors/): Filters $5M universe, equal weight (the ACP lesson),
fee 5bps, daily borrow on shorts, rebalance AT each signal's own decision
dates, LS net of costs.

    python run_suite.py

Panels are cached per signal (data/panels/*.parquet) so re-runs are cheap.
Each builder is fault-isolated: one idea crashing is logged loudly and the
suite continues. Results append incrementally to results/suite_results.csv.

Signals whose research direction was NEGATIVE (dio_2q) enter INVERTED so a
positive Sharpe means "the idea works as concluded in research". Everything
else enters as constructed - a negative production Sharpe is information,
not an error.
"""
from __future__ import annotations

import json
import sys
import traceback
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
for sub in ("", "general_plan", "general_predictive_signals", "ssi",
            "copycat", "original_methods", "ica_demand"):
    sys.path.insert(0, str(HERE.parent / sub))

import panel as pn                                  # noqa: E402
import market_cap as mc                             # noqa: E402
from run_all import load_market, log                # noqa: E402
from run_signals import residualise                 # noqa: E402
from signal_defs import CATALOGUE, build_all        # noqa: E402

PANELS = HERE / "data" / "panels"
RESULTS = HERE / "results"
LAG = 50
INVERT = {"dio_2q"}          # research concluded the contrarian side


# --------------------------------------------------------------------------- #
# shared context
# --------------------------------------------------------------------------- #

class Ctx:
    def __init__(self):
        self.cmap, self.md = load_market()
        self.dates = self.md.prices.index
        self.adv = self.md.dollar_volume.rolling(63, min_periods=20).median()
        self.shares = mc.shares_panel(self.dates, self.md.tickers,
                                      self.md.prices, self.md.prices_raw)
        self.mcap = mc.mktcap_panel(self.md.prices_raw, self.shares)
        self.meta = pd.read_parquet(pn.QDIR / "filings_meta.parquet")
        self.qs = [q for q in pn.quarters()
                   if pd.Timestamp("2013-06-30") <= q
                   <= self.dates[-1] - pd.Timedelta(days=60)]

    def market_at(self, dec):
        di = self.dates.searchsorted(dec, side="right") - 1
        return di, self.md.prices_raw.iloc[di], self.adv.iloc[di], \
            self.mcap.iloc[di]


def to_panel(cross: dict, ctx) -> pd.DataFrame:
    p = pd.DataFrame(cross).T.sort_index()
    return p.reindex(ctx.dates).ffill(limit=75)


def save(name: str, cross: dict, ctx):
    PANELS.mkdir(parents=True, exist_ok=True)
    to_panel(cross, ctx).to_parquet(PANELS / f"{name}.parquet")


# --------------------------------------------------------------------------- #
# builder 1: the 17-signal batch (headline versions)
# --------------------------------------------------------------------------- #

def build_batch(ctx):
    todo = [n for n in CATALOGUE if n != "conf_reveal"
            and not (PANELS / f"{n}.parquet").exists()]
    if not todo:
        return
    nh = ctx.meta[ctx.meta["amendment_type"] == "NEW HOLDINGS"]
    cross = defaultdict(dict)
    for qi in range(2, len(ctx.qs)):
        p, p1, p2 = ctx.qs[qi], ctx.qs[qi - 1], ctx.qs[qi - 2]
        dec = p + pd.Timedelta(days=LAG)
        if dec >= ctx.dates[-1]:
            break
        cur = pn.snapshot_as_of(p, dec)
        prev = pn.snapshot_as_of(p1, dec)
        prev2 = pn.snapshot_as_of(p2, dec)
        if min(len(cur), len(prev)) < 1000:
            continue
        di, px, adv_d, mc_d = ctx.market_at(dec)

        def so_at(period):
            dix = ctx.dates.searchsorted(period, side="right") - 1
            row = ctx.shares.iloc[dix] if len(ctx.shares) else pd.Series(dtype=float)
            t = pd.Series(ctx.cmap)
            return pd.Series(t.map(row).values, index=t.index)

        orig = ctx.meta[(ctx.meta["period_end"] == p) & (~ctx.meta["is_amendment"])]
        early = set(orig.loc[orig["filing_date"] <= p + pd.Timedelta(days=40),
                             "filer_id"])
        pair = cur.merge(prev, on=["filer_id", "instrument_id"],
                         suffixes=("_c", "_p"))
        pair = pair[(pair["shares_p"] > 0) & (pair["shares_c"] > 0)]
        pair["ratio"] = (pair["shares_c"] / pair["shares_p"]).round(3)
        fac = {}
        for j, g in pair.groupby("instrument_id"):
            if len(g) < 10:
                continue
            c = g["ratio"].value_counts()
            mode, k = c.index[0], c.iloc[0]
            k2 = c.iloc[1] if len(c) > 1 else 0
            if abs(mode - 1) > 0.15 and (k >= 0.10 * len(g)
                                         or (k >= 30 and k >= 2.5 * k2)):
                fac[j] = float(mode)
        sig = build_all(cur, prev, prev2, so_at(p), so_at(p1), so_at(p2),
                        early, pd.Index([]), split_fac=pd.Series(fac, dtype=float))
        t = sig.index.to_series().map(ctx.cmap)
        adv_i = t.map(adv_d)
        sig["days_adv"] = sig.pop("inst_value") / adv_i
        sig["d_days_adv"] = sig["days_adv"] - sig.pop("inst_value_prev") / adv_i
        sig["ticker"] = t
        sig = sig.dropna(subset=["ticker"])
        agg = {n: ("mean" if n in ("ti", "vi", "breadth_level",
                                   "herf_holders") else "sum")
               for n in todo}
        agg["log_n_holders"] = "max"
        byt = sig.groupby("ticker").agg(agg)
        byt = byt.loc[px.reindex(byt.index) >= 1.0]
        ctrl = pd.DataFrame({"log_mktcap": np.log(mc_d.reindex(byt.index)),
                             "log_adv": np.log(adv_d.reindex(byt.index))})
        stamp = ctx.dates[min(di + 1, len(ctx.dates) - 1)]
        for name in todo:
            m = CATALOGUE[name]
            s = byt[name].replace([np.inf, -np.inf], np.nan)
            s = s.clip(s.quantile(0.01), s.quantile(0.99))
            r = np.log1p(s.clip(lower=0)).rank(pct=True) \
                if name in ("days_adv", "pso") else s.rank(pct=True)
            if m.theorem:
                X = ctrl.copy()
                for ec in m.extra_controls:
                    X[ec] = byt[ec]
                r = residualise(r, X).rank(pct=True)
            if name in INVERT:
                r = 1.0 - r
            cross[name][stamp] = r.dropna()
        log(f"batch {p.date()}")
    for name in todo:
        save(name, cross[name], ctx)


# --------------------------------------------------------------------------- #
# builder 2/3: champion panels (already cached by earlier runs - just copy)
# --------------------------------------------------------------------------- #

def build_champion(ctx):
    for src, dst in [(HERE.parent / "champion/results/champion_signal_panel.parquet",
                      "champion_v1"),
                     (HERE.parent / "champion/results/v0_signal_panel.parquet",
                      "nc_v0")]:
        if src.exists() and not (PANELS / f"{dst}.parquet").exists():
            pd.read_parquet(src).to_parquet(PANELS / f"{dst}.parquet")


# --------------------------------------------------------------------------- #
# builder 4: copycat flow (resid rank)
# --------------------------------------------------------------------------- #

def build_copycat(ctx):
    if (PANELS / "copycat_flow.parquet").exists():
        return
    excess = defaultdict(list)
    lead_new, lead_prev = None, []
    cross = {}
    for qi in range(1, len(ctx.qs)):
        p, p1 = ctx.qs[qi], ctx.qs[qi - 1]
        dec = p + pd.Timedelta(days=LAG)
        if dec >= ctx.dates[-1]:
            break
        cur = pn.snapshot_as_of(p, dec)
        prev = pn.snapshot_as_of(p1, dec)
        if min(len(cur), len(prev)) < 1000:
            continue
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
                raw = {A: len(nb & la) / len(nb)
                       for A, la in lead_new.items() if la}
                if raw:
                    base = np.mean(list(raw.values()))
                    for A, v in raw.items():
                        if v - base > 0:
                            excess[(B, A)].append((qi, v - base))
        saum = defaultdict(float)
        for (B, A), h in excess.items():
            rec = [v for (qq, v) in h if qi - 4 <= qq <= qi]
            if rec and B in elig.index:
                saum[A] += float(elig.loc[B, "aum"]) * float(np.mean(rec))
        saum = pd.Series(saum, dtype=float)
        if len(saum) >= 30:
            hi = saum.quantile(2 / 3)
            flow = defaultdict(float)
            for A in leaders:
                if float(saum.get(A, 0.0)) >= hi:
                    for j in new.get(A, frozenset()):
                        flow[j] += float(saum[A])
            fs = pd.Series(flow, dtype=float)
            di, px, adv_d, mc_d = ctx.market_at(dec)
            ft = fs.groupby(fs.index.to_series().map(ctx.cmap)).sum()
            sig = (ft / adv_d.reindex(ft.index)).replace(
                [np.inf, -np.inf], np.nan).dropna()
            sig = sig[px.reindex(sig.index) >= 1.0]
            if len(sig) >= 80:
                ctrl = pd.DataFrame({
                    "log_mktcap": np.log(mc_d.reindex(sig.index)),
                    "log_adv": np.log(adv_d.reindex(sig.index))})
                r = residualise(np.log1p(sig).rank(pct=True), ctrl).rank(pct=True)
                # research verdict: hangover -> INVERTED (short high flow)
                cross[ctx.dates[min(di + 1, len(ctx.dates) - 1)]] = (1.0 - r).dropna()
        lead_new = {A: new.get(A, frozenset()) for A in leaders}
        lead_prev = leaders
        log(f"copycat {p.date()}")
    save("copycat_flow", cross, ctx)


# --------------------------------------------------------------------------- #
# builder 5: SSI (resid headline)
# --------------------------------------------------------------------------- #

def build_ssi(ctx):
    if (PANELS / "ssi.parquet").exists():
        return
    from run_ssi import ssi_cross_section
    cross = {}
    for qi in range(1, len(ctx.qs)):
        p = ctx.qs[qi]
        dec = p + pd.Timedelta(days=45)
        if dec >= ctx.dates[-1]:
            break
        cur = pn.snapshot_as_of(p, dec)
        if len(cur) < 1000:
            continue
        di, px, adv_d, mc_d = ctx.market_at(dec)
        w_mkt = (mc_d / mc_d.sum()).dropna()
        X = ssi_cross_section(cur, ctx.cmap, w_mkt)
        if len(X) < 300:
            continue
        X = X.loc[X.index.isin(X.index[px.reindex(X.index) >= 1.0])]
        ctrl = pd.DataFrame({"log_mktcap": np.log(mc_d.reindex(X.index)),
                             "log_adv": np.log(adv_d.reindex(X.index))})
        r = residualise(np.log1p(X["ssi"].clip(lower=0)).rank(pct=True),
                        ctrl).rank(pct=True)
        # research direction: high SSI = Miller overpricing -> INVERT
        cross[ctx.dates[min(di + 1, len(ctx.dates) - 1)]] = (1.0 - r).dropna()
        log(f"ssi {p.date()}")
    save("ssi", cross, ctx)


# --------------------------------------------------------------------------- #
# builder 6: NMF strategy crowding (resid headline, as constructed)
# --------------------------------------------------------------------------- #

def build_nmf(ctx):
    if (PANELS / "nmf_crowd.parquet").exists():
        return
    from nmf_crowding import build_W, fit_nmf
    cross = {}
    for qi in range(len(ctx.qs)):
        p = ctx.qs[qi]
        dec = p + pd.Timedelta(days=45)
        if dec >= ctx.dates[-1]:
            break
        snap = pn.snapshot_as_of(p, dec)
        if len(snap) < 1000:
            continue
        di, px, adv_d, mc_d = ctx.market_at(dec)
        W, aum = build_W(snap, ctx.cmap, px)
        if len(W) < 100:
            continue
        A, S = fit_nmf(W, 12)
        cap = (A * aum.values[:, None]).sum(axis=0)
        S_n = S / S.sum(axis=1, keepdims=True)
        badv = S_n @ adv_d.reindex(W.columns).fillna(0.0).values
        crowd = cap / np.maximum(badv, 1.0)
        expo = S / np.maximum(S.sum(axis=0, keepdims=True), 1e-12)
        sig = pd.Series(expo.T @ crowd, index=W.columns)
        ctrl = pd.DataFrame({"log_mktcap": np.log(mc_d.reindex(sig.index)),
                             "log_adv": np.log(adv_d.reindex(sig.index))})
        r = residualise(np.log1p(sig.clip(lower=0)).rank(pct=True),
                        ctrl).rank(pct=True)
        # research: crowded-strategy names UNDERPERFORM in calm -> invert
        cross[ctx.dates[min(di + 1, len(ctx.dates) - 1)]] = (1.0 - r).dropna()
        log(f"nmf {p.date()}")
    save("nmf_crowd", cross, ctx)


# --------------------------------------------------------------------------- #
# builder 7: ICA rev / comb (from the cached flow panel, expanding fits)
# --------------------------------------------------------------------------- #

def build_ica(ctx):
    if (PANELS / "ica_rev.parquet").exists():
        return
    from run_ica import classify, decompose
    fp = HERE.parent / "ica_demand" / "results" / "flow_panel.parquet"
    X = pd.read_parquet(fp)
    cols = list(X.columns)
    cross_rev, cross_comb = {}, {}
    for ti in range(20, len(cols)):
        t = cols[ti]
        dec = t + pd.Timedelta(days=45)
        if dec >= ctx.dates[-1]:
            break
        di, px, adv_d, mc_d = ctx.market_at(dec)
        win = X[cols[:ti + 1]]
        cover = win.notna().mean(axis=1)
        alive = win.index[(cover >= 0.8) & (px.reindex(win.index) >= 1.0)
                          & win[t].notna()]
        win = win.loc[alive]
        if len(win) < 300:
            continue
        S, B = decompose(win, "ica")
        forced, informed = classify(S)
        s_now = S[:, -1]
        rev = -pd.Series(B[:, forced] @ s_now[forced], index=win.index)
        cont = pd.Series(B[:, informed] @ s_now[informed], index=win.index)
        stamp = ctx.dates[min(di + 1, len(ctx.dates) - 1)]
        cross_rev[stamp] = rev.rank(pct=True)
        cross_comb[stamp] = ((rev.rank(pct=True) + cont.rank(pct=True)) / 2)
        log(f"ica {t.date()}")
    save("ica_rev", cross_rev, ctx)
    save("ica_comb", cross_comb, ctx)


# --------------------------------------------------------------------------- #
# the common production backtest
# --------------------------------------------------------------------------- #

def backtest_panel(name: str, ctx, flt, Portfolio, Backtest) -> dict | None:
    f = PANELS / f"{name}.parquet"
    if not f.exists():
        return None
    inds = pd.read_parquet(f)
    inds = inds[[c for c in inds.columns if c in ctx.md.prices.columns]] \
        .reindex(index=ctx.dates)
    # decision dates = days where the CONTENT changed for many names (a new
    # cross-section was stamped). Count-based detection misses quarters whose
    # breadth is stable - content-based does not.
    changed = (inds != inds.shift(1)).sum(axis=1)
    has = inds.notna().sum(axis=1)
    thresh = max(20, int(has[has > 0].median() * 0.30))
    dec_idxs = np.flatnonzero((changed > thresh).values)
    # collapse runs of consecutive trigger days (ffill expiry noise)
    if len(dec_idxs):
        keep = [dec_idxs[0]]
        for i in dec_idxs[1:]:
            if i - keep[-1] > 20:
                keep.append(i)
        dec_idxs = np.array(keep)
    if len(dec_idxs) < 10:
        return None
    first = ctx.dates[dec_idxs[0]]
    p = Portfolio.from_indicator(name, inds, flt.universe, side="HML",
                                 pct=0.2, min_stocks=40)
    p = p.normalize(type="split")
    p.rebalance(dec_idxs, ctx.md.prices)
    rr = Backtest([p]).get_returns(ctx.md, trading_fee=0.0005).iloc[:, 0].dropna()
    rr = rr[rr.index >= first]
    if not len(rr):
        return None
    # daily net return series dumped for the paper's PnL charts/tables
    (HERE / "data" / "pnl").mkdir(parents=True, exist_ok=True)
    rr.rename("net_ret").to_csv(HERE / "data" / "pnl" / f"{name}.csv")
    ann, vol = rr.mean() * 252, rr.std() * np.sqrt(252)
    eq = rr.cumsum()
    return {"signal": name, "ann_net": ann, "vol": vol,
            "sharpe": ann / vol if vol > 0 else np.nan,
            "max_dd": float((eq - eq.cummax()).min()),
            "hit": float((rr > 0).mean()),
            "n_rebals": len(dec_idxs),
            "start": str(first.date())}


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    ctx = Ctx()
    import os
    os.chdir(HERE.parent)
    from backtest import Backtest
    from filters import Filters
    from portfolio import Portfolio
    flt = Filters(ctx.md)
    os.chdir(HERE)

    for builder in (build_champion, build_batch, build_copycat, build_ssi,
                    build_nmf, build_ica):
        try:
            builder(ctx)
        except Exception:
            log(f"BUILDER FAILED: {builder.__name__}\n{traceback.format_exc()}")

    rows = []
    for f in sorted(PANELS.glob("*.parquet")):
        try:
            r = backtest_panel(f.stem, ctx, flt, Portfolio, Backtest)
            if r:
                rows.append(r)
                pd.DataFrame(rows).to_csv(RESULTS / "suite_results.csv",
                                          index=False)
                log(f"bt {f.stem}: sharpe {r['sharpe']:.2f}")
        except Exception:
            log(f"BT FAILED: {f.stem}\n{traceback.format_exc()}")

    res = pd.DataFrame(rows).sort_values("sharpe", ascending=False)
    L = ["# Suite de producao - todas as ideias no motor real", "",
         "Convencoes unicas: universo Filters ($4/$5M/252d), equal weight,",
         "LS (HML pct=0,2, min 40 nomes/perna), fee 5bps, borrow 50bps a.a.,",
         "rebal NAS datas de decisao de cada sinal, net. Sinais com veredito",
         "de pesquisa NEGATIVO entram invertidos (dio_2q, copycat_flow, ssi,",
         "nmf_crowd) - Sharpe positivo = 'a conclusao da pesquisa paga'.", "",
         res.round(3).to_markdown(index=False)]
    (RESULTS / "SUITE_REPORT.md").write_text("\n".join(L), encoding="utf-8")
    log("done -> results/")


if __name__ == "__main__":
    main()
