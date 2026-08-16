"""Reconcile the DH price-leg surface with the earlier module-level
distress numbers (-4.5%/q cohort excess; M3 positive short PnL).

Differences to isolate, default config (thr -0.10, top 20%):
  benchmark   universe MEDIAN (DH) vs universe MEAN vs S&P (hedged)
  basket      supply/ADV top-frac (DH) vs held-cohort (absorcao-style)
  pecking     with vs without the liquidity-rank multiplier
  clipping    +-0.5 clip vs none
Windows: full, IS (<=2020), OOS (2021+).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
for sub in ("", "general_plan", "fire_calendar"):
    sys.path.insert(0, str(HERE.parent / sub))

import panel as pn                                  # noqa: E402
from backtest_gp import forward_return, nw_tstat    # noqa: E402
from run_all import load_market, log                # noqa: E402
from run_fire import implied_flows                  # noqa: E402

LAG = 45
THR, FRAC = -0.10, 0.20


def main() -> None:
    cmap, mdta = load_market()
    dates = mdta.prices.index
    cum = mdta.returns.cumsum()
    bench = mdta.benchmark_returns.reindex(dates).fillna(0.0).cumsum()
    adv = mdta.dollar_volume.rolling(63, min_periods=20).median()

    qs = [q for q in pn.quarters()
          if pd.Timestamp("2013-06-30") <= q
          <= dates[-1] - pd.Timedelta(days=120)]
    rows = []
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
        dis = fl.index[fl["flow"] < THR]
        if len(dis) < 10:
            continue
        s = cur[cur["filer_id"].isin(dis)].copy()
        s["ticker"] = s["instrument_id"].map(cmap)
        s = s.dropna(subset=["ticker"])
        s["advj"] = s["ticker"].map(adv_d)
        s = s.dropna(subset=["advj"])
        fmag = fl["flow"].abs().reindex(s["filer_id"]).values
        aumc = fl["aum_cur"].reindex(s["filer_id"]).values
        w = s["value_usd"] / s.groupby("filer_id")["value_usd"] \
            .transform("sum")
        s["peck"] = s.groupby("filer_id")["advj"].rank(pct=True)
        s["sup"] = fmag * aumc * w
        s["sup_pk"] = s["sup"] * s["peck"]

        nxt_dec = qs[qi + 1] + pd.Timedelta(days=LAG) \
            if qi + 1 < len(qs) else dates[-1]
        fwd = forward_return(cum, dates, dec, min(nxt_dec, dates[-1]))
        mret = float(bench.reindex(dates).iloc[
            dates.searchsorted(min(nxt_dec, dates[-1]), side="right") - 1]
            - bench.iloc[di])
        uni_ok = px.index[px >= 1.0]
        f_u = fwd.reindex(uni_ok).dropna()
        med, mean = float(f_u.median()), float(f_u.mean())

        def basket_ret(sup_col, frac=FRAC):
            g = s.groupby("ticker")[sup_col].sum()
            sup = (g / adv_d.reindex(g.index)).replace(
                [np.inf, -np.inf], np.nan).dropna()
            sup = sup[px.reindex(sup.index) >= 1.0]
            if len(sup) < 40:
                return np.nan
            top = sup.nlargest(max(int(len(sup) * frac), 20)).index
            return float(fwd.reindex(top).dropna().clip(-0.5, 0.5).mean())

        # held-cohort (absorcao-style): all names held by distressed,
        # weighted by nothing - plain mean of the cohort
        coh = s.groupby("ticker")["value_usd"].sum()
        coh = coh[px.reindex(coh.index) >= 1.0]
        coh_r = float(fwd.reindex(coh.index).dropna().clip(-0.5, 0.5)
                      .mean()) if len(coh) > 40 else np.nan

        b = basket_ret("sup")
        bpk = basket_ret("sup_pk")
        rows.append({
            "period": p,
            "vs_median": b - med, "vs_mean": b - mean, "vs_mkt": b - mret,
            "peck_vs_median": bpk - med,
            "cohort_vs_mean": coh_r - mean, "cohort_vs_mkt": coh_r - mret})
        log(f"{p.date()}")

    E = pd.DataFrame(rows).set_index("period").sort_index()
    E.to_csv(HERE / "results" / "reconcile.csv")
    for w, m in [("full", E), ("IS<=2020", E[E.index <= "2020-12-31"]),
                 ("OOS 2021+", E[E.index > "2020-12-31"])]:
        print(f"-- {w} ({len(m)}q)")
        for c in E.columns:
            x = m[c].dropna()
            print(f"   {c:18s} {x.mean():+.4f}/q  t={nw_tstat(x):+.2f}")


if __name__ == "__main__":
    main()
