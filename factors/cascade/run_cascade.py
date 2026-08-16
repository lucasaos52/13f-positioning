"""Shock -> Fund Outflow -> Other-Holdings Cascade (doc idea #2).

    python run_cascade.py            # full sample
    python run_cascade.py --smoke    # shorter tail

CAUSAL CHAIN (three stages, each tested in order - the price test only
means something if the middle link holds):
    single-name disaster in the book (idiosyncratic crash of one holding)
      -> end investors respond with redemptions   [Di Maggio et al.: flows
         are sensitive to salient single-stock losses]
      -> the manager must raise cash and sells the OTHER holdings,
         names with no news of their own
      -> predictable selling pressure spills over to innocent stocks.

STAGES:
  A (mechanism, no returns): does ShockExposure_m,t predict the manager's
    NEXT-quarter implied flow? SE_m = sum_i w_mi |xret_i| over holdings
    whose quarter excess return < -SHOCK_CUT. Pre-registered: coefficient
    NEGATIVE (pain -> outflows), pooled with quarter clustering.
  B (price): CascadePressure_j = sum_m E[outflow]_m * aum_m * w_mj / ADV_j
    over managers with high SE, EXCLUDING the shocked names themselves
    (the whole point: pressure on the innocent holdings). Pre-registered:
    NEGATIVE next-quarter excess for high-pressure names. Evaluated raw
    and residualized on size/ADV ranks (the matched-characteristics
    approximation of the doc's pair design).
  C placebo: SE permuted across managers -> both the outflow prediction
    and the price spread must die.

E[outflow] uses the STRICTLY-PAST pooled slope of stage A (expanding,
min 8 quarters) - the signal never sees its own quarter's outcome.
"""
from __future__ import annotations

import argparse
import sys
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
SHOCK_CUT = 0.25       # quarter excess return worse than -25% = disaster
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

    se_hist: dict = {}          # period -> Series SE per manager
    fl_hist: dict = {}          # period -> Series flow per manager
    mech_rows, price_rows = [], []

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

        # ---- current flows (outcome for stage A of quarter p-1) ---------- #
        fl = implied_flows(cur, prev, cmap, ret_q)
        fl_hist[p] = fl["flow"]

        # ---- stage A regression rows: SE at p-1 -> flow at p ------------- #
        if p1 in se_hist:
            se_prev = se_hist[p1]
            common = se_prev.index.intersection(fl.index)
            if len(common) > 200:
                mech_rows.append(pd.DataFrame({
                    "period": p, "se": se_prev.reindex(common),
                    "flow": fl["flow"].reindex(common)}))

        # ---- ShockExposure per manager at p ------------------------------ #
        d = cur[["filer_id", "instrument_id", "value_usd"]].copy()
        d["ticker"] = d["instrument_id"].map(cmap)
        d = d.dropna(subset=["ticker"])
        d["xr"] = d["ticker"].map(xret)
        book = d.groupby("filer_id")["value_usd"].transform("sum")
        d["w"] = d["value_usd"] / book.replace(0, np.nan)
        d["hit"] = (d["xr"] < -SHOCK_CUT).astype(float)
        d["se_c"] = d["w"] * d["xr"].abs() * d["hit"]
        se = d.groupby("filer_id")["se_c"].sum()
        npos = d.groupby("filer_id").size()
        se = se[npos >= 15]
        se_hist[p] = se

        # ---- stage B: cascade pressure, strictly-past slope -------------- #
        past = [pp for pp in se_hist if pp < p and qs[qs.index(pp) + 1]
                in fl_hist] if False else None
        # pooled slope from mech_rows accumulated so far (strictly past:
        # the last row uses flows known at THIS dec, so exclude it for the
        # signal? flows at p are computed from public snapshots at dec ->
        # usable. Slope uses rows with period <= p (all public by dec).
        if len(mech_rows) >= MIN_SLOPE_Q:
            M = pd.concat(mech_rows, ignore_index=True).dropna()
            b_hat = float(np.polyfit(M["se"], M["flow"], 1)[0])
        else:
            b_hat = None
        if b_hat is not None and b_hat < 0 and len(se) > 200:
            shocked_names = set(xret.index[(xret < -SHOCK_CUT)])
            aum = d.groupby("filer_id")["value_usd"].sum()
            exp_out = (b_hat * se).clip(upper=0.0)      # expected outflow
            rng = np.random.default_rng(int(p.value) % (2**32))
            se_perm = pd.Series(rng.permutation(se.values), index=se.index)
            exp_out_pl = (b_hat * se_perm).clip(upper=0.0)

            def pressure(e):
                dd = d[d["filer_id"].isin(e.index)].copy()
                dd["x"] = dd["filer_id"].map(e) \
                    * dd["filer_id"].map(aum) * dd["w"]
                s = dd.groupby("ticker")["x"].sum()
                s = s[~s.index.isin(shocked_names)]     # innocents only
                out = s / pd.Series(s.index.map(adv_d), index=s.index)
                return out.replace([np.inf, -np.inf], np.nan)

            cp = pressure(exp_out)          # <= 0; more negative = more sell
            cp_pl = pressure(exp_out_pl)
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
                   "n_shocked": len(shocked_names)}
            for nm, s in [("raw", cp), ("resid", cp), ("placebo", cp_pl)]:
                ss = s.reindex(uni)
                r = ss.rank(pct=True)       # high rank = LESS pressure
                if nm == "resid":
                    r = residualise(r, ctrl).rank(pct=True)
                df = pd.concat([r.rename("s"), fwd.rename("f")],
                               axis=1).dropna()
                if len(df) < 300:
                    row[f"spread_{nm}"] = np.nan
                    continue
                jit = pd.Series(rng.uniform(0, 1e-9, len(df)),
                                index=df.index)
                q5 = pd.qcut((df["s"] + jit).rank(), 5, labels=False)
                gq = df.groupby(q5)["f"].mean()
                # Q0 = most negative pressure (most expected selling):
                # thesis says Q0 underperforms -> spread Q4-Q0 POSITIVE
                row[f"spread_{nm}"] = float(gq.get(4, np.nan)
                                            - gq.get(0, np.nan))
            price_rows.append(row)
            log(f"{p.date()}: b_hat {b_hat:+.4f}, shocked "
                f"{len(shocked_names)}, spread "
                f"{row.get('spread_raw')}")

    # ---- reports ----------------------------------------------------------- #
    L = ["# cascade - choque single-name -> resgate -> venda dos inocentes",
         ""]
    if mech_rows:
        M = pd.concat(mech_rows, ignore_index=True).dropna()
        per_q = []
        for pp, g in M.groupby("period"):
            if len(g) > 100 and g["se"].std() > 0:
                per_q.append(float(np.polyfit(g["se"], g["flow"], 1)[0]))
        per_q = pd.Series(per_q)
        L += ["## Estagio A - mecanismo (SE_t -> fluxo_t+1)", "",
              f"- slope pooled: {np.polyfit(M['se'], M['flow'], 1)[0]:+.4f} "
              f"({len(M)} obs gestor-tri)",
              f"- slope por tri: media {per_q.mean():+.4f} "
              f"(t={nw_tstat(per_q):+.2f}, {len(per_q)} tri) - "
              f"pre-registro: NEGATIVO (dor -> resgate)", ""]
    pr = pd.DataFrame(price_rows)
    if len(pr):
        pr.to_csv(RESULTS / "cascade_events.csv", index=False)
        L += ["## Estagio B - preco nos inocentes (spread Q4-Q0, "
              "esperado POSITIVO: quem tem mais pressao esperada de venda "
              "rende menos)", ""]
        for nm, lbl in [("raw", "raw"), ("resid", "resid size/ADV"),
                        ("placebo", "placebo (SE permutado)")]:
            s = pr[f"spread_{nm}"].dropna()
            if len(s):
                L.append(f"- **{lbl}**: {s.mean():+.4f}/tri "
                         f"(t={nw_tstat(s):+.2f}, {len(s)} tri)")
    (RESULTS / "CASCADE_REPORT.md").write_text("\n".join(L),
                                               encoding="utf-8")
    log("done -> results/")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    main(**vars(ap.parse_args()))
