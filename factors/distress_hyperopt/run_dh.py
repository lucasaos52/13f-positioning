"""Bootstrap-robust hyperparameter surface for the DISTRESS leg -
the two remaining unjustified hyperparameters of the production combo.

    python run_dh.py

PROVENANCE: DISTRESS_FLOW = -0.10 ("a manager is distressed when
implied flow < -10%") and the top-20% supply basket were set a priori
and never varied - the same status the champion's trio had before
champion_hyperopt. They sit behind the t=+20.9 mechanism headline, the
score model's `distress` feature and the combo's short leg, so the
surface deserves the same treatment (arXiv:2510.12725 protocol).

TWO SEPARATE QUESTIONS, kept separate on purpose:
  (1) MECHANISM MONOTONICITY (no selection involved): the fraction of
      held shares sold next quarter by managers below each threshold,
      vs healthy managers. If the delta grows smoothly as the
      threshold tightens, -0.10 is a point on a monotone curve, not a
      cherry-pick; the t=+20.9 headline is threshold-robust.
  (2) PRICE-LEG SURFACE (selection risk lives here): the short
      basket's forward excess (negative = the short pays) over a
      5 thresholds x 3 basket-fraction grid; IS 2013-2020, coupled
      moving-block bootstrap (block 4, B=2000) of the IS series,
      selection by the 5th percentile of the SHORT-LEG Sharpe
      (utility = -excess), frozen, evaluated OOS 2021+.
Same honesty clause as champion_hyperopt: the a-priori default stays
the reported spec; a better grid point is a post-hoc candidate.
"""
from __future__ import annotations

import sys
from itertools import product
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
IS_END = pd.Timestamp("2020-12-31")
THRS = (-0.05, -0.075, -0.10, -0.15, -0.20)
FRACS = (0.10, 0.20, 0.30)
DEFAULT = (-0.10, 0.20)
BLOCK, NDRAWS, PCTL = 4, 2000, 5.0


def cfg(thr, fr):
    return f"thr{thr:+.3f}_top{int(fr * 100)}"


def main() -> None:
    RESULTS.mkdir(exist_ok=True)
    cmap, mdta = load_market()
    dates = mdta.prices.index
    cum = mdta.returns.cumsum()
    bench = mdta.benchmark_returns.reindex(dates).fillna(0.0).cumsum()
    adv = mdta.dollar_volume.rolling(63, min_periods=20).median()

    qs = [q for q in pn.quarters()
          if pd.Timestamp("2013-06-30") <= q
          <= dates[-1] - pd.Timedelta(days=120)]
    configs = list(product(THRS, FRACS))
    price_rows, mech_rows = [], []

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
        ret_q = cum.iloc[di_p] - cum.iloc[di_p1]
        adv_d = adv.iloc[di]
        px = mdta.prices_raw.iloc[di]
        fl = implied_flows(cur, prev, cmap, ret_q)
        if len(fl) < 300:
            continue

        # ---- (1) mechanism: sold fraction per threshold --------------- #
        nxt_q = qs[qi + 1] if qi + 1 < len(qs) else None
        nxt = None
        if nxt_q is not None:
            dec2 = nxt_q + pd.Timedelta(days=LAG)
            if dec2 < dates[-1]:
                nxt = pn.snapshot_as_of(nxt_q, dec2)
        if nxt is not None and len(nxt) > 1000:
            healthy = fl.index[fl["flow"] > 0]

            def sold_frac(members):
                a = cur[cur["filer_id"].isin(members)][
                    ["filer_id", "instrument_id", "shares"]].merge(
                    nxt[["filer_id", "instrument_id", "shares"]],
                    on=["filer_id", "instrument_id"], how="left",
                    suffixes=("", "_n"))
                if len(a) < 200:
                    return np.nan
                return float(((a["shares"] - a["shares_n"].fillna(0.0))
                              .clip(lower=0) / a["shares"]).mean())

            row = {"period": p, "sold_healthy": sold_frac(healthy)}
            for thr in THRS:
                dis = fl.index[fl["flow"] < thr]
                row[f"sold_{thr:+.3f}"] = sold_frac(dis) \
                    if len(dis) >= 10 else np.nan
                row[f"n_{thr:+.3f}"] = int(len(dis))
            mech_rows.append(row)

        # ---- (2) price leg per config --------------------------------- #
        nxt_dec = qs[qi + 1] + pd.Timedelta(days=LAG) \
            if qi + 1 < len(qs) else dates[-1]
        fwd = forward_return(cum, dates, dec, min(nxt_dec, dates[-1]))
        uni_ok = px.index[px >= 1.0]
        uni_m = float(fwd.reindex(uni_ok).dropna().median())
        mkt = float(bench.iloc[dates.searchsorted(
            min(nxt_dec, dates[-1]), side="right") - 1] - bench.iloc[di])
        prow = {"period": p, "mkt_minus_med": mkt - uni_m}
        for thr, fr in configs:
            dis = fl.index[fl["flow"] < thr]
            if len(dis) < 10:
                prow[cfg(thr, fr)] = np.nan
                continue
            s = cur[cur["filer_id"].isin(dis)].copy()
            s["ticker"] = s["instrument_id"].map(cmap)
            s = s.dropna(subset=["ticker"])
            fmag = fl["flow"].abs().reindex(s["filer_id"]).values
            aumc = fl["aum_cur"].reindex(s["filer_id"]).values
            s["sup"] = fmag * aumc * (
                s["value_usd"] / s.groupby("filer_id")["value_usd"]
                .transform("sum"))
            sup = (s.groupby("ticker")["sup"].sum()
                   / adv_d.reindex(s.groupby("ticker")["sup"].sum().index))
            sup = sup.replace([np.inf, -np.inf], np.nan).dropna()
            sup = sup[px.reindex(sup.index) >= 1.0]
            if len(sup) < 40:
                prow[cfg(thr, fr)] = np.nan
                continue
            top = sup.nlargest(max(int(len(sup) * fr), 20)).index
            prow[cfg(thr, fr)] = float(
                fwd.reindex(top).dropna().clip(-0.5, 0.5).mean() - uni_m)
        price_rows.append(prow)
        log(f"{p.date()} done")

    M = pd.DataFrame(mech_rows).set_index("period")
    S = pd.DataFrame(price_rows).set_index("period").sort_index()
    M.to_csv(RESULTS / "dh_mechanism.csv")
    S.to_csv(RESULTS / "dh_price.csv")

    # ---- bootstrap-robust selection on the short-leg utility ---------- #
    # utility = -(basket - MARKET): the tradable, index-hedged short.
    # Stored cfg values are basket-minus-median, so subtract
    # (mkt - median) to get basket-minus-market. (The first cut used
    # the median benchmark; the reconciliation check showed benchmark
    # choice flips the story - see the verdict.)
    cfg_cols = [c for c in S.columns if c.startswith("thr")]
    S = S[cfg_cols].sub(S["mkt_minus_med"], axis=0)
    is_mask = S.index <= IS_END
    S_is, S_oos = S[is_mask].dropna(), S[~is_mask].dropna()
    T_is = len(S_is)
    rng = np.random.default_rng(20260816)
    n_blocks = int(np.ceil(T_is / BLOCK))
    idxs = np.stack([
        np.concatenate([np.arange(s0, s0 + BLOCK) for s0 in
                        rng.integers(0, T_is - BLOCK + 1, n_blocks)])[:T_is]
        for _ in range(NDRAWS)])
    stats = []
    for c in S.columns:
        u = -S_is[c].values                       # short pays -> positive
        draws = u[idxs]
        sh = draws.mean(axis=1) / draws.std(axis=1, ddof=1) * 2
        uo = -S_oos[c]
        stats.append({
            "config": c,
            "is_sharpe": float(u.mean() / u.std(ddof=1) * 2),
            "boot_p05": float(np.percentile(sh, PCTL)),
            "oos_sharpe": float(uo.mean() / uo.std(ddof=1) * 2),
            "oos_t": nw_tstat(uo)})
    R = pd.DataFrame(stats).set_index("config")
    R.to_csv(RESULTS / "dh_table.csv")

    name_def = cfg(*DEFAULT)
    pick = R["boot_p05"].idxmax()
    rc = sps.spearmanr(R["boot_p05"], R["oos_sharpe"])[0]
    rc_pt = sps.spearmanr(R["is_sharpe"], R["oos_sharpe"])[0]

    L = ["# Distress-leg hyperparameter surface (arXiv:2510.12725 "
         "protocol)", "",
         "**Provenance:** flow<-0.10 and the top-20% supply basket were "
         "set a priori and never varied before this script - the same "
         "status the champion's trio had before champion_hyperopt.", "",
         "## (1) Mechanism monotonicity - no selection involved", "",
         "| threshold | mean sold fraction | delta vs healthy (t) | "
         "avg n distressed/q |", "|---|---|---|---|",
         f"| healthy (flow>0) | {M['sold_healthy'].mean():.3f} | - | - |"]
    for thr in THRS:
        d = (M[f"sold_{thr:+.3f}"] - M["sold_healthy"]).dropna()
        L.append(f"| flow<{thr:+.3f} | {M[f'sold_{thr:+.3f}'].mean():.3f} "
                 f"| {d.mean():+.3f} (t={nw_tstat(d):+.2f}) | "
                 f"{M[f'n_{thr:+.3f}'].mean():.0f} |")
    L += ["", "## (2) Price-leg surface (short-leg Sharpe; utility = "
          "-excess)", "",
          f"- IS {T_is} q (<= {IS_END.date()}), OOS {len(S_oos)} q; "
          f"coupled block bootstrap block={BLOCK}, B={NDRAWS}", "",
          "| config | IS Sharpe | boot p05 | OOS Sharpe | OOS t |",
          "|---|---|---|---|---|"]
    for c in R.sort_values("boot_p05", ascending=False).index:
        r = R.loc[c]
        mark = " **(default)**" if c == name_def else ""
        L.append(f"| {c}{mark} | {r['is_sharpe']:+.2f} | "
                 f"{r['boot_p05']:+.2f} | {r['oos_sharpe']:+.2f} | "
                 f"{r['oos_t']:+.2f} |")
    L += ["",
          f"- robust p05 pick: {pick}; a-priori default: {name_def}",
          f"- rank-corr(boot p05, OOS): {rc:+.3f}; "
          f"rank-corr(IS point, OOS): {rc_pt:+.3f}"]
    (RESULTS / "DH_REPORT.md").write_text("\n".join(L), encoding="utf-8")
    log("done -> results/")


if __name__ == "__main__":
    main()
