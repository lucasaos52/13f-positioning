"""Literature-faithful sorts: what the published numbers actually measure.

The main run applies the plan §4.1 pipeline (size neutralisation +
orthogonalisation) to every factor - right for a CLEAN factor, wrong for a
LITERATURE COMPARISON, because the published Days-ADV numbers are raw sorts:

  Brown-Howard-Lundblad / Chincarini et al., quintiles on raw Days-ADV,
  1980-2021, all filers: Q5 (most crowded) +0.54%/mo, Q1 -0.90%/mo,
  spread 1.44%/mo (t=9.67). Their own Amihud adjustment shrinks it to
  0.89%/mo - i.e. ~40% of the raw spread IS the liquidity premium that our
  size/liquidity neutralisation removes by design.

This script reruns the sorts the way the papers do:
  - RAW signal (winsor + log + rank only; NO residualisation);
  - liquidity floor relaxed to price >= $1 and no ADV cut (their Q1 lives
    in illiquid small caps; our default floor amputates the short leg);
  - per-leg quintile means reported, not just the spread (their result is
    2/3 short leg);
  - all filers, D+45, quarterly hold, EW and VW.

Also runs dBreadth (Chen-Hong-Stein 2002: raw decile sort, low-minus-high
spread 6.38%/12mo in 1979-1998 mutual funds) as the count-based line.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import panel as pn                    # noqa: E402
import signals as sg                  # noqa: E402
from backtest_gp import forward_return, nw_tstat  # noqa: E402
from run_all import load_market, log  # noqa: E402

RESULTS = HERE / "results"


def main() -> None:
    cmap, mdta = load_market()
    dates = mdta.prices.index
    cum = mdta.returns.cumsum()
    adv = mdta.dollar_volume.rolling(63, min_periods=20).median()

    qs = [q for q in pn.quarters()
          if pd.Timestamp("2013-06-30") <= q <= dates[-1] - pd.Timedelta(days=120)]
    rows = []
    for qi in range(1, len(qs)):
        p, p_prev = qs[qi], qs[qi - 1]
        dec = p + pd.Timedelta(days=45)
        if dec >= dates[-1] - pd.Timedelta(days=95):
            continue
        cur = pn.snapshot_as_of(p, dec)
        prev = pn.snapshot_as_of(p_prev, dec)
        if min(len(cur), len(prev)) < 1000:
            continue
        di = dates.searchsorted(dec, side="right") - 1
        adv_d, px = adv.iloc[di], mdta.prices_raw.iloc[di]

        inst = cur.groupby("instrument_id").agg(val=("value_usd", "sum"),
                                                n=("filer_id", "nunique"))
        pin = prev.groupby("instrument_id")["filer_id"].nunique()
        tick = inst.index.to_series().map(cmap)
        da = inst["val"] / tick.map(adv_d)
        dbr = (inst["n"] - pin.reindex(inst.index).fillna(0.0)) / float(
            cur["filer_id"].nunique())

        raw = pd.DataFrame({"days_adv": da, "dbreadth": dbr,
                            "ticker": tick, "val": inst["val"]}).dropna(
            subset=["ticker"])
        byt = raw.groupby("ticker").agg(days_adv=("days_adv", "sum"),
                                        dbreadth=("dbreadth", "sum"),
                                        val=("val", "sum"))
        # literature floor: listed, price >= $1, ADV exists. Nothing else.
        u = byt.index[(px.reindex(byt.index) >= 1.0)
                      & tick.map(adv_d).groupby(tick).first().reindex(byt.index).gt(0)]
        byt = byt.loc[byt.index.isin(u)]

        nxt = p + pd.offsets.QuarterEnd(1) + pd.Timedelta(days=45)
        fwd = forward_return(cum, dates, dec, min(nxt, dates[-1]))
        for fac, logit in [("days_adv", True), ("dbreadth", False)]:
            s = byt[fac].replace([np.inf, -np.inf], np.nan).dropna()
            s = s.clip(s.quantile(0.01), s.quantile(0.99))
            if logit:
                s = np.log1p(s.clip(lower=0))
            s = s.rank(pct=True)                     # RAW rank - no residual
            df = pd.concat([s.rename("s"), fwd.reindex(s.index).rename("f"),
                            byt["val"].reindex(s.index).rename("vw")],
                           axis=1).dropna()
            if len(df) < 100:
                continue
            df["q"] = pd.qcut(df["s"], 5, labels=False, duplicates="drop") + 1
            ew = df.groupby("q")["f"].mean()
            vw = df.groupby("q").apply(lambda g: np.average(g["f"], weights=g["vw"]))
            r = {"period": p, "factor": fac, "n": len(df),
                 "spread_ew": ew.get(5, np.nan) - ew.get(1, np.nan),
                 "spread_vw": vw.get(5, np.nan) - vw.get(1, np.nan)}
            for k in range(1, 6):
                r[f"q{k}_ew"] = ew.get(k, np.nan)
            rows.append(r)
        log(f"{p.date()} ok")

    ev = pd.DataFrame(rows)
    ev.to_csv(RESULTS / "literature_sorts.csv", index=False)
    out = []
    for fac, g in ev.groupby("factor"):
        rec = {"factor": fac, "n_events": len(g)}
        for col in ("spread_ew", "spread_vw"):
            rec[f"{col}_mean_q"] = g[col].mean()
            rec[f"{col}_t_nw"] = nw_tstat(g[col])
        for k in range(1, 6):
            rec[f"q{k}_ew_mean"] = g[f"q{k}_ew"].mean()
        out.append(rec)
    res = pd.DataFrame(out).set_index("factor")
    res.to_csv(RESULTS / "literature_summary.csv")
    print(res.round(4).to_string())


if __name__ == "__main__":
    main()
    os.chdir(HERE)
