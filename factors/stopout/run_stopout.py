"""Stop-out / forced-liquidation tactical framework - MVP of the research
memo in factors/stopping_after_drawdon (doc sections 5-9, 33).

    python run_stopout.py            # full sample
    python run_stopout.py --smoke    # last ~12 quarters

CAUSAL CHAIN (four stages; each gets its own gate, in order):
    synthetic disclosed-book drawdown (daily, from drifted PIT holdings)
      -> manager under stress                       [state]
      -> ACTIVE liquidation (broad selling)         [gate H1 - make-or-break]
      -> temporary pressure on his holdings         [H4 continuation]
      -> exhaustion -> tactical rebound             [H5 - the alpha claim]

KEY PRIOR ART INSIDE THE PROJECT: quarterly distress_mom found CONTINUATION,
not reversal - so the naive "fund in drawdown -> buy its stocks" is already
falsified at the quarterly clock. This module only claims a DAYS-scale
window: information continuation (months) and a small tactical rebound
after flow exhaustion (days) can coexist (doc section 31).

UNIVERSE (structural, never skill):
  - ETF instruments removed EVERYWHERE using the audited flag list
    (factors/ETF_strat/data/etf_universe_flags.csv, is_etf=True) - an ETF
    line is not a discretionary position and pollutes both the synthetic
    book and the pressure map;
  - eligible managers: 15-500 positions, book >= $250M, ticker coverage
    >= 70%, holdings persistence >= 50% (prior-quarter positions still
    held), active share vs the VW universe >= 40% (a passive-like filer
    cannot hit a discretionary stop in the modeled sense).

DAILY OBJECTS inside each inter-decision window (dec_q -> dec_{q+1}, all
holdings public by construction):
  - synthetic book NAV from drifted weights (dollars x cum price relatives);
  - residual drawdown DD_perp (book return minus market, beta=1 MVP);
  - PainBreadth = weight share of holdings down more than 1 daily sigma;
  - Stress_m,t = z(-DD_perp) + z(PainBreadth) (cross-sectional z per day);
    stressed = Stress > 2;
  - SOF_i,t = sum over stressed managers of dollar holding / ADV_i.

GATES:
  H1 (make-or-break): managers stressed during the window must show the
     FORCED-SALE label at the next filing (implied flow bottom decile AND
     sell breadth top quintile). If stressed managers do not sell more
     than calm ones, everything downstream is noise - stop.
  H4 continuation: crashed high-SOF names still falling -> keep falling.
  H5 exhaustion rebound: SOF top decile + past-5d excess < -7% + first
     positive excess day -> long, CAR +1/+3/+5/+10 vs the SAME-day crash
     placebo with ZERO stressed ownership (same crash, no distressed
     holder - the Agarwal-style control). The PAIRED delta is the claim.
  PnL: every H5 event held 5 days, market-hedged, 10bps round trip ->
     daily strategy series, gross/net Sharpe.
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
from run_all import load_market, log                # noqa: E402
from run_fire import implied_flows                  # noqa: E402
from backtest_gp import nw_tstat                    # noqa: E402

RESULTS = HERE / "results"
ETF_FLAGS = HERE.parent / "ETF_strat" / "data" / "etf_universe_flags.csv"
DEC_LAG = 50
STRESS_CUT = 2.0
CRASH_5D = -0.07
SOF_TOP = 0.90          # top decile of positive SOF
HOLD = 5                # tactical holding days for the PnL
COST = 0.0010           # 10 bps round trip per event


def main(smoke: bool = False) -> None:
    RESULTS.mkdir(exist_ok=True)
    cmap, mdta = load_market()
    dates = mdta.prices.index
    rets = mdta.returns
    bench = mdta.benchmark_returns.reindex(dates).fillna(0.0)
    ex = rets.sub(bench, axis=0)                    # excess vs market
    cum_ex = ex.cumsum()
    adv = mdta.dollar_volume.rolling(63, min_periods=20).median()
    vol_d = mdta.volatility / np.sqrt(252.0)
    shares = mc.shares_panel(dates, mdta.tickers, mdta.prices, mdta.prices_raw)
    mcap = mc.mktcap_panel(mdta.prices_raw, shares)

    etf = pd.read_csv(ETF_FLAGS, usecols=["instrument_id", "is_etf"])
    etf_set = set(etf.loc[etf["is_etf"] == True, "instrument_id"])  # noqa: E712
    log(f"ETF filter: {len(etf_set)} instruments flagged")

    qs = [q for q in pn.quarters()
          if pd.Timestamp("2013-06-30") <= q <= dates[-1] - pd.Timedelta(days=140)]
    if smoke:
        qs = qs[-12:]
    log(f"{len(qs)} quarters")

    stress_prev: dict = {}      # window stats per manager, for H1 next q
    h1_rows, ev_rows = [], []
    pnl_daily: dict[int, list] = {}

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

        # ---- H1 labels for the PREVIOUS window's stress ------------------- #
        if stress_prev:
            di_p = dates.searchsorted(q, side="right") - 1
            di_p1 = dates.searchsorted(q1, side="right") - 1
            ret_q = (mdta.prices.iloc[di_p] / mdta.prices.iloc[di_p1] - 1.0)
            fl = implied_flows(cur, prev, cmap, ret_q.fillna(0.0))
            pcur = cur.groupby(["filer_id", "instrument_id"])["shares"] \
                .sum()
            pprev = prev.groupby(["filer_id", "instrument_id"])["shares"] \
                .sum()
            tr = pd.concat([pprev.rename("o"), pcur.rename("n")], axis=1)
            tr = tr[tr["o"].notna()]
            tr["cut"] = tr["n"].fillna(0.0) < 0.95 * tr["o"]
            sb = tr.groupby(level=0)["cut"].mean()
            lab = pd.DataFrame({"flow": fl["flow"], "sb": sb}).dropna()
            if len(lab) > 200:
                f_cut = lab["flow"].quantile(0.10)
                s_cut = lab["sb"].quantile(0.80)
                lab["forced"] = (lab["flow"] <= f_cut) & (lab["sb"] >= s_cut)
                st = pd.Series(stress_prev)
                common = lab.index.intersection(st.index)
                if len(common) > 200:
                    ls = lab.loc[common]
                    ss = st.loc[common]
                    h1_rows.append({
                        "period": q,
                        "rate_stressed": float(ls["forced"][ss > STRESS_CUT]
                                               .mean()),
                        "n_stressed": int((ss > STRESS_CUT).sum()),
                        "rate_calm": float(ls["forced"][ss <= 0].mean()),
                        "sb_stressed": float(ls["sb"][ss > STRESS_CUT]
                                             .mean()),
                        "sb_calm": float(ls["sb"][ss <= 0].mean()),
                        "flow_stressed": float(ls["flow"][ss > STRESS_CUT]
                                               .mean()),
                        "flow_calm": float(ls["flow"][ss <= 0].mean())})

        # ---- eligibility -------------------------------------------------- #
        d = cur[["filer_id", "instrument_id", "value_usd"]].copy()
        d["ticker"] = d["instrument_id"].map(cmap)
        d = d.dropna(subset=["ticker"])
        cover = (d.groupby("filer_id")["value_usd"].sum()
                 / cur.groupby("filer_id")["value_usd"].sum())
        aum = cur.groupby("filer_id")["value_usd"].sum()
        npos = cur.groupby("filer_id")["instrument_id"].nunique()
        prev_sets = prev.groupby("filer_id")["instrument_id"].agg(set)
        cur_sets = cur.groupby("filer_id")["instrument_id"].agg(set)
        pers = {}
        for m in cur_sets.index:
            po = prev_sets.get(m)
            if po:
                pers[m] = len(cur_sets[m] & po) / max(len(po), 1)
        pers = pd.Series(pers)
        di = dates.searchsorted(dec, side="right") - 1
        mc_d = mcap.iloc[di]
        bw = mc_d / mc_d.sum()
        act = {}
        for m, g in d.groupby("filer_id"):
            w = g.set_index("ticker")["value_usd"]
            w = w / w.sum()
            act[m] = 0.5 * float(
                (w - bw.reindex(w.index).fillna(0.0)).abs().sum()
                + (1 - bw.reindex(w.index).fillna(0.0).sum()) * 0)
        act = pd.Series(act)
        elig = aum.index[(npos.between(15, 500)) & (aum >= 250e6)
                         & (cover.reindex(aum.index) >= 0.70)
                         & (pers.reindex(aum.index) >= 0.50)
                         & (act.reindex(aum.index) >= 0.40)]
        if len(elig) < 150:
            stress_prev = {}
            continue

        # ---- matrices for the daily window -------------------------------- #
        db = d[d["filer_id"].isin(elig)]
        V = db.pivot_table(index="filer_id", columns="ticker",
                           values="value_usd", aggfunc="sum").fillna(0.0)
        T = [t for t in V.columns if t in rets.columns]
        V = V[T]
        Vv = V.values
        Wn = Vv / Vv.sum(axis=1, keepdims=True)
        d0 = dates.searchsorted(dec, side="right")
        d1 = dates.searchsorted(dec2, side="right") - 1
        if d1 - d0 < 20:
            stress_prev = {}
            continue
        R = rets[T].iloc[d0:d1].fillna(0.0).values          # D x N
        E = ex[T].iloc[d0:d1].fillna(0.0).values
        B = bench.iloc[d0:d1].values
        sig = vol_d[T].iloc[d0].fillna(0.02).values
        adv_w = adv[T].iloc[d0].values
        Dw = R.shape[0]

        cumrel = np.cumprod(1.0 + R, axis=0)                # D x N
        S = Wn @ cumrel.T                                   # M x D book rel
        book_ret = np.diff(np.column_stack([np.ones(len(S)), S]), axis=1) \
            / np.column_stack([np.ones(len(S)), S])[:, :-1]
        resid = book_ret - B[None, :]
        nav = np.cumprod(1.0 + resid, axis=1)
        dd = nav / np.maximum.accumulate(nav, axis=1) - 1.0

        stress_stats = {}
        sof_events_q, cont_q = [], []
        plc_events_q = []
        max_stress = np.full(len(V), -9.0)
        for t in range(5, Dw - 1):
            pain = Wn @ (E[t] < -sig).astype(float)
            z1 = -(dd[:, t] - dd[:, t].mean()) / (dd[:, t].std() + 1e-12)
            z2 = (pain - pain.mean()) / (pain.std() + 1e-12)
            stress = z1 + z2
            max_stress = np.maximum(max_stress, stress)
            hot = stress > STRESS_CUT
            if not hot.any():
                continue
            sof = (Vv[hot].sum(axis=0) / adv_w)
            sof = np.where(np.isfinite(sof), sof, 0.0)
            pos = sof[sof > 0]
            if len(pos) < 30:
                continue
            cut = np.quantile(pos, SOF_TOP)
            past5 = E[t - 5:t].sum(axis=0)
            today = E[t]
            gd0 = d0 + t                                     # global index
            crash = past5 < CRASH_5D
            hi = sof >= cut
            # H5 exhaustion long: crash + high SOF + first positive day
            for j in np.where(crash & hi & (today > 0))[0]:
                sof_events_q.append((gd0, T[j]))
            # H4 continuation: crash + high SOF + still negative
            for j in np.where(crash & hi & (today < 0))[0]:
                cont_q.append((gd0, T[j]))
            # placebo: same crash + positive day + ZERO stressed ownership
            for j in np.where(crash & (sof <= 0) & (today > 0))[0]:
                plc_events_q.append((gd0, T[j]))
        stress_prev = dict(zip(V.index, max_stress))

        # ---- CARs (global clock, may cross the window edge) --------------- #
        def cars(evts, tag):
            out = []
            for gd, t in evts:
                if gd + 11 >= len(dates):
                    continue
                c0 = cum_ex[t].iloc[gd]
                row = {"period": q, "tag": tag, "ticker": t, "gd": gd}
                for h in (1, 3, 5, 10):
                    row[f"car{h}"] = float(np.clip(
                        cum_ex[t].iloc[gd + h] - c0, -0.5, 0.5))
                out.append(row)
            return out

        rng = np.random.default_rng(qi)
        if len(plc_events_q) > len(sof_events_q) > 0:
            sel = rng.permutation(len(plc_events_q))[:len(sof_events_q)]
            plc_events_q = [plc_events_q[i] for i in sel]
        ev_rows += cars(sof_events_q, "exhaust_long")
        ev_rows += cars(cont_q, "continuation")
        ev_rows += cars(plc_events_q, "placebo_nosof")
        for gd, t in sof_events_q:                      # tactical PnL book
            pnl_daily.setdefault(gd, []).append(t)
        log(f"{q.date()}: elig {len(elig)}, exhaust {len(sof_events_q)}, "
            f"cont {len(cont_q)}, placebo {len(plc_events_q)}")

    # ---- aggregate --------------------------------------------------------- #
    ev = pd.DataFrame(ev_rows)
    ev.to_csv(RESULTS / "stopout_events.csv", index=False)
    h1 = pd.DataFrame(h1_rows)
    h1.to_csv(RESULTS / "h1_gate.csv", index=False)

    L = ["# stopout - drawdown sintetico, stress e reversao tatica", "",
         "ETFs removidos dos books (lista auditada do ETF_strat). "
         "Universo estrutural: 15-500 posicoes, >=250M, persistencia>=50%, "
         "active share>=40%.", ""]
    if len(h1):
        d_rate = (h1["rate_stressed"] - h1["rate_calm"]).dropna()
        d_sb = (h1["sb_stressed"] - h1["sb_calm"]).dropna()
        d_fl = (h1["flow_stressed"] - h1["flow_calm"]).dropna()
        L += ["## GATE H1 - stress sintetico preve venda forcada no filing "
              "seguinte?", "",
              f"- taxa de forced-sale: stressed "
              f"{h1['rate_stressed'].mean():.3f} vs calm "
              f"{h1['rate_calm'].mean():.3f} (delta t="
              f"{nw_tstat(d_rate):+.2f}, {len(h1)} tri; media "
              f"{h1['n_stressed'].mean():.0f} gestores stressed/tri)",
              f"- sell breadth: {h1['sb_stressed'].mean():.3f} vs "
              f"{h1['sb_calm'].mean():.3f} (t={nw_tstat(d_sb):+.2f})",
              f"- fluxo implicito: {h1['flow_stressed'].mean():+.4f} vs "
              f"{h1['flow_calm'].mean():+.4f} (t={nw_tstat(d_fl):+.2f})",
              ""]
    if len(ev):
        L += ["## Eventos taticos (CAR em excesso vs mercado, cluster/tri)",
              ""]
        for tag, lbl in [("exhaust_long", "H5 LONG exaustao (tese)"),
                         ("placebo_nosof", "placebo: mesmo crash, SEM dono "
                          "stressed"),
                         ("continuation", "H4 continuacao (ainda caindo)")]:
            g = ev[ev["tag"] == tag]
            if not len(g):
                continue
            qg = g.groupby("period")
            L.append(f"### {lbl} ({len(g)} eventos)")
            for h in (1, 3, 5, 10):
                m = qg[f"car{h}"].mean()
                L.append(f"- CAR +{h}d: {g[f'car{h}'].mean():+.4f} "
                         f"(t={nw_tstat(m):+.2f})")
            L.append("")
        te = ev[ev["tag"] == "exhaust_long"].groupby("period")["car5"].mean()
        tp = ev[ev["tag"] == "placebo_nosof"].groupby("period")["car5"].mean()
        dd_ = (te - tp).dropna()
        L.append(f"- **delta pareado tese - placebo (CAR5)**: "
                 f"{dd_.mean():+.4f} (t={nw_tstat(dd_):+.2f}, "
                 f"{len(dd_)} tri)")

    # tactical PnL: each exhaust event held HOLD days, market-hedged
    if pnl_daily:
        first = min(pnl_daily) ; last = max(pnl_daily) + HOLD + 1
        daily = []
        for gd in range(first, min(last, len(dates) - 1)):
            legs = []
            for e0 in range(max(first, gd - HOLD + 1), gd + 1):
                for t in pnl_daily.get(e0, []):
                    r = float(ex[t].iloc[gd + 1]) if t in ex.columns else 0.0
                    c = COST / HOLD
                    legs.append(np.clip(r, -0.5, 0.5) - c)
            if legs:
                daily.append((dates[gd + 1], float(np.mean(legs)),
                              len(legs)))
        if daily:
            ds = pd.DataFrame(daily, columns=["date", "ret", "n"]) \
                .set_index("date")
            ds.to_csv(RESULTS / "tactical_pnl.csv")
            ann = ds["ret"].mean() * 252
            sh = ds["ret"].mean() / (ds["ret"].std() + 1e-12) * np.sqrt(252)
            days_active = len(ds)
            L += ["", "## PnL tatico (eventos H5, hold 5d, hedge de "
                  "mercado, 10bps ida-e-volta)",
                  f"- Sharpe (dias ativos): {sh:+.2f} | retorno "
                  f"{ann * 100:+.1f}%/aa nos dias ativos | "
                  f"{days_active} dias ativos | media "
                  f"{ds['n'].mean():.1f} posicoes/dia"]
    (RESULTS / "STOPOUT_REPORT.md").write_text("\n".join(L),
                                               encoding="utf-8")
    log("done -> results/")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    main(**vars(ap.parse_args()))
