"""Daily monitor suite - the three monitors from the survey, built on the
FINAL stress spec (v1: z(-DD)+z(PainBreadth), absolute cut 2.0 - the one
the v2 ablation defended). State watches the book; it never becomes a
signal (the project's law).

    python run_monitor.py            # full sample
    python run_monitor.py --smoke    # last ~12 quarters

MONITOR 1 - stress on OUR book:
  (a) long-leg early warning: each day, each combo long carries
      risk_i = sum over HOT managers of their dollar holding / ADV_i.
      TEST (actionable if true): within our long book, high-risk-tercile
      names underperform low-risk names over the next 5d (sampled every
      5d to avoid overlap; quarter-clustered NW).
  (b) short-leg squeeze alarm: a combo short with past-5d excess > +7%
      AND 5d volume > 2x its ADV is flagged. TEST: alarmed shorts keep
      rising over the next 5d (=> cover on alarm is the action).

MONITOR 2 - aggregate deleveraging index:
  AggStress_t = AUM-weighted fraction of eligible managers HOT that day.
  Deliverables: the full daily series (CSV), the top-1% episode dates
  (should land on known crises with no date labels in the fit), the
  correlation with FORWARD 10d realized market vol (risk conditioner
  validation, not alpha), and the honest conditioner test: combo-proxy
  daily PnL at constant gross vs gross halved when AggStress is above
  its own expanding 80th percentile - report Sharpe and maxDD both.

MONITOR 3 - cover timing for the short leg:
  exhaustion rule per shorted name (declared ex-ante): after day 10 of
  the window, first day with past-5d excess return > 0 AND 5d dollar
  volume below its 63d ADV (supply no longer pressing). Compare holding
  the short full-window vs covering at exhaustion: price PnL difference
  + borrow saved (engine daily borrow) - the claim is COST reduction,
  not alpha, so the bar is "does not lose money and saves borrow".

Combo books rebuilt inline per quarter at the decision date (PIT):
  LONG  = top-50 names by residualized new_conviction rank (champion
          core; copycat filter omitted - membership overlap is high and
          the monitor tests do not depend on it);
  SHORT = top-50 names by distress fire-sale supply (when >= 15
          distressed managers exist that quarter).
ETF instruments removed everywhere (audited flag list).
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
from backtest_gp import nw_tstat                    # noqa: E402
from run_all import load_market, log                # noqa: E402
from run_fire import implied_flows                  # noqa: E402

RESULTS = HERE / "results"
ETF_FLAGS = HERE.parent / "ETF_strat" / "data" / "etf_universe_flags.csv"
DEC_LAG = 50
STRESS_CUT = 2.0
NBOOK = 50
DISTRESS_FLOW = -0.10


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


def split_factor(cur, prev):
    pair = cur.merge(prev, on=["filer_id", "instrument_id"],
                     suffixes=("_c", "_p"))
    pair = pair[(pair["shares_p"] > 0) & (pair["shares_c"] > 0)]
    pair["ratio"] = (pair["shares_c"] / pair["shares_p"]).round(3)
    fac = {}
    for j, g in pair.groupby("instrument_id"):
        if len(g) < 10:
            continue
        counts = g["ratio"].value_counts()
        mode, k = counts.index[0], counts.iloc[0]
        k2 = counts.iloc[1] if len(counts) > 1 else 0
        if abs(mode - 1) > 0.15 and (k >= 0.10 * len(g)
                                     or (k >= 30 and k >= 2.5 * k2)):
            fac[j] = float(mode)
    return pd.Series(fac, dtype=float)


def main(smoke: bool = False) -> None:
    RESULTS.mkdir(exist_ok=True)
    cmap, mdta = load_market()
    dates = mdta.prices.index
    rets = mdta.returns
    bench = mdta.benchmark_returns.reindex(dates).fillna(0.0)
    ex = rets.sub(bench, axis=0)
    adv = mdta.dollar_volume.rolling(63, min_periods=20).median()
    dvol = mdta.dollar_volume
    vol_d = mdta.volatility / np.sqrt(252.0)
    shares = mc.shares_panel(dates, mdta.tickers, mdta.prices, mdta.prices_raw)
    mcap = mc.mktcap_panel(mdta.prices_raw, shares)
    cmap_s = pd.Series(cmap)
    etf = pd.read_csv(ETF_FLAGS, usecols=["instrument_id", "is_etf"])
    etf_set = set(etf.loc[etf["is_etf"] == True, "instrument_id"])  # noqa: E712
    dbr = mdta.daily_borrow_rate

    qs = [q for q in pn.quarters()
          if pd.Timestamp("2013-06-30") <= q <= dates[-1] - pd.Timedelta(days=140)]
    if smoke:
        qs = qs[-12:]
    log(f"{len(qs)} quarters")

    m1_long, m1_squeeze, m3_rows = [], [], []
    agg_series = []          # (date, AggStress, combo_ret)

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
        di = dates.searchsorted(dec, side="right") - 1
        di_p = dates.searchsorted(q, side="right") - 1
        di_p1 = dates.searchsorted(q1, side="right") - 1
        adv_d = adv.iloc[di]
        mc_d = mcap.iloc[di]

        def to_pairs(df):
            d = df[["filer_id", "instrument_id", "shares", "value_usd"]].copy()
            d["ticker"] = d["instrument_id"].map(cmap)
            d = d.dropna(subset=["ticker"])
            return d.groupby(["filer_id", "ticker"], as_index=False).agg(
                value=("value_usd", "sum"), sh=("shares", "sum"))

        pc, pp = to_pairs(cur), to_pairs(prev)

        # ---- combo books at dec (PIT) ------------------------------------ #
        fac_i = split_factor(cur, prev)
        fac_t = (pd.DataFrame({"t": cmap_s.reindex(fac_i.index),
                               "f": fac_i.values})
                 .dropna().groupby("t")["f"].first())
        pc_w = pc.copy()
        book = pc_w.groupby("filer_id")["value"].transform("sum")
        pc_w["w"] = pc_w["value"] / book.replace(0, np.nan)
        thr = pc_w.groupby("filer_id")["w"].transform(
            lambda s: s.quantile(0.9))
        m5 = pc_w.merge(pp[["filer_id", "ticker", "sh"]],
                        on=["filer_id", "ticker"], how="left",
                        suffixes=("", "_p"))
        m5["sh_p_adj"] = m5["sh_p"].fillna(0.0) \
            * m5["ticker"].map(fac_t).fillna(1.0)
        grew = m5["sh_p"].isna() | (m5["sh"] >= 1.25 * m5["sh_p_adj"])
        top = m5[(m5["w"] >= thr.values) & grew]
        n_filers = float(cur["filer_id"].nunique())
        nc = (top.groupby("ticker")["filer_id"].nunique() / n_filers)
        uni = nc.index[pd.Series(nc.index.map(
            mdta.prices_raw.iloc[di]), index=nc.index) >= 1.0]
        nc = nc.reindex(uni)
        ctrl = pd.DataFrame({
            "lm": np.log(pd.Series(uni.map(mc_d), index=uni)),
            "la": np.log(pd.Series(uni.map(adv_d), index=uni))})
        ncr = residualise(nc.rank(pct=True), ctrl).rank(pct=True).dropna()
        longs = list(ncr.nlargest(NBOOK).index)

        ret_q = (mdta.prices.iloc[di_p] / mdta.prices.iloc[di_p1] - 1.0)
        fl = implied_flows(cur, prev, cmap, ret_q.fillna(0.0))
        shorts = []
        distressed = fl.index[fl["flow"] < DISTRESS_FLOW] if len(fl) else []
        if len(distressed) >= 15:
            s = pc[pc["filer_id"].isin(distressed)].copy()
            s["advj"] = s["ticker"].map(adv_d)
            s = s.dropna(subset=["advj"])
            s["peck"] = s.groupby("filer_id")["advj"].rank(pct=True)
            fmag = fl["flow"].abs().reindex(s["filer_id"]).values
            aumc = fl["aum_cur"].reindex(s["filer_id"]).values
            s["sup"] = fmag * aumc * (s["value"] / s.groupby("filer_id")
                                      ["value"].transform("sum")) * s["peck"]
            sup = (s.groupby("ticker")["sup"].sum()
                   / adv_d.reindex(s.groupby("ticker")["sup"].sum().index))
            sup = sup.replace([np.inf, -np.inf], np.nan).dropna()
            shorts = list(sup.nlargest(NBOOK).index)

        # ---- eligibility + matrices (stress machine, final spec) --------- #
        d = pc.copy()
        cover = (d.groupby("filer_id")["value"].sum()
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
        if len(elig) < 150 or not longs:
            continue
        db = d[d["filer_id"].isin(elig)]
        V = db.pivot_table(index="filer_id", columns="ticker",
                           values="value", aggfunc="sum").fillna(0.0)
        T = [t for t in V.columns if t in rets.columns]
        V = V[T]
        Vv = V.values
        Wn = Vv / Vv.sum(axis=1, keepdims=True)
        aum_v = aum.reindex(V.index).values
        d0 = dates.searchsorted(dec, side="right")
        d1 = dates.searchsorted(dec2, side="right") - 1
        if d1 - d0 < 20 or d1 + 7 >= len(dates):
            continue
        R = rets[T].iloc[d0:d1].fillna(0.0).values
        E = ex[T].iloc[d0:d1].fillna(0.0).values
        B = bench.iloc[d0:d1].values
        sig = vol_d[T].iloc[d0].fillna(0.02).values
        Dw = R.shape[0]
        cumrel = np.cumprod(1.0 + R, axis=0)
        S = Wn @ cumrel.T
        book_ret = np.diff(np.column_stack([np.ones(len(S)), S]), axis=1) \
            / np.column_stack([np.ones(len(S)), S])[:, :-1]
        resid_b = book_ret - B[None, :]
        nav = np.cumprod(1.0 + resid_b, axis=1)
        dd = nav / np.maximum.accumulate(nav, axis=1) - 1.0

        Tpos = {t: j for j, t in enumerate(T)}
        long_in = [t for t in longs if t in Tpos]
        long_j = [Tpos[t] for t in long_in]
        ex_l = ex[long_in].iloc[d0:d1 + 6]
        ex_s = ex[[t for t in shorts if t in ex.columns]].iloc[d0:d1 + 6] \
            if shorts else None
        adv_s = adv_d.reindex(shorts) if shorts else None
        cum_ex_win = ex.iloc[d0 - 6:d1 + 6]

        covered_day: dict = {}
        for t in range(5, Dw - 1):
            pain = Wn @ (E[t] < -sig).astype(float)
            z1 = -(dd[:, t] - dd[:, t].mean()) / (dd[:, t].std() + 1e-12)
            z2 = (pain - pain.mean()) / (pain.std() + 1e-12)
            stress = z1 + z2
            hot = stress > STRESS_CUT
            gd = d0 + t
            agg = float(aum_v[hot].sum() / aum_v.sum())

            # combo proxy daily return (next day, books fixed in window)
            r_l = float(ex.iloc[gd + 1].reindex(long_in).mean()) \
                if long_in else 0.0
            r_s = float(ex.iloc[gd + 1].reindex(shorts).mean()) \
                if shorts else 0.0
            combo_r = 0.5 * r_l - 0.5 * r_s if shorts else r_l
            agg_series.append((dates[gd], agg, combo_r))

            # ---- M1a: hot-ownership risk within the LONG book ------------- #
            if hot.any() and long_j and (t % 5 == 0) and gd + 6 < len(dates):
                risk = Vv[hot][:, long_j].sum(axis=0) \
                    / np.maximum(adv_d.reindex(long_in).values, 1.0)
                rs = pd.Series(risk, index=long_in)
                f5 = (ex.iloc[gd + 1:gd + 6].reindex(
                    columns=long_in).sum())
                hi = rs >= rs.quantile(2 / 3)
                lo = rs <= rs.quantile(1 / 3)
                if hi.sum() >= 5 and lo.sum() >= 5:
                    m1_long.append({
                        "period": q,
                        "d_hi_lo": float(f5[hi].mean() - f5[lo].mean())})

            # ---- M1b: squeeze alarm on the SHORT book -------------------- #
            if shorts and (t >= 5) and gd + 6 < len(dates):
                past5 = ex.iloc[gd - 4:gd + 1].reindex(
                    columns=shorts).sum()
                v5 = dvol.iloc[gd - 4:gd + 1].reindex(
                    columns=shorts).mean()
                alarm = (past5 > 0.07) & (v5 > 2.0 * adv_s)
                calm_ = (past5 < 0.03)
                if alarm.sum() >= 3 and calm_.sum() >= 5:
                    f5 = ex.iloc[gd + 1:gd + 6].reindex(
                        columns=shorts).sum()
                    m1_squeeze.append({
                        "period": q,
                        "alarmed": float(f5[alarm].mean()),
                        "calm": float(f5[calm_].mean())})

            # ---- M3: cover-timing exhaustion ----------------------------- #
            if shorts and t >= 10:
                past5 = ex.iloc[gd - 4:gd + 1].reindex(columns=shorts).sum()
                v5 = dvol.iloc[gd - 4:gd + 1].reindex(columns=shorts).mean()
                for tt in shorts:
                    if tt in covered_day:
                        continue
                    if past5.get(tt, -1) > 0 and \
                            v5.get(tt, 9e18) < adv_s.get(tt, 0):
                        covered_day[tt] = gd

        # ---- M3 accounting: full-hold vs cover-at-exhaustion -------------- #
        if shorts:
            full = -ex.iloc[d0 + 1:d1 + 1].reindex(columns=shorts).sum()
            timed = {}
            bor_saved = {}
            for tt in shorts:
                cd = covered_day.get(tt)
                if cd is None:
                    timed[tt] = full.get(tt, np.nan)
                    bor_saved[tt] = 0.0
                else:
                    timed[tt] = -float(ex.iloc[d0 + 1:cd + 1]
                                       .get(tt, pd.Series()).sum())
                    nd = (d1 - cd)
                    br = float(dbr[tt].iloc[cd]) if tt in dbr.columns else 0.0
                    bor_saved[tt] = br * nd
            timed = pd.Series(timed)
            bs_ = pd.Series(bor_saved)
            m3_rows.append({
                "period": q,
                "full": float(full.mean()),
                "timed": float(timed.mean()),
                "borrow_saved": float(bs_.mean()),
                "frac_covered": float(len(covered_day) / len(shorts))})
        log(f"{q.date()}: longs {len(long_in)}, shorts {len(shorts)}, "
            f"elig {len(elig)}")

    # ---- aggregate & report ------------------------------------------------ #
    ags = pd.DataFrame(agg_series, columns=["date", "agg", "combo"]) \
        .drop_duplicates("date").set_index("date").sort_index()
    ags.to_csv(RESULTS / "agg_stress_daily.csv")

    L = ["# daily_monitor - os tres monitores da varredura", "",
         "Spec de stress: v1 final (z(-DD)+z(PainBreadth), corte absoluto "
         "2.0, defendida por ablacao). Books do combo reconstruidos PIT "
         "por trimestre (long top-50 new_conv resid; short top-50 distress "
         "supply).", ""]

    if m1_long:
        e = pd.DataFrame(m1_long).groupby("period")["d_hi_lo"].mean()
        L += ["## M1a - longs do combo detidos por gestores HOT", "",
              f"- delta 5d (tercil alto - baixo de hot-ownership/ADV): "
              f"{e.mean():+.4f} (t={nw_tstat(e):+.2f}, {len(e)} tri) - "
              f"negativo = o monitor identifica longs em risco", ""]
    if m1_squeeze:
        e = pd.DataFrame(m1_squeeze)
        qd = e.groupby("period").apply(
            lambda g: g["alarmed"].mean() - g["calm"].mean())
        L += ["## M1b - alarme de squeeze nos shorts", "",
              f"- pos-alarme 5d: alarmados {e['alarmed'].mean():+.4f} vs "
              f"calmos {e['calm'].mean():+.4f} (delta t="
              f"{nw_tstat(qd):+.2f}, {e['period'].nunique()} tri) - "
              f"positivo nos alarmados = cobrir no alarme e a acao", ""]

    if len(ags):
        mvol = bench.rolling(10).std() * np.sqrt(252)
        fwd_vol = mvol.shift(-10).reindex(ags.index)
        fwd_ret = bench.rolling(10).sum().shift(-10).reindex(ags.index)
        c_vol = float(ags["agg"].corr(fwd_vol))
        c_ret = float(ags["agg"].corr(fwd_ret))
        top_days = ags["agg"].nlargest(int(len(ags) * 0.01))
        episodes = top_days.groupby(top_days.index.to_period("Q")).count() \
            .sort_values(ascending=False)
        # conditioner: halve gross when agg above expanding p80
        thr_ = ags["agg"].expanding(120).quantile(0.80).shift(1)
        w_ = np.where(ags["agg"].shift(1) > thr_, 0.5, 1.0)
        base = ags["combo"]
        cond = base * w_

        def stats(s):
            sh = s.mean() / (s.std() + 1e-12) * np.sqrt(252)
            nav_ = (1 + s.fillna(0)).cumprod()
            mdd = float((nav_ / nav_.cummax() - 1).min())
            return sh, mdd

        sb, mb = stats(base)
        sc, mc_ = stats(cond)
        L += ["## M2 - indice diario de deleveraging (AggStress)", "",
              f"- {len(ags)} dias | corr(AggStress, vol de mercado 10d "
              f"FUTURA) = {c_vol:+.2f} | corr com retorno 10d futuro = "
              f"{c_ret:+.2f}",
              "- episodios no top-1% do indice (trimestres com mais dias): "
              + ", ".join(f"{k} ({v}d)" for k, v in
                          episodes.head(6).items()),
              f"- conditioner no combo-proxy: base Sharpe {sb:+.2f} / "
              f"maxDD {mb:.1%}  ->  gross 50% acima do p80 expanding: "
              f"Sharpe {sc:+.2f} / maxDD {mc_:.1%}", ""]

    if m3_rows:
        e = pd.DataFrame(m3_rows)
        dlt = e["timed"] - e["full"]
        L += ["## M3 - cover na exaustao vs segurar o short o tri inteiro",
              "",
              f"- PnL short: full {e['full'].mean():+.4f}/tri vs timed "
              f"{e['timed'].mean():+.4f}/tri (delta {dlt.mean():+.4f}, "
              f"t={nw_tstat(dlt):+.2f})",
              f"- borrow poupado: {e['borrow_saved'].mean() * 100:+.2f}%"
              f"/tri | fracao coberta antes do fim: "
              f"{e['frac_covered'].mean():.0%}",
              f"- barra do monitor: nao perder PnL (delta >= 0 apos "
              f"somar borrow) - e reducao de custo, nao alpha"]
    (RESULTS / "MONITOR_REPORT.md").write_text("\n".join(L),
                                               encoding="utf-8")
    log("done -> results/")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    main(**vars(ap.parse_args()))
