"""Manager factor decomposition E_t = W_t X_t and the layers on top.

    python run_mfp.py           # full sample
    python run_mfp.py --smoke   # last ~14 quarters

Implements E1-E5 of README.md under the project's standard clock (decision at
p+45d, event-driven PIT snapshots; only filings public by the decision date).

Design choices that will be asked about in review:

- X_t are CHARACTERISTIC z-scores (doc §2.1), not return betas: winsorized
  1%/99%, cross-sectionally standardized over the eligible universe at the
  quarter-end trading day. Signs: size = -z(log ME) (positive = small tilt),
  lowvol = -z(vol126) (positive = defensive), mom = z(r[-12m,-1m]),
  strev = z(r[-1m]) (positive = recent winner), beta = z(beta252),
  liq = z(log ADV63) (positive = liquid).
- Exposures are ACTIVE vs the value-weighted eligible universe (doc §5):
  E_active[m,k] = sum_i (w_mi - b_i) z_ik. Without this, "managers are long
  large liquid stocks" would read as a style bet when it is mechanics.
- Weights w from reported quarter-end values (the E^QE flavour of doc §15),
  materialised at the decision date. One clock, same as every other module.
- Manager filter: >= 15 positions, book >= $100M, factor coverage >= 80% of
  book value. No skill selection anywhere (project evidence).
- Rotation (doc §9): exact 3-way split. E_old = w_prev X_prev;
  E_price = wdrift X_prev; E_char = wdrift X_cur; E_actual = w_cur X_cur.
  price drift = E_price - E_old, char drift = E_char - E_price,
  ACTIVE ROTATION = E_actual - E_char. All components REPORTED, none
  residualized away (the DFR lesson).
- Pressure (doc §10): AUM-weighted rotation over the factor basket capacity
  sum_i |z_ik| ADV_i. Funding flow (doc §11): f_m from the validated
  implied-flow instrument times the manager's PREVIOUS exposure, same
  denominator. Kept separate from observed rotation (no double counting).
- Factor return for the tests: next-quarter return of the z-weighted
  basket r_k = sum_i z_ik fwd_i / sum_i |z_ik| - internally consistent with
  the X that defines the exposure (KF factors differ by universe/weighting).
- Crowding state: EXPANDING z of AUM-weighted aggregate position (min 8
  quarters) - no look-ahead in the interaction test.
- Mismatch (doc §14, momentum only): pref_m = trailing 8q mean of the
  manager's own E_active[mom] (strictly past, >= 4 obs);
  OwnerPref_i = value-weighted pref of current holders;
  Mismatch_i = OwnerPref_i * -(z_mom,t - z_mom,t-1). Mechanism FIRST:
  IC(Mismatch_t, dIO_{t+1}) must be negative (owners sell what no longer
  matches their style) before the return sort means anything.

Outputs in results/: manager_factor_exposure.parquet (the permanent panel),
dashboard.csv, MFP_REPORT.md.
"""
from __future__ import annotations

import argparse
import sys
from collections import deque
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sps

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
FACTORS = ["size", "mom", "beta", "lowvol", "strev", "liq"]
MIN_POS = 15
MIN_AUM = 1e8
MIN_COVER = 0.80
BREADTH_C = 0.5          # doc §7.2 threshold on active z
PREF_TRAIL = 8           # quarters for the persistent style preference
PREF_MIN = 4
CROWD_MIN = 8            # expanding-z warmup for crowding state


def winz(s: pd.Series) -> pd.Series:
    lo, hi = s.quantile(0.01), s.quantile(0.99)
    z = s.clip(lo, hi)
    return (z - z.mean()) / z.std()


def build_X(di_p: int, mdta, adv, mcap) -> pd.DataFrame:
    """Stock-factor z-score matrix at one quarter-end trading day."""
    px_raw = mdta.prices_raw.iloc[di_p]
    prices = mdta.prices
    mcap_d = mcap.iloc[di_p]
    adv_d = adv.iloc[di_p]
    n = len(prices)

    def safe(i):
        return prices.iloc[max(i, 0)]

    mom = safe(di_p - 21) / safe(di_p - 252) - 1.0
    strev = prices.iloc[di_p] / safe(di_p - 21) - 1.0
    w0 = max(di_p - 252, 0)
    R = mdta.returns.iloc[w0:di_p]
    b = mdta.benchmark_returns.reindex(R.index).fillna(0.0)
    bv = b.var()
    beta = R.apply(lambda c: c.cov(b)) / bv if bv > 0 else pd.Series(
        np.nan, index=R.columns)
    vol = mdta.returns.iloc[max(di_p - 126, 0):di_p].std()

    X = pd.DataFrame({
        "size": -winz(np.log(mcap_d.replace(0, np.nan))),
        "mom": winz(mom),
        "beta": winz(beta),
        "lowvol": -winz(vol),
        "strev": winz(strev),
        "liq": winz(np.log(adv_d.replace(0, np.nan))),
    })
    uni = X.index[(px_raw.reindex(X.index) >= 1.0)
                  & mcap_d.reindex(X.index).notna()
                  & adv_d.reindex(X.index).gt(0)]
    X = X.loc[uni].dropna(thresh=4)
    # value-weighted benchmark exposure of the eligible universe
    bw = mcap_d.reindex(X.index)
    bw = bw / bw.sum()
    bench = X.mul(bw, axis=0).sum()
    return X, bench, bw, n


def manager_E(pairs: pd.DataFrame, X: pd.DataFrame,
              bench: pd.Series) -> tuple[pd.DataFrame, pd.Series]:
    """E_active per manager from a (filer_id, ticker, value) table."""
    d = pairs.copy()
    tot = d.groupby("filer_id")["value"].transform("sum")
    d["w"] = d["value"] / tot.replace(0, np.nan)
    zc = X.reindex(d["ticker"]).reset_index(drop=True)
    d = pd.concat([d.reset_index(drop=True), zc], axis=1)
    cov = d.assign(ok=d[FACTORS].notna().any(axis=1).astype(float) * d["w"]) \
        .groupby("filer_id")["ok"].sum()
    E = pd.DataFrame({k: (d["w"] * d[k]).groupby(d["filer_id"]).sum()
                      / d.assign(m=d["w"] * d[k].notna())
                      .groupby("filer_id")["m"].sum()
                      for k in FACTORS})
    aum = pairs.groupby("filer_id")["value"].sum()
    npos = pairs.groupby("filer_id").size()
    keep = E.index[(aum.reindex(E.index) >= MIN_AUM)
                   & (npos.reindex(E.index) >= MIN_POS)
                   & (cov.reindex(E.index) >= MIN_COVER)]
    return (E.loc[keep] - bench, aum.reindex(keep))


def cluster_ols(y: np.ndarray, Xm: np.ndarray,
                clusters: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """OLS with one-way cluster-robust SEs (small helper, no statsmodels)."""
    A = np.column_stack([np.ones(len(Xm)), Xm])
    bhat, *_ = np.linalg.lstsq(A, y, rcond=None)
    u = y - A @ bhat
    XtX_inv = np.linalg.inv(A.T @ A)
    meat = np.zeros((A.shape[1], A.shape[1]))
    for c in np.unique(clusters):
        Ac, uc = A[clusters == c], u[clusters == c]
        s = Ac.T @ uc
        meat += np.outer(s, s)
    V = XtX_inv @ meat @ XtX_inv
    return bhat, np.sqrt(np.diag(V))


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
        qs = qs[-14:]
    log(f"{len(qs)} quarters, factors: {FACTORS}")

    # rolling state
    prev_pairs = prev_X = prev_E = prev_aum = None
    pref_hist: deque = deque(maxlen=PREF_TRAIL)
    pend_mismatch = None            # scored against NEXT quarter's dIO
    panel_rows, dash_rows, mech_rows, ret_events = [], [], [], []
    exposure_store = []
    placebo_P, real_P = [], []
    synth_checks = []

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
        adv_d = adv.iloc[di_p]
        mc_d = mcap.iloc[di]
        so_c = shares.iloc[di_p]
        ret_q = cum.iloc[di_p] - cum.iloc[di_p1]

        X, bench, bw, _ = build_X(di_p, mdta, adv, mcap)

        def to_pairs(df):
            d = df[["filer_id", "instrument_id", "shares", "value_usd"]].copy()
            d["ticker"] = d["instrument_id"].map(cmap)
            d = d.dropna(subset=["ticker"])
            return d.groupby(["filer_id", "ticker"], as_index=False).agg(
                value=("value_usd", "sum"), sh=("shares", "sum"))

        pc, pp = to_pairs(cur), to_pairs(prev)
        E_act, aum = manager_E(pc, X, bench)

        # ---- E1 store + E5 dashboard ------------------------------------- #
        st = E_act.copy()
        st["aum"], st["period"] = aum, p
        exposure_store.append(st.reset_index())
        a_w = aum / aum.sum()
        P_aum = E_act.mul(a_w, axis=0).sum()
        P_ew = E_act.mean()
        disp = E_act.std()
        breadth = E_act.gt(BREADTH_C).mul(a_w, axis=0).sum()
        Epos = E_act.clip(lower=0).mul(aum, axis=0)
        hhi_pos = (Epos / Epos.sum()).pow(2).sum()
        dash_rows.append(pd.DataFrame({
            "period": p, "factor": FACTORS,
            "P_aum": P_aum, "P_ew": P_ew, "dispersion": disp,
            "breadth_pos": breadth, "hhi_pos": hhi_pos}))
        real_P.append(P_aum.rename(p))

        # placebo (doc test 5): shuffle z within size quintiles -> the
        # aggregate positioning time-structure must collapse
        rng = np.random.default_rng(int(p.value) % (2**32))
        Xp = X.copy()
        sq = pd.qcut(-X["size"].rank(), 5, labels=False)
        for b_ in range(5):
            m_ = sq == b_
            Xp.loc[m_, "mom"] = rng.permutation(X.loc[m_, "mom"].values)
        Ep, _ = manager_E(pc, Xp, Xp.mul(bw.reindex(Xp.index).fillna(0),
                                         axis=0).sum())
        placebo_P.append(float(Ep["mom"].mul(
            a_w.reindex(Ep.index).fillna(0), axis=0).sum()))

        # synthetic known books (doc test 1) at 3 sample dates
        if qi in (5, len(qs) // 2, len(qs) - 2):
            topmom = X["mom"].nlargest(int(len(X) * 0.1)).index
            small = X["size"].nlargest(int(len(X) * 0.1)).index
            for nm, bk, k in [("top-decile momentum EW", topmom, "mom"),
                              ("small-cap decile EW", small, "size")]:
                fake = pd.DataFrame({"filer_id": 0, "ticker": list(bk),
                                     "value": 1.0, "sh": 1.0})
                Ef, _ = manager_E(fake.assign(value=1e7), X, bench)
                if len(Ef):
                    synth_checks.append({"period": p, "book": nm,
                                         "factor": k,
                                         "E": float(Ef[k].iloc[0])})

        # ---- E2 rotation decomposition ----------------------------------- #
        rot_agg = {}
        if prev_pairs is not None and prev_E is not None:
            r_i = (mdta.prices.iloc[di_p] / mdta.prices.iloc[di_p1] - 1.0)
            common = prev_E.index.intersection(E_act.index)
            pv = prev_pairs[prev_pairs["filer_id"].isin(common)].copy()
            pv["gross"] = pv["value"] * (1.0 + pv["ticker"].map(r_i).fillna(0.0))
            tot_g = pv.groupby("filer_id")["gross"].transform("sum")
            pv["wd"] = pv["gross"] / tot_g.replace(0, np.nan)

            def expo(tab, wcol, Z, bch):
                zz = Z.reindex(tab["ticker"]).reset_index(drop=True)
                t2 = pd.concat([tab[["filer_id", wcol]]
                                .reset_index(drop=True), zz], axis=1)
                return pd.DataFrame(
                    {k: (t2[wcol] * t2[k]).groupby(t2["filer_id"]).sum()
                     / t2.assign(m=t2[wcol] * t2[k].notna())
                     .groupby("filer_id")["m"].sum()
                     for k in FACTORS}) - bch

            bench_prev = prev_X.mul(
                mcap.iloc[di_p1].reindex(prev_X.index).fillna(0)
                / mcap.iloc[di_p1].reindex(prev_X.index).fillna(0).sum(),
                axis=0).sum()
            E_price = expo(pv, "wd", prev_X, bench_prev)
            E_char = expo(pv, "wd", X, bench)
            E_old = prev_E.loc[common]
            E_new = E_act.loc[common]
            drift_p = (E_price.reindex(common) - E_old)
            drift_c = (E_char.reindex(common) - E_price.reindex(common))
            rotation = (E_new - E_char.reindex(common))
            wA = prev_aum.reindex(common)
            wA = wA / wA.sum()
            for k in FACTORS:
                rot_agg[k] = {
                    "drift_price": float((drift_p[k] * wA).sum()),
                    "drift_char": float((drift_c[k] * wA).sum()),
                    "rotation": float((rotation[k] * wA).sum())}
            cap = (X.abs().mul(adv_d.reindex(X.index), axis=0)).sum()
            dollar_rot = rotation.mul(prev_aum.reindex(common), axis=0).sum()
            pressure = dollar_rot / cap.replace(0, np.nan)

            # ---- E3 funding-induced factor flow --------------------------- #
            fl = implied_flows(cur, prev, cmap, ret_q)
            ffl = fl["flow"].reindex(common).dropna()
            dollar_fund = prev_E.loc[ffl.index].mul(
                ffl * prev_aum.reindex(ffl.index), axis=0).sum()
            funding = dollar_fund / cap.replace(0, np.nan)

            # next-quarter z-weighted basket return per factor
            nxt = qs[qi + 1] + pd.Timedelta(days=LAG) if qi + 1 < len(qs) \
                else dates[-1]
            fwd = forward_return(cum, dates, dec, min(nxt, dates[-1]))
            fk = {}
            for k in FACTORS:
                z = X[k].dropna()
                f_ = fwd.reindex(z.index)
                ok = f_.notna()
                fk[k] = float((z[ok] * f_[ok]).sum() / z[ok].abs().sum())
            for k in FACTORS:
                panel_rows.append({
                    "period": p, "factor": k,
                    "pressure": float(pressure[k]),
                    "funding": float(funding[k]),
                    "P_aum": float(P_aum[k]),
                    "rot_agg": rot_agg[k]["rotation"],
                    "drift_price": rot_agg[k]["drift_price"],
                    "drift_char": rot_agg[k]["drift_char"],
                    "fwd_factor_ret": fk[k]})

        # ---- E4 mismatch (momentum): score pending, then build ----------- #
        # dIO per ticker this quarter (all-filers proxy for owner trading)
        mrg = pc.merge(pp, on=["filer_id", "ticker"], how="outer",
                       suffixes=("_c", "_p"))
        dsh = mrg["sh_c"].fillna(0.0) - mrg["sh_p"].fillna(0.0)
        dio = (dsh / mrg["ticker"].map(so_c)).replace(
            [np.inf, -np.inf], np.nan)
        dio_t = pd.DataFrame({"ticker": mrg["ticker"], "dio": dio}) \
            .groupby("ticker")["dio"].sum()
        if pend_mismatch is not None:
            comm = pend_mismatch.index.intersection(dio_t.index)
            if len(comm) > 300:
                mech_rows.append({
                    "period": p,
                    "ic_dio": sps.spearmanr(pend_mismatch.reindex(comm),
                                            dio_t.reindex(comm),
                                            nan_policy="omit")[0],
                    "n": len(comm)})
        pend_mismatch = None
        if len(pref_hist) >= PREF_MIN and prev_X is not None:
            Pref = pd.concat(list(pref_hist), axis=1)
            pref_m = Pref.mean(axis=1)[Pref.notna().sum(axis=1) >= PREF_MIN]
            hold = pc[pc["filer_id"].isin(pref_m.index)].copy()
            hold["pw"] = hold["filer_id"].map(pref_m) * hold["value"]
            g = hold.groupby("ticker")
            owner_pref = g["pw"].sum() / g["value"].sum()
            dz = (X["mom"] - prev_X["mom"]).dropna()
            mm = (owner_pref * (-dz)).dropna()
            pend_mismatch = mm
            # return test under the standard protocol (raw; expected NEGATIVE)
            nxt = qs[qi + 1] + pd.Timedelta(days=LAG) if qi + 1 < len(qs) \
                else dates[-1]
            fwd = forward_return(cum, dates, dec, min(nxt, dates[-1]))
            df = pd.concat([mm.rename("s"), fwd.rename("f")], axis=1).dropna()
            if len(df) >= 300:
                q5 = pd.qcut(df["s"].rank(method="first"), 5, labels=False)
                ew = df.groupby(q5)["f"].mean()
                ret_events.append({
                    "period": p,
                    "spread_ew": ew.get(4, np.nan) - ew.get(0, np.nan),
                    "ic": sps.spearmanr(df["s"], df["f"])[0],
                    "n": len(df)})
        pref_hist.append(E_act["mom"].rename(str(p.date())))

        prev_pairs, prev_X, prev_E, prev_aum = pc, X, E_act, aum
        log(f"{p.date()}: mgrs {len(E_act)}, X uni {len(X)}, "
            f"P_mom {P_aum['mom']:+.2f}")

    # ---- persist + aggregate ---------------------------------------------- #
    expo = pd.concat(exposure_store, ignore_index=True)
    expo.to_parquet(RESULTS / "manager_factor_exposure.parquet", index=False)
    dash = pd.concat(dash_rows, ignore_index=True)
    dash.to_csv(RESULTS / "dashboard.csv", index=False)
    pnl = pd.DataFrame(panel_rows)
    pnl.to_csv(RESULTS / "factor_flow_panel.csv", index=False)

    L = ["# manager_factor_positioning - resultados", "",
         f"- {expo['period'].nunique()} trimestres, "
         f"{expo['filer_id'].nunique()} gestores distintos, K={len(FACTORS)}",
         ""]

    L += ["## Validacao (antes de alpha)", ""]
    for r in synth_checks:
        L.append(f"- {r['period'].date()} {r['book']}: E[{r['factor']}] = "
                 f"{r['E']:+.2f} (esperado ~ +1.5 a +2.0)")
    rp = pd.concat(real_P, axis=1).T["mom"]
    pl = pd.Series(placebo_P)
    L += [f"- persistencia P_mom real AR1 = {rp.autocorr():+.2f} vs placebo "
          f"(shuffle intra-size) AR1 = {pl.autocorr():+.2f} "
          f"(placebo deve colapsar)", ""]

    L += ["## E5 dashboard (media e ultimo trimestre, AUM-weighted)", ""]
    last = dash[dash["period"] == dash["period"].max()].set_index("factor")
    mean_ = dash.groupby("factor")[["P_aum", "dispersion",
                                    "breadth_pos", "hhi_pos"]].mean()
    tab = mean_.round(3).join(last[["P_aum"]].round(3),
                              rsuffix="_last")
    L += [tab.to_markdown(), ""]

    if len(pnl):
        L += ["## E2/E3 - decomposicao e testes de painel", ""]
        va = pnl.groupby("factor")[["drift_price", "drift_char",
                                    "rot_agg"]].std()
        L += ["Desvio-padrao temporal de cada componente (quem move a "
              "exposicao agregada):", va.round(4).to_markdown(), ""]
        # H1/H2 persistence
        h1 = pnl.groupby("factor")["P_aum"].apply(lambda s: s.autocorr())
        h2 = pnl.groupby("factor")["rot_agg"].apply(lambda s: s.autocorr())
        L += ["- H1 AR1 da posicao agregada: "
              + ", ".join(f"{k} {v:+.2f}" for k, v in h1.items()),
              "- H2 AR1 da rotacao ativa: "
              + ", ".join(f"{k} {v:+.2f}" for k, v in h2.items()), ""]
        # standardize within factor for the pooled tests
        pnl["pz"] = pnl.groupby("factor")["pressure"].transform(
            lambda s: (s - s.mean()) / s.std())
        pnl["fz"] = pnl.groupby("factor")["funding"].transform(
            lambda s: (s - s.mean()) / s.std())
        # expanding crowding z (no look-ahead)
        pnl["crowd"] = pnl.groupby("factor")["P_aum"].transform(
            lambda s: (s - s.expanding(CROWD_MIN).mean().shift(1))
            / s.expanding(CROWD_MIN).std().shift(1))
        ok = pnl.dropna(subset=["pz", "fwd_factor_ret"])
        cl = ok["period"].astype(str).values
        b, se = cluster_ols(ok["fwd_factor_ret"].values,
                            ok[["pz"]].values, cl)
        L += [f"- H3 (pressure -> retorno do fator t+1, painel K x T, "
              f"SE cluster/tri): b = {b[1]:+.5f} (t = {b[1] / se[1]:+.2f}, "
              f"n = {len(ok)})"]
        ok2 = pnl.dropna(subset=["crowd", "fwd_factor_ret"])
        if len(ok2) > 40:
            b4, se4 = cluster_ols(ok2["fwd_factor_ret"].values,
                                  ok2[["crowd"]].values,
                                  ok2["period"].astype(str).values)
            L += [f"- H4 (crowding sozinho): b = {b4[1]:+.5f} "
                  f"(t = {b4[1] / se4[1]:+.2f}, n = {len(ok2)}) - "
                  f"esperado ~0"]
        ok3 = pnl.dropna(subset=["crowd", "fz", "fwd_factor_ret"]).copy()
        if len(ok3) > 40:
            ok3["shock"] = (-ok3["fz"]).clip(lower=0)
            ok3["inter"] = ok3["shock"] * ok3["crowd"]
            b5, se5 = cluster_ols(
                ok3["fwd_factor_ret"].values,
                ok3[["shock", "crowd", "inter"]].values,
                ok3["period"].astype(str).values)
            L += [f"- H5 (choque adverso x crowding): b_inter = "
                  f"{b5[3]:+.5f} (t = {b5[3] / se5[3]:+.2f}, "
                  f"n = {len(ok3)}) - esperado NEGATIVO", ""]

    if mech_rows:
        me = pd.DataFrame(mech_rows)
        L += ["## E4 - mismatch de rebalanceamento (momentum)", "",
              f"- MECANISMO: IC(mismatch_t, dIO_t+1) = "
              f"{me['ic_dio'].mean():+.4f} (t = {nw_tstat(me['ic_dio']):+.2f}, "
              f"{len(me)} tri) - pre-registro: NEGATIVO (owners vendem o "
              f"que saiu do estilo)"]
    if ret_events:
        re_ = pd.DataFrame(ret_events)
        L += [f"- RETORNO: spread Q5-Q1 {re_['spread_ew'].mean():+.4f}/tri "
              f"(t = {nw_tstat(re_['spread_ew']):+.2f}), IC "
              f"{re_['ic'].mean():+.4f}, {len(re_)} tri - pre-registro: "
              f"NEGATIVO"]
        re_.to_csv(RESULTS / "mismatch_events.csv", index=False)

    (RESULTS / "MFP_REPORT.md").write_text("\n".join(L), encoding="utf-8")
    log("done -> results/")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    main(**vars(ap.parse_args()))
