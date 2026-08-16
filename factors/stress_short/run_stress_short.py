"""Stress-anticipated distress short: can the SYNTHETIC daily stress
detector front-run the distress_mom effect - shorting the manager's book
the day he turns hot, a quarter BEFORE his filing reveals the outflow?

    python run_stress_short.py            # full sample
    python run_stress_short.py --smoke

RATIONALE: distress_mom (production, Sharpe 0.74 standalone) waits for
the FILING that reveals the redemption. The stopout module showed the
daily synthetic stress signal identifies eventual forced sellers one
quarter earlier (forced-sale rate 12.2% vs 6.7% - 2x - though t=1.62 on
19 quarters). If distress = information + continued selling, the decline
of the distressed book should be capturable from the DETECTION day, not
just from the filing day.

EVENT: manager's FIRST hot day in the window (Stress > 2 after >= 10
calm days). BASKET: his top-20 holdings by dollar/ADV (where his selling
must concentrate in days-of-ADV terms). OUTCOME: basket excess return
(vs market) over +5/+10/+20 days - pre-registered NEGATIVE (this is a
SHORT thesis). PLACEBO: same-day basket of a random calm manager in the
same AUM tercile - must be ~0. The paired quarter-clustered delta is the
verdict. Same universe rules as stopout (ETF instruments removed,
structural eligibility, never skill).
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
STRESS_CUT = 2.0
CALM_DAYS = 10
TOPN = 20


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
        if d1 - d0 < 20 or d1 + 22 >= len(dates):
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

        # per-manager top-N basket by dollar/ADV
        da = Vv / np.where(adv_w > 0, adv_w, np.nan)[None, :]
        da = np.where(np.isfinite(da), da, 0.0)
        topn_idx = np.argsort(-da, axis=1)[:, :TOPN]

        aum_e = aum.reindex(V.index)
        ter = pd.qcut(aum_e.rank(method="first"), 3, labels=False).values
        rng = np.random.default_rng(qi)

        hot_hist = np.zeros(len(V), dtype=int)
        fired = np.zeros(len(V), dtype=bool)
        n_ev = 0
        for t in range(5, Dw - 1):
            pain = Wn @ (E[t] < -sig).astype(float)
            z1 = -(dd[:, t] - dd[:, t].mean()) / (dd[:, t].std() + 1e-12)
            z2 = (pain - pain.mean()) / (pain.std() + 1e-12)
            stress = z1 + z2
            hot = stress > STRESS_CUT
            new_hot = hot & (~fired) & (hot_hist >= CALM_DAYS)
            gd = d0 + t
            for mi in np.where(new_hot)[0]:
                if gd + 21 >= len(dates):
                    continue
                basket = [T[j] for j in topn_idx[mi] if da[mi, j] > 0]
                if len(basket) < 8:
                    continue
                calm_pool = np.where((~hot) & (ter == ter[mi])
                                     & (hot_hist >= CALM_DAYS))[0]
                if not len(calm_pool):
                    continue
                pj = rng.choice(calm_pool)
                pbasket = [T[j] for j in topn_idx[pj] if da[pj, j] > 0]
                row = {"period": q, "gd": gd}
                for h in (5, 10, 20):
                    c0 = cum_ex[basket].iloc[gd]
                    row[f"car{h}"] = float(
                        (cum_ex[basket].iloc[gd + h] - c0)
                        .clip(-0.5, 0.5).mean())
                    c0p = cum_ex[pbasket].iloc[gd]
                    row[f"pl{h}"] = float(
                        (cum_ex[pbasket].iloc[gd + h] - c0p)
                        .clip(-0.5, 0.5).mean())
                row["basket"] = "|".join(basket)
                rows.append(row)
                fired[mi] = True
                n_ev += 1
            hot_hist = np.where(hot, 0, hot_hist + 1)
        log(f"{q.date()}: {n_ev} eventos hot")

    ev = pd.DataFrame(rows)
    ev.to_csv(RESULTS / "stress_short_events.csv", index=False)
    L = ["# stress_short - short no book do gestor no DIA da deteccao de "
         "stress", "",
         "Basket = top-20 nomes por dolar/ADV do gestor recem-hot; placebo "
         "= gestor calmo do mesmo tercil de AUM no mesmo dia. Pre-registro: "
         "CAR do basket NEGATIVO (tese short), placebo ~0.", ""]
    if len(ev):
        qg = ev.groupby("period")
        L.append(f"- {len(ev)} eventos em {ev['period'].nunique()} tri\n")
        for h in (5, 10, 20):
            m = qg[f"car{h}"].mean()
            mp = qg[f"pl{h}"].mean()
            dlt = (qg[f"car{h}"].mean() - qg[f"pl{h}"].mean()).dropna()
            L.append(f"- **CAR +{h}d**: tese {ev[f'car{h}'].mean():+.4f} "
                     f"(t={nw_tstat(m):+.2f}) | placebo "
                     f"{ev[f'pl{h}'].mean():+.4f} (t={nw_tstat(mp):+.2f}) "
                     f"| delta {dlt.mean():+.4f} (t={nw_tstat(dlt):+.2f})")
    # ---- tactical PnL: short each event basket for 5 days ----------------- #
    # three cost rulers: gross | net trading only (BORROW = 0, user ask) |
    # net trading + daily borrow from the engine's rate
    if len(ev):
        HOLD = 5
        RT = 0.0010                      # 10 bps round trip per event
        active: dict[int, list] = {}
        for _, r in ev.iterrows():
            bk = r["basket"].split("|")
            for dd_ in range(1, HOLD + 1):
                active.setdefault(int(r["gd"]) + dd_, []).append(bk)
        days = sorted(active)
        out = []
        for gd in days:
            if gd >= len(dates):
                continue
            legs, bors = [], []
            for bk in active[gd]:
                e_ = ex.iloc[gd].reindex(bk).dropna()
                if len(e_):
                    legs.append(-float(e_.clip(-0.5, 0.5).mean()))
                    bors.append(float(mdta.daily_borrow_rate[
                        [t for t in bk if t in mdta.daily_borrow_rate
                         .columns]].iloc[gd].mean()))
            if legs:
                g_ = float(np.mean(legs))
                b_ = float(np.mean(bors)) if bors else 0.0
                out.append({"date": dates[gd], "gross": g_,
                            "net0": g_ - RT / HOLD,
                            "net": g_ - RT / HOLD - b_})
        ds = pd.DataFrame(out).set_index("date")
        ds.to_csv(RESULTS / "stress_short_pnl.csv")

        def sh(col):
            s = ds[col]
            return (s.mean() / (s.std() + 1e-12) * np.sqrt(252),
                    s.mean() * 252 * 100)

        L += ["", "## PnL tatico do short (hold 5d, media dos baskets "
              "ativos por dia)", f"- {len(ds)} dias ativos"]
        for col, lbl in [("gross", "BRUTO"),
                         ("net0", "líquido trading, BORROW=0"),
                         ("net", "líquido trading + borrow do motor")]:
            s_, a_ = sh(col)
            L.append(f"- **{lbl}**: Sharpe {s_:+.2f} | {a_:+.1f}%/aa "
                     f"nos dias ativos")
    (RESULTS / "STRESS_SHORT_REPORT.md").write_text("\n".join(L),
                                                    encoding="utf-8")
    log("done -> results/")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    main(**vars(ap.parse_args()))
