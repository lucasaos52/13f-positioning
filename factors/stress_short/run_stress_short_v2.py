"""stress_short v2 - two refinements over v1, both requested:

    python run_stress_short_v2.py            # full sample
    python run_stress_short_v2.py --smoke

1. CORRELATION TRIGGER (the user's original intuition, memo section 7.3).
   v1's PainBreadth measures how much of the book falls together on a day
   - which any market selloff produces. CorrShock measures whether the
   book's internal correlations ROSE vs the manager's own normal:
       CorrShock_m,t = sigma_book(10d realized) / sqrt(sum w_i^2 var_i)
   (inverse diversification ratio: numerator = the vol the book HAS,
   denominator = the vol it would have if positions were independent).
   Entered as a THROUGH-TIME z against the manager's own trailing window
   (>= 15 days), not cross-sectional - what matters is HIS correlation
   rising vs HIS normal.
   ABLATION on the same sample answers "does correlation add?":
       A  z(-DD) + z(PainBreadth)                  [v1 baseline]
       B  z(-DD) + z(PainBreadth) + z_t(CorrShock) [v2]
       C  z_t(CorrShock) alone                     [pure intuition]

2. THRESHOLD TRANSPARENCY. v1 used Stress > 2.0 (a pre-registered "two
   sigma" convention, never optimized) and hold=5 chosen alongside the CAR
   horizons - the PnL's hold=5 was picked AFTER seeing CAR5 strongest,
   a mild look-ahead confessed here. v2 (a) replaces the fixed cut with
   the day's cross-sectional quantile (top 2% of managers, self-adapting)
   and (b) reports the FULL sensitivity grid cut {p97, p98, p99} x hold
   {3, 5, 10} with no selection - the reader sees the whole surface.

Everything else identical to v1: eligibility, ETF filter, top-20 by
dollar/ADV baskets, calm-manager placebo, quarter-clustered NW.
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
CALM_DAYS = 10
TOPN = 20
Q_CUT = 0.98            # headline: top 2% of managers that day
GRID_CUTS = [0.97, 0.98, 0.99]
GRID_HOLDS = [3, 5, 10]


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

        # rolling 10d realized: book sigma and independent-book sigma
        E_df = pd.DataFrame(E)
        var10 = E_df.rolling(10, min_periods=8).var().values      # D x N
        book10 = pd.DataFrame(resid.T).rolling(10, min_periods=8) \
            .std().values                                          # D x M
        W2 = Wn ** 2

        da = Vv / np.where(adv_w > 0, adv_w, np.nan)[None, :]
        da = np.where(np.isfinite(da), da, 0.0)
        topn_idx = np.argsort(-da, axis=1)[:, :TOPN]
        aum_e = aum.reindex(V.index)
        ter = pd.qcut(aum_e.rank(method="first"), 3, labels=False).values
        rng = np.random.default_rng(qi)

        M = len(V)
        cs_hist = np.full((Dw, M), np.nan)
        hot_hist = {v: np.zeros(M, dtype=int) for v in "ABC"}
        fired = {v: np.zeros(M, dtype=bool) for v in "ABC"}
        for t in range(10, Dw - 1):
            pain = Wn @ (E[t] < -sig).astype(float)
            z1 = -(dd[:, t] - dd[:, t].mean()) / (dd[:, t].std() + 1e-12)
            z2 = (pain - pain.mean()) / (pain.std() + 1e-12)
            indep = np.sqrt(np.maximum(W2 @ np.nan_to_num(var10[t]), 1e-12))
            cs = book10[t] / indep
            cs_hist[t] = cs
            lo = max(10, t - 20)
            hist = cs_hist[lo:t]
            mu = np.nanmean(hist, axis=0)
            sd = np.nanstd(hist, axis=0)
            z3 = np.where(sd > 1e-9, (cs - mu) / sd, 0.0)
            z3 = np.nan_to_num(z3)

            stress = {"A": z1 + z2, "B": z1 + z2 + z3, "C": z3}
            for v, sv in stress.items():
                cut = np.quantile(sv, Q_CUT)
                hot = sv > cut
                new_hot = hot & (~fired[v]) & (hot_hist[v] >= CALM_DAYS)
                gd = d0 + t
                for mi in np.where(new_hot)[0]:
                    if gd + 11 >= len(dates):
                        continue
                    basket = [T[j] for j in topn_idx[mi] if da[mi, j] > 0]
                    if len(basket) < 8:
                        continue
                    calm_pool = np.where((~hot) & (ter == ter[mi])
                                         & (hot_hist[v] >= CALM_DAYS))[0]
                    if not len(calm_pool):
                        continue
                    pj = rng.choice(calm_pool)
                    pbasket = [T[j] for j in topn_idx[pj] if da[pj, j] > 0]
                    row = {"period": q, "variant": v, "gd": gd,
                           "z_used": float(sv[mi])}
                    for h in GRID_HOLDS:
                        c0 = cum_ex[basket].iloc[gd]
                        row[f"car{h}"] = float(
                            (cum_ex[basket].iloc[gd + h] - c0)
                            .clip(-0.5, 0.5).mean())
                        c0p = cum_ex[pbasket].iloc[gd]
                        row[f"pl{h}"] = float(
                            (cum_ex[pbasket].iloc[gd + h] - c0p)
                            .clip(-0.5, 0.5).mean())
                    # sensitivity: would stricter cuts also fire?
                    for qc in GRID_CUTS:
                        row[f"cut{int(qc * 100)}"] = bool(
                            sv[mi] > np.quantile(sv, qc))
                    rows.append(row)
                    fired[v][mi] = True
                hot_hist[v] = np.where(hot, 0, hot_hist[v] + 1)
        log(f"{q.date()}: eventos A/B/C = "
            f"{sum(1 for r in rows if r['period'] == q and r['variant'] == 'A')}/"
            f"{sum(1 for r in rows if r['period'] == q and r['variant'] == 'B')}/"
            f"{sum(1 for r in rows if r['period'] == q and r['variant'] == 'C')}")

    ev = pd.DataFrame(rows)
    ev.to_csv(RESULTS / "stress_v2_events.csv", index=False)

    L = ["# stress_short v2 - ablacao do trigger de correlacao + "
         "sensibilidade de limiares", "",
         "A = z(-DD)+z(PainBreadth) [v1] | B = A + z_t(CorrShock) [v2] | "
         "C = z_t(CorrShock) puro. Corte headline = top 2% do dia "
         "(quantil, nao valor fixo). Grade completa reportada sem "
         "selecao.", ""]
    if len(ev):
        for v, lbl in [("A", "A - v1 (DD+PainBreadth)"),
                       ("B", "B - v2 (+ CorrShock)"),
                       ("C", "C - CorrShock puro")]:
            g = ev[ev["variant"] == v]
            if not len(g):
                continue
            qg = g.groupby("period")
            L.append(f"## {lbl} ({len(g)} eventos, "
                     f"{g['period'].nunique()} tri)")
            for h in GRID_HOLDS:
                dlt = (qg[f"car{h}"].mean() - qg[f"pl{h}"].mean()).dropna()
                L.append(f"- +{h}d: tese {g[f'car{h}'].mean():+.4f} "
                         f"(t={nw_tstat(qg[f'car{h}'].mean()):+.2f}) | "
                         f"placebo {g[f'pl{h}'].mean():+.4f} | "
                         f"**delta {dlt.mean():+.4f} "
                         f"(t={nw_tstat(dlt):+.2f})**")
            L.append("")
        L += ["## Grade de sensibilidade (variante B, delta tese-placebo)",
              ""]
        gB = ev[ev["variant"] == "B"]
        for qc in GRID_CUTS:
            sub = gB[gB[f"cut{int(qc * 100)}"]]
            if not len(sub):
                continue
            parts = []
            for h in GRID_HOLDS:
                qg = sub.groupby("period")
                dlt = (qg[f"car{h}"].mean() - qg[f"pl{h}"].mean()).dropna()
                parts.append(f"+{h}d {dlt.mean():+.4f} "
                             f"(t={nw_tstat(dlt):+.2f})")
            L.append(f"- corte p{int(qc * 100)} ({len(sub)} ev): "
                     + " | ".join(parts))
    (RESULTS / "STRESS_V2_REPORT.md").write_text("\n".join(L),
                                                 encoding="utf-8")
    log("done -> results/")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    main(**vars(ap.parse_args()))
