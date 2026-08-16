"""Cascade v2 - three causal sharpenings over run_cascade.py, each with
its own economic justification (see report of v1 for why v1 stalled).

    python run_cascade_v2.py            # full sample
    python run_cascade_v2.py --smoke

FIX 1 - SALIENCE. Redemptions respond to salient losses (Di Maggio et
al.): the client reads "fund X's biggest position fell 40%", not the full
book. v1 let three crashed 0.5% positions count like one destroyed
flagship. v2: ShockExposure only over positions with book weight >= 5%.
    SE2_m = sum_{i: w_mi >= 5%} w_mi |xret_i| 1(xret_i < -25%)

FIX 2 - MARGINALITY. Flows respond to aggregate performance anyway; the
causal question is whether the flagship crash adds redemptions BEYOND
what average performance predicts. v1 had no control. v2 runs, per
quarter, cross-sectionally:
    flow_{m,t+1} = a + b*SE2_{m,t} + c*rbook_{m,t} + e
and the pre-registered claim is b < 0 GIVEN c (NW t on the b series).
Plus the interaction check: the b should be stronger among managers whose
overall quarter was also bad (no offsetting wins to show the client).

FIX 3 - PECKING in the price leg. When the redemption comes, managers
sell the LIQUID names first (validated in fire_calendar stage 1). The
innocents at risk are the liquid innocents. v2 weights the projected
selling by the within-book liquidity rank.

PRE-REGISTERED:
  A2  b(SE2 | rbook) < 0;
  A2b b more negative in the rbook<0 subsample than rbook>0;
  B2  innocents' spread Q4-Q0 POSITIVE (most-pressured names underperform)
      on raw and size/ADV-residualized versions; placebo (SE2 permuted) ~0.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
for sub in ("", "general_plan", "fire_calendar"):
    sys.path.insert(0, str(HERE.parent / sub))

import market_cap as mc                             # noqa: E402
import panel as pn                                  # noqa: E402
from backtest_gp import forward_return, nw_tstat    # noqa: E402
from run_all import load_market, log                # noqa: E402
from run_fire import implied_flows                  # noqa: E402

RESULTS = HERE / "results"
LAG = 45
SHOCK_CUT = 0.25
FLAG_W = 0.05          # flagship = >= 5% of the book
MIN_SLOPE_Q = 8


def residualise(y, X):
    df = pd.concat([y.rename("y"), X], axis=1).replace(
        [np.inf, -np.inf], np.nan)
    ok = df.notna().all(axis=1)
    if ok.sum() < 30:
        return y - y.mean()
    A = np.column_stack([np.ones(ok.sum()), df.loc[ok, X.columns].values])
    try:
        b, *_ = np.linalg.lstsq(A, df.loc[ok, "y"].values, rcond=None)
    except np.linalg.LinAlgError:
        return y - y.mean()
    r = y.copy()
    r[ok] = df.loc[ok, "y"].values - A @ b
    r[~ok] = np.nan
    return r


def xreg(y, X):
    """slope vector of y on X (with intercept), via lstsq."""
    A = np.column_stack([np.ones(len(X))] + [X[c].values for c in X])
    b, *_ = np.linalg.lstsq(A, y.values, rcond=None)
    return b[1:]


def main(smoke: bool = False) -> None:
    RESULTS.mkdir(exist_ok=True)
    cmap, mdta = load_market()
    dates = mdta.prices.index
    cum = mdta.returns.cumsum()
    adv = mdta.dollar_volume.rolling(63, min_periods=20).median()
    shares = mc.shares_panel(dates, mdta.tickers, mdta.prices, mdta.prices_raw)
    mcap = mc.mktcap_panel(mdta.prices_raw, shares)

    qs = [q for q in pn.quarters()
          if pd.Timestamp("2013-06-30") <= q <= dates[-1] - pd.Timedelta(days=120)]
    if smoke:
        qs = qs[-(10 + MIN_SLOPE_Q):]
    log(f"{len(qs)} quarters")

    se_hist: dict = {}          # period -> DataFrame(se2, rbook) per manager
    mech_rows, price_rows = [], []
    b_series = []               # per-quarter b(SE2 | rbook)

    for qi in range(1, len(qs)):
        p, p1 = qs[qi], qs[qi - 1]
        dec = p + pd.Timedelta(days=LAG)
        if dec >= dates[-1] - pd.Timedelta(days=95):
            continue
        cur = pn.snapshot_as_of(p, dec)
        prev = pn.snapshot_as_of(p1, dec)
        if min(len(cur), len(prev)) < 1000:
            continue
        di = dates.searchsorted(dec, side="right") - 1
        di_p = dates.searchsorted(p, side="right") - 1
        di_p1 = dates.searchsorted(p1, side="right") - 1
        px, adv_d = mdta.prices_raw.iloc[di], adv.iloc[di_p]
        mc_d = mcap.iloc[di]
        ret_q = cum.iloc[di_p] - cum.iloc[di_p1]
        xret = ret_q - ret_q.median()

        fl = implied_flows(cur, prev, cmap, ret_q)

        # ---- stage A2: flow_p ~ SE2_{p-1} + rbook_{p-1} ------------------- #
        if p1 in se_hist and len(fl) > 200:
            st = se_hist[p1]
            common = st.index.intersection(fl.index)
            if len(common) > 200:
                Xr = st.loc[common, ["se2", "rbook"]]
                yr = fl["flow"].reindex(common)
                ok = Xr.notna().all(axis=1) & yr.notna()
                if ok.sum() > 200 and Xr.loc[ok, "se2"].std() > 0:
                    bb = xreg(yr[ok], Xr[ok])
                    b_series.append({"period": p, "b_se2": bb[0],
                                     "c_rbook": bb[1]})
                    mech_rows.append(pd.DataFrame({
                        "period": p, "se2": Xr.loc[ok, "se2"],
                        "rbook": Xr.loc[ok, "rbook"], "flow": yr[ok]}))

        # ---- SE2 (flagship crashes) at p --------------------------------- #
        d = cur[["filer_id", "instrument_id", "value_usd"]].copy()
        d["ticker"] = d["instrument_id"].map(cmap)
        d = d.dropna(subset=["ticker"])
        d["xr"] = d["ticker"].map(xret)
        book = d.groupby("filer_id")["value_usd"].transform("sum")
        d["w"] = d["value_usd"] / book.replace(0, np.nan)
        d["flag"] = (d["w"] >= FLAG_W) & (d["xr"] < -SHOCK_CUT)
        d["se_c"] = d["w"] * d["xr"].abs() * d["flag"].astype(float)
        se2 = d.groupby("filer_id")["se_c"].sum()
        npos = d.groupby("filer_id").size()
        se2 = se2[npos >= 15]
        st = pd.DataFrame({"se2": se2})
        st["rbook"] = fl["rbook"].reindex(st.index)
        se_hist[p] = st

        # ---- stage B2: pecking-weighted pressure on innocents ------------- #
        if len(b_series) >= MIN_SLOPE_Q:
            bs = pd.DataFrame(b_series)
            b_hat = float(bs["b_se2"].mean())
        else:
            b_hat = None
        if b_hat is not None and b_hat < 0:
            shocked = set(xret.index[(xret < -SHOCK_CUT)])
            aum = d.groupby("filer_id")["value_usd"].sum()
            exp_out = (b_hat * se2).clip(upper=0.0)
            hit = exp_out[exp_out < 0]
            if len(hit) >= 30:
                rng = np.random.default_rng(int(p.value) % (2**32))
                se_perm = pd.Series(rng.permutation(se2.values),
                                    index=se2.index)
                exp_pl = (b_hat * se_perm).clip(upper=0.0)

                def pressure(e):
                    dd = d[d["filer_id"].isin(e[e < 0].index)].copy()
                    if not len(dd):
                        return pd.Series(dtype=float)
                    dd["advj"] = dd["ticker"].map(adv_d)
                    dd = dd.dropna(subset=["advj"])
                    dd["peck"] = dd.groupby("filer_id")["advj"] \
                        .rank(pct=True)          # liquid sold first
                    dd["x"] = dd["filer_id"].map(e) \
                        * dd["filer_id"].map(aum) * dd["w"] * dd["peck"]
                    s = dd.groupby("ticker")["x"].sum()
                    s = s[~s.index.isin(shocked)]
                    out = s / pd.Series(s.index.map(adv_d), index=s.index)
                    return out.replace([np.inf, -np.inf], np.nan)

                cp = pressure(exp_out)
                cp_pl = pressure(exp_pl)
                idx = cp.index
                uni = idx[(pd.Series(idx.map(px), index=idx) >= 1.0)]
                nxt = qs[qi + 1] + pd.Timedelta(days=LAG) \
                    if qi + 1 < len(qs) else dates[-1]
                fwd = forward_return(cum, dates, dec,
                                     min(nxt, dates[-1])).reindex(uni)
                ctrl = pd.DataFrame({
                    "lm": np.log(pd.Series(uni.map(mc_d), index=uni)),
                    "la": np.log(pd.Series(uni.map(adv_d), index=uni))})
                row = {"period": p, "b_hat": b_hat,
                       "n_hit_mgrs": int(len(hit))}
                for nm, s in [("raw", cp), ("resid", cp),
                              ("placebo", cp_pl)]:
                    ss = s.reindex(uni)
                    r = ss.rank(pct=True)
                    if nm == "resid":
                        r = residualise(r, ctrl).rank(pct=True)
                    df = pd.concat([r.rename("s"), fwd.rename("f")],
                                   axis=1).dropna()
                    if len(df) < 200:
                        row[f"spread_{nm}"] = np.nan
                        continue
                    jit = pd.Series(rng.uniform(0, 1e-9, len(df)),
                                    index=df.index)
                    q5 = pd.qcut((df["s"] + jit).rank(), 5, labels=False)
                    gq = df.groupby(q5)["f"].mean()
                    row[f"spread_{nm}"] = float(gq.get(4, np.nan)
                                                - gq.get(0, np.nan))
                price_rows.append(row)
        log(f"{p.date()}: flagship-SE>0 em "
            f"{int((se2 > 0).sum())} gestores")

    # ---- reports ----------------------------------------------------------- #
    L = ["# cascade v2 - saliencia + marginalidade + pecking", ""]
    bs = pd.DataFrame(b_series)
    if len(bs):
        L += ["## A2 - mecanismo com controle de performance", "",
              f"- b(SE2 | rbook): media {bs['b_se2'].mean():+.4f} "
              f"(t={nw_tstat(bs['b_se2']):+.2f}, {len(bs)} tri) - "
              f"pre-registro NEGATIVO",
              f"- c(rbook): media {bs['c_rbook'].mean():+.4f} "
              f"(t={nw_tstat(bs['c_rbook']):+.2f}) - referencia: fluxo "
              f"persegue performance", ""]
    if mech_rows:
        M = pd.concat(mech_rows, ignore_index=True)
        neg = M[M["rbook"] < 0]
        pos = M[M["rbook"] >= 0]

        def slope_by(sub):
            out = []
            for pp, g in sub.groupby("period"):
                if len(g) > 80 and g["se2"].std() > 0:
                    out.append(float(np.polyfit(g["se2"], g["flow"], 1)[0]))
            return pd.Series(out)

        sn, sp = slope_by(neg), slope_by(pos)
        L += [f"- A2b interacao: b em fundos com rbook<0 = {sn.mean():+.3f} "
              f"(t={nw_tstat(sn):+.2f}) vs rbook>=0 = {sp.mean():+.3f} "
              f"(t={nw_tstat(sp):+.2f}) - esperado mais negativo no 1o", ""]
    pr = pd.DataFrame(price_rows)
    if len(pr):
        pr.to_csv(RESULTS / "cascade_v2_events.csv", index=False)
        L += ["## B2 - preco nos inocentes liquidos (Q4-Q0, esperado "
              "POSITIVO)", "",
              f"- gestores atingidos/tri: {pr['n_hit_mgrs'].mean():.0f}"]
        for nm, lbl in [("raw", "raw"), ("resid", "resid size/ADV"),
                        ("placebo", "placebo (SE2 permutado)")]:
            s = pr[f"spread_{nm}"].dropna()
            if len(s):
                L.append(f"- **{lbl}**: {s.mean():+.4f}/tri "
                         f"(t={nw_tstat(s):+.2f}, {len(s)} tri)")
    (RESULTS / "CASCADE_V2_REPORT.md").write_text("\n".join(L),
                                                  encoding="utf-8")
    log("done -> results/")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    main(**vars(ap.parse_args()))
