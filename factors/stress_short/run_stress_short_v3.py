"""stress_short v3 - variant D: the liquidation-FOOTPRINT trigger
(PCShare x Alignment, memo sections 7.4/8.2), the last correlation-family
refinement with its own causal story.

    python run_stress_short_v3.py            # full sample
    python run_stress_short_v3.py --smoke

WHY D IS DIFFERENT FROM THE DEAD C: correlation rising IN ANY SHAPE is
generic stress (market/sector noise - that is what killed CorrShock).
Correlation rising IN THE SHAPE OF THE MANAGER'S EXIT - his big-by-
liquidity positions falling together and proportionally to what he would
have to sell - is a liquidation fingerprint. The question stops being
"did everything correlate?" and becomes "did it correlate in the shape
of his way out?".

CONSTRUCTION (every 5th day - eigen work is O(managers x days)):
    for manager m, day t:
      X   = last 15d of residual returns of HIS holdings (demeaned)
      v1  = top eigenvector of X'X by power iteration (warm-started at
            the liquidation vector, 4 iterations - converges to the true
            top eigenvector regardless of start)
      PCShare  = lambda1 / trace          (book became a one-factor basket)
      Align    = |cos(v1, a_m)|            a_m = his dollar/ADV vector
      Dfeat    = PCShare x Align
    trigger: through-time z of Dfeat vs the manager's OWN trailing grid
    history, z_t > 2.0 ABSOLUTE (the v2 ablation lesson: stress is an
    absolute state - quantile cuts fire in calm markets and die).

HEAD-TO-HEAD: variant V1FIX (the original z(-DD)+z(PainBreadth) > 2.0
absolute) runs on the SAME 5-day grid, same baskets, same calm-manager
placebo, same quarters - so the comparison is clean, not cross-run.

PRE-REGISTERED: D's paired delta (thesis - placebo) at +5d more negative
than V1FIX's on the same sample, or D dies and the correlation family is
closed complete (level -> failed in v2; shape -> failed here).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
for sub in ("", "general_plan"):
    sys.path.insert(0, str(HERE.parent / sub))

import market_cap as mc                             # noqa: E402
import panel as pn                                  # noqa: E402
from backtest_gp import nw_tstat                    # noqa: E402
from run_all import load_market, log                # noqa: E402

RESULTS = HERE / "results"
ETF_FLAGS = HERE.parent / "ETF_strat" / "data" / "etf_universe_flags.csv"
DEC_LAG = 50
CUT = 2.0
GRID = 5                 # evaluate triggers every 5th day
CALM_STEPS = 2           # ~10d calm before a fresh event
TOPN = 20
EIG_WIN = 15


def main(smoke: bool = False) -> None:
    RESULTS.mkdir(exist_ok=True)
    cmap, mdta = load_market()
    dates = mdta.prices.index
    rets = mdta.returns
    bench = mdta.benchmark_returns.reindex(dates).fillna(0.0)
    ex = rets.sub(bench, axis=0)
    cum_ex = ex.cumsum()
    adv = mdta.dollar_volume.rolling(63, min_periods=20).median()
    vol_d = mdta.volatility / np.sqrt(252.0)
    shares = mc.shares_panel(dates, mdta.tickers, mdta.prices, mdta.prices_raw)
    mcap = mc.mktcap_panel(mdta.prices_raw, shares)
    etf = pd.read_csv(ETF_FLAGS, usecols=["instrument_id", "is_etf"])
    etf_set = set(etf.loc[etf["is_etf"] == True, "instrument_id"])  # noqa: E712

    qs = [q for q in pn.quarters()
          if pd.Timestamp("2013-06-30") <= q <= dates[-1] - pd.Timedelta(days=140)]
    if smoke:
        qs = qs[-12:]
    log(f"{len(qs)} quarters")

    rows = []
    for qi in range(1, len(qs) - 1):
        q, q1, q2 = qs[qi], qs[qi - 1], qs[qi + 1]
        dec = q + pd.Timedelta(days=DEC_LAG)
        dec2 = q2 + pd.Timedelta(days=DEC_LAG)
        if dec2 >= dates[-1] - pd.Timedelta(days=25):
            break
        cur = pn.snapshot_as_of(q, dec)
        prev = pn.snapshot_as_of(q1, dec)
        if min(len(cur), len(prev)) < 1000:
            continue
        cur = cur[~cur["instrument_id"].isin(etf_set)]
        prev = prev[~prev["instrument_id"].isin(etf_set)]

        d = cur[["filer_id", "instrument_id", "value_usd"]].copy()
        d["ticker"] = d["instrument_id"].map(cmap)
        d = d.dropna(subset=["ticker"])
        cover = (d.groupby("filer_id")["value_usd"].sum()
                 / cur.groupby("filer_id")["value_usd"].sum())
        aum = cur.groupby("filer_id")["value_usd"].sum()
        npos = cur.groupby("filer_id")["instrument_id"].nunique()
        prev_sets = prev.groupby("filer_id")["instrument_id"].agg(set)
        cur_sets = cur.groupby("filer_id")["instrument_id"].agg(set)
        pers = {m: len(cur_sets[m] & prev_sets.get(m, set()))
                / max(len(prev_sets.get(m, set())), 1)
                for m in cur_sets.index if m in prev_sets.index}
        pers = pd.Series(pers)
        elig = aum.index[(npos.between(15, 500)) & (aum >= 250e6)
                         & (cover.reindex(aum.index) >= 0.70)
                         & (pers.reindex(aum.index) >= 0.50)]
        if len(elig) < 150:
            continue

        db = d[d["filer_id"].isin(elig)]
        V = db.pivot_table(index="filer_id", columns="ticker",
                           values="value_usd", aggfunc="sum").fillna(0.0)
        T = [t for t in V.columns if t in rets.columns]
        V = V[T]
        Vv = V.values
        Wn = Vv / Vv.sum(axis=1, keepdims=True)
        d0 = dates.searchsorted(dec, side="right")
        d1 = dates.searchsorted(dec2, side="right") - 1
        if d1 - d0 < 25 or d1 + 12 >= len(dates):
            continue
        R = rets[T].iloc[d0:d1].fillna(0.0).values
        E = ex[T].iloc[d0:d1].fillna(0.0).values
        B = bench.iloc[d0:d1].values
        sig = vol_d[T].iloc[d0].fillna(0.02).values
        adv_w = adv[T].iloc[d0].values
        Dw = R.shape[0]

        cumrel = np.cumprod(1.0 + R, axis=0)
        S = Wn @ cumrel.T
        book_ret = np.diff(np.column_stack([np.ones(len(S)), S]), axis=1) \
            / np.column_stack([np.ones(len(S)), S])[:, :-1]
        resid = book_ret - B[None, :]
        nav = np.cumprod(1.0 + resid, axis=1)
        dd = nav / np.maximum.accumulate(nav, axis=1) - 1.0

        da = Vv / np.where(adv_w > 0, adv_w, np.nan)[None, :]
        da = np.where(np.isfinite(da), da, 0.0)
        topn_idx = np.argsort(-da, axis=1)[:, :TOPN]
        aum_e = aum.reindex(V.index)
        ter = pd.qcut(aum_e.rank(method="first"), 3, labels=False).values
        rng = np.random.default_rng(qi)
        M = len(V)

        # per-manager holdings index lists and liquidation unit vectors
        jlists, a_units = [], []
        for mi in range(M):
            jl = np.where(Vv[mi] > 0)[0]
            jlists.append(jl)
            av = da[mi, jl]
            n_ = np.linalg.norm(av)
            a_units.append(av / n_ if n_ > 0 else av)

        dfeat_hist: list[dict] = []
        hot_hist = {v: np.zeros(M, dtype=int) + CALM_STEPS
                    for v in ("V1FIX", "D")}
        fired = {v: np.zeros(M, dtype=bool) for v in ("V1FIX", "D")}
        for t in range(EIG_WIN, Dw - 1, GRID):
            pain = Wn @ (E[t] < -sig).astype(float)
            z1 = -(dd[:, t] - dd[:, t].mean()) / (dd[:, t].std() + 1e-12)
            z2 = (pain - pain.mean()) / (pain.std() + 1e-12)
            s_v1 = z1 + z2

            # variant D feature on this grid day
            W15 = E[t - EIG_WIN + 1:t + 1]
            dfeat = np.zeros(M)
            for mi in range(M):
                jl = jlists[mi]
                if len(jl) < 8:
                    continue
                X = W15[:, jl]
                X = X - X.mean(axis=0, keepdims=True)
                tr = float((X ** 2).sum())
                if tr <= 1e-12:
                    continue
                v = a_units[mi].copy()
                if not np.isfinite(v).all() or np.linalg.norm(v) == 0:
                    continue
                for _ in range(4):
                    v = X.T @ (X @ v)
                    n_ = np.linalg.norm(v)
                    if n_ <= 1e-15:
                        break
                    v = v / n_
                lam1 = float(np.linalg.norm(X @ v) ** 2)
                pcshare = lam1 / tr
                align = abs(float(v @ a_units[mi]))
                dfeat[mi] = pcshare * align
            hist = {mi: [h[mi] for h in dfeat_hist if h[mi] > 0]
                    for mi in range(M)}
            z3 = np.zeros(M)
            for mi in range(M):
                hh = hist[mi][-4:]
                if len(hh) >= 3 and np.std(hh) > 1e-9 and dfeat[mi] > 0:
                    z3[mi] = (dfeat[mi] - np.mean(hh)) / np.std(hh)
            dfeat_hist.append(dfeat)

            gd = d0 + t
            for vname, sv in (("V1FIX", s_v1), ("D", z3)):
                hot = sv > CUT
                new_hot = hot & (~fired[vname]) \
                    & (hot_hist[vname] >= CALM_STEPS)
                for mi in np.where(new_hot)[0]:
                    if gd + 11 >= len(dates):
                        continue
                    basket = [T[j] for j in topn_idx[mi] if da[mi, j] > 0]
                    if len(basket) < 8:
                        continue
                    calm_pool = np.where((~hot) & (ter == ter[mi]))[0]
                    if not len(calm_pool):
                        continue
                    pj = rng.choice(calm_pool)
                    pbasket = [T[j] for j in topn_idx[pj] if da[pj, j] > 0]
                    row = {"period": q, "variant": vname, "gd": gd}
                    for h in (3, 5, 10):
                        c0 = cum_ex[basket].iloc[gd]
                        row[f"car{h}"] = float(
                            (cum_ex[basket].iloc[gd + h] - c0)
                            .clip(-0.5, 0.5).mean())
                        c0p = cum_ex[pbasket].iloc[gd]
                        row[f"pl{h}"] = float(
                            (cum_ex[pbasket].iloc[gd + h] - c0p)
                            .clip(-0.5, 0.5).mean())
                    rows.append(row)
                    fired[vname][mi] = True
                hot_hist[vname] = np.where(hot, 0, hot_hist[vname] + 1)
        log(f"{q.date()}: eventos V1FIX/D = "
            f"{sum(1 for r in rows if r['period'] == q and r['variant'] == 'V1FIX')}/"
            f"{sum(1 for r in rows if r['period'] == q and r['variant'] == 'D')}")

    ev = pd.DataFrame(rows)
    ev.to_csv(RESULTS / "stress_v3_events.csv", index=False)
    L = ["# stress_short v3 - variante D (pegada de liquidacao: "
         "PCShare x Alignment)", "",
         "D = z_t(lambda1-share x |cos(v1, vetor dolar/ADV)|) > 2.0 "
         "absoluto, grade de 5d; V1FIX = spec original na MESMA grade/"
         "amostra/placebo.", ""]
    for vname, lbl in [("V1FIX", "V1FIX - spec original (baseline)"),
                       ("D", "D - pegada de liquidacao")]:
        g = ev[ev["variant"] == vname]
        if not len(g):
            continue
        qg = g.groupby("period")
        L.append(f"## {lbl} ({len(g)} eventos, {g['period'].nunique()} tri)")
        for h in (3, 5, 10):
            dlt = (qg[f"car{h}"].mean() - qg[f"pl{h}"].mean()).dropna()
            L.append(f"- +{h}d: tese {g[f'car{h}'].mean():+.4f} "
                     f"(t={nw_tstat(qg[f'car{h}'].mean()):+.2f}) | "
                     f"placebo {g[f'pl{h}'].mean():+.4f} | "
                     f"**delta {dlt.mean():+.4f} (t={nw_tstat(dlt):+.2f})**")
        L.append("")
    (RESULTS / "STRESS_V3_REPORT.md").write_text("\n".join(L),
                                                 encoding="utf-8")
    log("done -> results/")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    main(**vars(ap.parse_args()))
