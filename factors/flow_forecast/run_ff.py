"""Flow forecasting (Coval-Stafford style): predict NEXT quarter's
manager flow from this quarter's flow + performance - can we identify
the distressed BEFORE their filing reveals it?

    python run_ff.py

LITERATURE: Coval-Stafford 2007 build expected flows exactly this way
(lagged flow + lagged performance); Sirri-Tufano/Chevalier-Ellison give
the convex flow-performance chasing; Lou 2012 scales it to predictable
flow-induced trading. Our own daily-anticipation attempt (stress_short)
was RETRACTED - this is the QUARTERLY clock, where the literature lives.

MECHANISM-FIRST GATES (in order; price only if the middle links hold):
  G1  forecastability: rank-corr(predicted flow_{t+1}, realized) OOS,
      expanding coefficients, strictly past. Also convexity term.
  G2  predicted-distress validity: managers PREDICTED to be in the
      bottom flow decile - do they actually SELL next quarter like the
      realized-distressed do (the t=+20.9 benchmark machinery)?
  G3  the payoff: supply basket built from PREDICTED distress at t
      (tradable at t+45d, one quarter EARLIER than the realized-distress
      basket) - forward excess return vs the realized-distress basket's.
Shrinkage variant: per-manager sensitivity pooled toward the cross-
section (single-slope pooled OLS = maximal shrinkage; per-manager slopes
are hopeless with ~40 obs - James-Stein logic, NMF-cluster refinement
left as next step).
"""
from __future__ import annotations

import sys
from collections import defaultdict, deque
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sps

HERE = Path(__file__).resolve().parent
for sub in ("", "general_plan", "fire_calendar"):
    sys.path.insert(0, str(HERE.parent / sub))

import panel as pn                                  # noqa: E402
from backtest_gp import forward_return, nw_tstat    # noqa: E402
from run_all import load_market, log                # noqa: E402
from run_fire import implied_flows                  # noqa: E402

RESULTS = HERE / "results"
LAG = 45
MIN_HIST = 8


def main() -> None:
    RESULTS.mkdir(exist_ok=True)
    cmap, mdta = load_market()
    dates = mdta.prices.index
    cum = mdta.returns.cumsum()
    bench = mdta.benchmark_returns.reindex(dates).fillna(0.0).cumsum()
    adv = mdta.dollar_volume.rolling(63, min_periods=20).median()

    qs = [q for q in pn.quarters()
          if pd.Timestamp("2013-06-30") <= q <= dates[-1] - pd.Timedelta(days=120)]
    log(f"{len(qs)} quarters")

    hist_rows = []          # pooled training rows (strictly past at use)
    prev_state: dict = {}   # filer -> (flow_t, perf_t)
    g1_rows, g2_rows, g3_rows = [], [], []

    for qi in range(1, len(qs)):
        p, p1 = qs[qi], qs[qi - 1]
        dec = p + pd.Timedelta(days=LAG)
        if dec >= dates[-1] - pd.Timedelta(days=95):
            continue
        cur = pn.snapshot_as_of(p, dec)
        prev = pn.snapshot_as_of(p1, dec)
        if min(len(cur), len(prev)) < 1000:
            continue
        di_p = dates.searchsorted(p, side="right") - 1
        di_p1 = dates.searchsorted(p1, side="right") - 1
        di = dates.searchsorted(dec, side="right") - 1
        ret_q = cum.iloc[di_p] - cum.iloc[di_p1]
        mret = float(bench.iloc[di_p] - bench.iloc[di_p1])
        adv_d = adv.iloc[di]
        px = mdta.prices_raw.iloc[di]

        fl = implied_flows(cur, prev, cmap, ret_q)
        if len(fl) < 300:
            prev_state = {}
            continue
        perf = (fl["rbook"] - mret)

        # ---- G1: forecast flow_t from state at t-1 (coefs from past) ----- #
        common = [m for m in fl.index if m in prev_state]
        if len(common) > 300 and len(hist_rows) >= MIN_HIST * 300:
            H = pd.DataFrame(hist_rows)
            X = np.column_stack([np.ones(len(H)), H["flow"], H["perf"],
                                 np.minimum(H["perf"], 0)])
            b_, *_ = np.linalg.lstsq(X, H["flow_next"].values, rcond=None)
            f0 = np.array([prev_state[m][0] for m in common])
            p0 = np.array([prev_state[m][1] for m in common])
            pred = b_[0] + b_[1] * f0 + b_[2] * p0 \
                + b_[3] * np.minimum(p0, 0)
            real = fl["flow"].reindex(common).values
            g1_rows.append({
                "period": p,
                "rank_corr": float(sps.spearmanr(pred, real)[0]),
                "n": len(common)})

            # ---- G2: do PREDICTED-distress managers actually sell? ------- #
            pr = pd.Series(pred, index=common)
            pred_dis = pr.nsmallest(max(int(len(pr) * 0.10), 20)).index
            nxt_q = qs[qi + 1] if qi + 1 < len(qs) else None
            if nxt_q is not None:
                dec2 = nxt_q + pd.Timedelta(days=LAG)
                if dec2 < dates[-1]:
                    nxt = pn.snapshot_as_of(nxt_q, dec2)
                    a = cur[cur["filer_id"].isin(pred_dis)][
                        ["filer_id", "instrument_id", "shares"]].merge(
                        nxt[["filer_id", "instrument_id", "shares"]],
                        on=["filer_id", "instrument_id"], how="left",
                        suffixes=("", "_n"))
                    sold_pred = float(((a["shares"] - a["shares_n"]
                                        .fillna(0.0)).clip(lower=0)
                                       / a["shares"]).mean())
                    ctrl_m = pr.nlargest(len(pred_dis)).index
                    c = cur[cur["filer_id"].isin(ctrl_m)][
                        ["filer_id", "instrument_id", "shares"]].merge(
                        nxt[["filer_id", "instrument_id", "shares"]],
                        on=["filer_id", "instrument_id"], how="left",
                        suffixes=("", "_n"))
                    sold_ctrl = float(((c["shares"] - c["shares_n"]
                                        .fillna(0.0)).clip(lower=0)
                                       / c["shares"]).mean())
                    g2_rows.append({"period": p,
                                    "sold_pred_dis": sold_pred,
                                    "sold_pred_inflow": sold_ctrl})

            # ---- G3: supply basket from PREDICTED distress, tradable NOW - #
            s = cur[cur["filer_id"].isin(pred_dis)].copy()
            s["ticker"] = s["instrument_id"].map(cmap)
            s = s.dropna(subset=["ticker"])
            s["advj"] = s["ticker"].map(adv_d)
            s = s.dropna(subset=["advj"])
            mag = (-pr).clip(lower=0.0).reindex(s["filer_id"]).values
            aumc = fl["aum_cur"].reindex(s["filer_id"]).values
            s["sup"] = mag * aumc * (
                s["value_usd"] / s.groupby("filer_id")["value_usd"]
                .transform("sum"))
            sup = (s.groupby("ticker")["sup"].sum()
                   / adv_d.reindex(s.groupby("ticker")["sup"].sum().index))
            sup = sup.replace([np.inf, -np.inf], np.nan).dropna()
            sup = sup[px.reindex(sup.index) >= 1.0]
            if len(sup) >= 60:
                top = sup.nlargest(max(int(len(sup) * 0.2), 30)).index
                nxt_dec = qs[qi + 1] + pd.Timedelta(days=LAG) \
                    if qi + 1 < len(qs) else dates[-1]
                fwd = forward_return(cum, dates, dec,
                                     min(nxt_dec, dates[-1]))
                uni_m = float(fwd.reindex(
                    px.index[px >= 1.0]).dropna().median())
                g3_rows.append({
                    "period": p, "n": len(top),
                    "excess": float(fwd.reindex(top).dropna()
                                    .clip(-0.5, 0.5).mean() - uni_m)})

        # ---- update pooled history and state ------------------------------ #
        for m in common:
            hist_rows.append({"flow": prev_state[m][0],
                              "perf": prev_state[m][1],
                              "flow_next": float(fl.loc[m, "flow"])})
        prev_state = {m: (float(fl.loc[m, "flow"]), float(perf.loc[m]))
                      for m in fl.index}
        log(f"{p.date()}: {len(fl)} fl, hist {len(hist_rows)}")

    L = ["# flow_forecast - predicting inflow/stop-out points one "
         "quarter ahead (Coval-Stafford clock)", ""]
    if g1_rows:
        g1 = pd.DataFrame(g1_rows)
        L += ["## G1 - is the implied flow forecastable?",
              f"- OOS rank-corr (predicted vs realized flow): "
              f"{g1['rank_corr'].mean():+.3f} "
              f"(t={nw_tstat(g1['rank_corr']):+.2f}, {len(g1)} qtrs, "
              f"~{g1['n'].mean():.0f} managers/qtr)", ""]
    if g2_rows:
        g2 = pd.DataFrame(g2_rows)
        d = g2["sold_pred_dis"] - g2["sold_pred_inflow"]
        L += ["## G2 - do PREDICTED-distressed managers actually sell?",
              f"- fraction sold next quarter: predicted-distressed "
              f"{g2['sold_pred_dis'].mean():.3f} vs predicted-inflow "
              f"{g2['sold_pred_inflow'].mean():.3f} "
              f"(delta t={nw_tstat(d):+.2f})",
              f"- contemporaneous benchmark (realized distress): "
              f"32.5% vs 16.2%, t=+20.9", ""]
    if g3_rows:
        g3 = pd.DataFrame(g3_rows)
        L += ["## G3 - short the PREDICTED supply basket (one quarter "
              "before the filing reveals it)",
              f"- predicted-basket excess: {g3['excess'].mean():+.4f}"
              f"/qtr (t={nw_tstat(g3['excess']):+.2f}, {len(g3)} qtrs) - "
              f"negative = the anticipated short captures the decline",
              f"- reference (realized distress, same construction): "
              f"~-4.5%/qtr historical"]
    (RESULTS / "FF_REPORT.md").write_text("\n".join(L), encoding="utf-8")
    log("done -> results/")


if __name__ == "__main__":
    main()
