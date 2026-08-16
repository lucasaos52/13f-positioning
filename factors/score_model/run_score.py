"""Unified expected-return score model: classical characteristics + 13F
positioning signals combined into E[r] per stock, three combining schools
raced under identical rules.

    python run_score.py            # full sample
    python run_score.py --smoke    # shorter panel (fewer eval quarters)

This is the production alpha-model question, not a diagnostic: to build the
portfolio tomorrow one needs ONE ranking that merges every surviving signal
with the classical characteristics. Predictor list PRE-REGISTERED here
(no additions after seeing results):

  classical (from manager_factor_positioning.build_X, same z conventions):
      size(+=small), mom, beta, lowvol(+=defensive), strev, liq(+=liquid)
  13F survivors:
      new_conv  (residual on log mktcap + log ADV - theorem signal)
      dbreadth  (common filers)
      distress  (fire-sale supply, negative expected)
      pressure  (implied-flow demand / ADV)

All predictors enter as cross-sectional percentile ranks centered at zero
(uniform scale; heavy tails neutralised - same reason the whole project
uses rank/Spearman machinery).

The three combiners, all STRICTLY out-of-sample (expanding, min 12 quarters
of history before the first traded quarter; a quarter's own forward return
is only usable once realised, i.e. lambda_s and IC_s enter at decision t
only for s < t):

  A  FM/Lewellen: lambda_s from cross-sectional OLS of r[s->s+1] on X_s;
     E[r] = mean(lambda_(<t))' x_t.  Estimates premia jointly - handles
     signal correlation, pays estimation noise.
  B  IC-weighted composite (Grinold-Kahn school): w_k = mean IC_k,(<t);
     E[r] = sum_k w_k rank(x_k). Univariate weights - robust, ignores
     overlap between signals.
  C  Naive rank-average of new_conv + distress(-) - the current combo's
     combining rule, as baseline.

Deliverables: (1) the horse race A vs B vs C on identical quarters
(spread, IC, paired deltas); (2) the JOINT MARGINALITY table - full-sample
mean lambda with NW t per predictor: "does new_conv still carry premium
holding all six classical characteristics simultaneously?" - the answer
the FF6 ladder (portfolio-level, one-at-a-time) cannot give.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sps

HERE = Path(__file__).resolve().parent
for sub in ("", "general_plan", "fire_calendar", "manager_factor_positioning"):
    sys.path.insert(0, str(HERE.parent / sub))

import market_cap as mc                             # noqa: E402
import panel as pn                                  # noqa: E402
from backtest_gp import forward_return, nw_tstat    # noqa: E402
from run_all import load_market, log                # noqa: E402
from run_fire import implied_flows                  # noqa: E402
from run_mfp import build_X                         # noqa: E402

RESULTS = HERE / "results"
LAG = 45
MIN_HIST = 12
DISTRESS_FLOW = -0.10
CLASSICAL = ["size", "mom", "beta", "lowvol", "strev", "liq"]
SIGNALS = ["new_conv", "dbreadth", "distress", "pressure"]
PREDICTORS = CLASSICAL + SIGNALS


def residualise(y: pd.Series, X: pd.DataFrame) -> pd.Series:
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


def build_panels(smoke: bool = False) -> list[tuple]:
    """(period, X centered pct-ranks over PREDICTORS, fwd return) per
    quarter - shared by the combiner race below and by run_ipca.py."""
    cmap, mdta = load_market()
    dates = mdta.prices.index
    cum = mdta.returns.cumsum()
    adv = mdta.dollar_volume.rolling(63, min_periods=20).median()
    shares = mc.shares_panel(dates, mdta.tickers, mdta.prices, mdta.prices_raw)
    mcap = mc.mktcap_panel(mdta.prices_raw, shares)
    cmap_s = pd.Series(cmap)

    qs = [q for q in pn.quarters()
          if pd.Timestamp("2013-06-30") <= q <= dates[-1] - pd.Timedelta(days=120)]
    if smoke:
        qs = qs[-(10 + MIN_HIST):]
    log(f"{len(qs)} quarters, predictors: {PREDICTORS}")

    panels: list[tuple] = []       # (period, X ranks, fwd)
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

        Xz, _bench, _bw, _n = build_X(di_p, mdta, adv, mcap)

        fac_i = split_factor(cur, prev)
        fac_t = (pd.DataFrame({"t": cmap_s.reindex(fac_i.index),
                               "f": fac_i.values})
                 .dropna().groupby("t")["f"].first())

        def to_pairs(df):
            d = df[["filer_id", "instrument_id", "shares", "value_usd"]].copy()
            d["ticker"] = d["instrument_id"].map(cmap)
            d = d.dropna(subset=["ticker"])
            return d.groupby(["filer_id", "ticker"], as_index=False).agg(
                value=("value_usd", "sum"), sh=("shares", "sum"))

        pc, pp = to_pairs(cur), to_pairs(prev)
        n_c = pc.groupby("ticker")["filer_id"].nunique()
        n_p = pp.groupby("ticker")["filer_id"].nunique()
        idx = n_c.index.union(n_p.index)
        n_filers = float(cur["filer_id"].nunique())
        sig = pd.DataFrame(index=idx)

        common = np.intersect1d(pc["filer_id"].unique(), pp["filer_id"].unique())
        cc = pc[pc["filer_id"].isin(common)].groupby("ticker")["filer_id"].nunique()
        pcm = pp[pp["filer_id"].isin(common)].groupby("ticker")["filer_id"].nunique()
        sig["dbreadth"] = (cc.reindex(idx).fillna(0)
                           - pcm.reindex(idx).fillna(0)) / len(common)

        pc_w = pc.copy()
        book = pc_w.groupby("filer_id")["value"].transform("sum")
        pc_w["w"] = pc_w["value"] / book.replace(0, np.nan)
        thr = pc_w.groupby("filer_id")["w"].transform(lambda s: s.quantile(0.9))
        m5 = pc_w.merge(pp[["filer_id", "ticker", "sh"]],
                        on=["filer_id", "ticker"], how="left",
                        suffixes=("", "_p"))
        m5["sh_p_adj"] = m5["sh_p"].fillna(0.0) \
            * m5["ticker"].map(fac_t).fillna(1.0)
        grew = m5["sh_p"].isna() | (m5["sh"] >= 1.25 * m5["sh_p_adj"])
        top = m5[(m5["w"] >= thr.values) & grew]
        sig["new_conv"] = (top.groupby("ticker")["filer_id"].nunique()
                           .reindex(idx).fillna(0) / n_filers)

        fl = implied_flows(cur, prev, cmap, ret_q)
        adv_i = pd.Series(idx.map(adv_d), index=idx)
        pair = pc.merge(pp, on=["filer_id", "ticker"], how="outer",
                        suffixes=("_c", "_p"))
        rows_p = pair[pair["value_p"].notna()].copy()
        f_row = rows_p["filer_id"].map(fl["flow"]) if len(fl) else pd.Series(
            np.nan, index=rows_p.index)
        rows_p = rows_p[f_row.notna()]
        rows_p["press"] = f_row.loc[rows_p.index] * rows_p["value_p"]
        sig["pressure"] = (rows_p.groupby("ticker")["press"].sum()
                           .reindex(idx).fillna(0.0) / adv_i) \
            .replace([np.inf, -np.inf], np.nan)

        distressed = fl.index[fl["flow"] < DISTRESS_FLOW] if len(fl) else []
        if len(distressed) >= 10:
            s = pc[pc["filer_id"].isin(distressed)].copy()
            s["advj"] = s["ticker"].map(adv_d)
            s = s.dropna(subset=["advj"])
            s["peck"] = s.groupby("filer_id")["advj"].rank(pct=True)
            fmag = fl["flow"].abs().reindex(s["filer_id"]).values
            aumc = fl["aum_cur"].reindex(s["filer_id"]).values
            s["sup"] = fmag * aumc * (s["value"] / s.groupby("filer_id")
                                      ["value"].transform("sum")) * s["peck"]
            sup = s.groupby("ticker")["sup"].sum()
            sig["distress"] = (sup.reindex(idx).fillna(0.0) / adv_i) \
                .replace([np.inf, -np.inf], np.nan)
        else:
            sig["distress"] = 0.0

        n_max = pd.concat([n_c.reindex(idx), n_p.reindex(idx)],
                          axis=1).max(axis=1).fillna(0)
        uni = idx[(pd.Series(idx.map(px), index=idx) >= 1.0) & (n_max >= 5)]
        uni = uni.intersection(Xz.index)
        if len(uni) < 500:
            continue

        # new_conv theorem residual, then everything to centered pct ranks
        ctrl = pd.DataFrame({
            "lm": np.log(pd.Series(uni.map(mc_d), index=uni)),
            "la": np.log(pd.Series(uni.map(adv_d), index=uni))})
        nc = residualise(sig["new_conv"].reindex(uni).rank(pct=True), ctrl)

        X = pd.DataFrame(index=uni)
        for k in CLASSICAL:
            X[k] = Xz[k].reindex(uni)
        X["new_conv"] = nc
        X["dbreadth"] = sig["dbreadth"].reindex(uni)
        X["distress"] = sig["distress"].reindex(uni)
        X["pressure"] = sig["pressure"].reindex(uni)
        X = X.rank(pct=True) - 0.5          # uniform scale, centered

        nxt = qs[qi + 1] + pd.Timedelta(days=LAG) if qi + 1 < len(qs) \
            else dates[-1]
        fwd = forward_return(cum, dates, dec, min(nxt, dates[-1])).reindex(uni)
        panels.append((p, X, fwd))
        log(f"{p.date()}: panel {len(uni)} names")
    return panels


def main(smoke: bool = False) -> None:
    RESULTS.mkdir(exist_ok=True)
    panels = build_panels(smoke)

    # ---- lambdas and ICs per quarter -------------------------------------- #
    lambdas, ics = [], []
    for p, X, fwd in panels:
        df = pd.concat([X, fwd.rename("f")], axis=1).dropna()
        A = np.column_stack([np.ones(len(df)), df[PREDICTORS].values])
        lam, *_ = np.linalg.lstsq(A, df["f"].values, rcond=None)
        lambdas.append(pd.Series(lam[1:], index=PREDICTORS, name=p))
        ics.append(pd.Series(
            {k: sps.spearmanr(df[k], df["f"])[0] for k in PREDICTORS},
            name=p))
    LAM = pd.DataFrame(lambdas)
    ICS = pd.DataFrame(ics)
    LAM.to_csv(RESULTS / "lambdas.csv")

    # ---- horse race, strictly expanding ----------------------------------- #
    ev = []
    rngseed = 7
    for ti in range(MIN_HIST, len(panels)):
        p, X, fwd = panels[ti]
        lam_bar = LAM.iloc[:ti].mean()
        ic_bar = ICS.iloc[:ti].mean()
        er_A = (X[PREDICTORS] * lam_bar).sum(axis=1)
        er_B = (X[PREDICTORS] * ic_bar).sum(axis=1)
        er_C = X["new_conv"].rank(pct=True) \
            + (-X["distress"]).rank(pct=True)
        rng = np.random.default_rng(int(p.value) % (2**32) + rngseed)

        def spread_ic(s):
            df = pd.concat([s.rename("s"), fwd.rename("f")], axis=1).dropna()
            if len(df) < 150:
                return np.nan, np.nan
            jit = pd.Series(rng.uniform(0, 1e-9, len(df)), index=df.index)
            q5 = pd.qcut((df["s"] + jit).rank(), 5, labels=False)
            g = df.groupby(q5)["f"].mean()
            return (g.get(4, np.nan) - g.get(0, np.nan),
                    sps.spearmanr(df["s"], df["f"])[0])

        row = {"period": p}
        for nm, er in [("A_fm", er_A), ("B_ic", er_B), ("C_naive", er_C)]:
            row[f"spread_{nm}"], row[f"ic_{nm}"] = spread_ic(er)
        ev.append(row)
    E = pd.DataFrame(ev)
    E.to_csv(RESULTS / "race_events.csv", index=False)

    # ---- report ------------------------------------------------------------ #
    L = ["# score_model - E[r] unificado: classicos + posicionamento 13F", "",
         f"- {len(panels)} tri no painel, {len(E)} tri avaliados OOS "
         f"(apos {MIN_HIST} tri de warm-up de lambda/IC)", "",
         "## Marginalidade conjunta (lambda medio full-sample, NW t)", "",
         "A pergunta que a escada FF6 nao responde: o preditor carrega "
         "premio segurando TODOS os outros simultaneamente?", ""]
    tab = pd.DataFrame({
        "lambda_medio": LAM.mean(),
        "t_NW": [nw_tstat(LAM[k]) for k in PREDICTORS],
        "IC_medio": ICS.mean(),
        "t_IC": [nw_tstat(ICS[k]) for k in PREDICTORS]}).round(4)
    L += [tab.to_markdown(), ""]
    L += ["## Corrida dos combinadores (OOS estrito, mesma amostra)", ""]
    for nm, lbl in [("A_fm", "A Fama-MacBeth/Lewellen"),
                    ("B_ic", "B IC-weighted (Grinold-Kahn)"),
                    ("C_naive", "C rank-average new_conv+distress")]:
        sp, ic = E[f"spread_{nm}"], E[f"ic_{nm}"]
        L.append(f"- **{lbl}**: spread {sp.mean():+.4f}/tri "
                 f"(t={nw_tstat(sp):+.2f}), Sharpe "
                 f"{sp.mean() / sp.std() * 2:+.2f}, IC {ic.mean():+.4f}")
    for a, b in [("A_fm", "B_ic"), ("A_fm", "C_naive"), ("B_ic", "C_naive")]:
        d = (E[f"spread_{a}"] - E[f"spread_{b}"]).dropna()
        L.append(f"- delta {a} vs {b}: {d.mean():+.4f}/tri "
                 f"(t={nw_tstat(d):+.2f})")
    (RESULTS / "SCORE_REPORT.md").write_text("\n".join(L), encoding="utf-8")
    log("done -> results/")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    main(**vars(ap.parse_args()))
