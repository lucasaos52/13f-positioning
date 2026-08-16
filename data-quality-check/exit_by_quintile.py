"""Panel-exit rate by NCB quintile: is the delisting-free price panel
bias quintile-neutral?

    python exit_by_quintile.py

A name 'exits' when it is in the universe at the decision date but has
no forward return over the holding window (left the price panel). If
exit rates are ~uniform across NCB quintiles, the delisting-free
approximation cannot manufacture the spread in either direction.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
for sub in ("factors", "factors/general_plan", "data-quality-check"):
    sys.path.insert(0, str(ROOT / sub))

import panel as pn                                  # noqa: E402
from backtest_gp import forward_return, nw_tstat    # noqa: E402
from rerun_champion_expanded import (               # noqa: E402
    residualise, split_factor)
from run_all import load_market, log                # noqa: E402

LAG = 45


def main() -> None:
    cmap, mdta = load_market()
    dates = mdta.prices.index
    cum = mdta.returns.cumsum()

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
        px = mdta.prices_raw.iloc[di]
        fac_i = split_factor(cur, prev)
        prev_sh = prev.groupby(["filer_id", "instrument_id"])["shares"].sum()

        b = cur.copy()
        tot = b.groupby("filer_id")["value_usd"].transform("sum")
        b["w"] = b["value_usd"] / tot.replace(0, np.nan)
        b["thr"] = b.groupby("filer_id")["w"].transform(
            lambda s: s.quantile(0.9))
        key = pd.MultiIndex.from_frame(b[["filer_id", "instrument_id"]])
        shp = pd.Series(prev_sh.reindex(key).values, index=b.index)
        fac = b["instrument_id"].map(fac_i).fillna(1.0)
        grew = shp.isna() | (b["shares"] >= 1.25 * shp * fac)
        v = b[(b["w"] >= b["thr"]) & grew].copy()
        v["ticker"] = v["instrument_id"].map(cmap)
        v = v.dropna(subset=["ticker"])
        nc = v.groupby("ticker")["filer_id"].nunique()
        b["ticker"] = b["instrument_id"].map(cmap)
        n_c = b.dropna(subset=["ticker"]).groupby("ticker")["filer_id"] \
            .nunique()
        idx_all = n_c.index[n_c >= 5]
        uni = idx_all[pd.Series(idx_all.map(px), index=idx_all) >= 1.0]
        s = nc.reindex(uni).fillna(0.0).rank(pct=True)

        nxt = qs[qi + 1] + pd.Timedelta(days=LAG) if qi + 1 < len(qs) \
            else dates[-1]
        fwd = forward_return(cum, dates, dec, min(nxt, dates[-1])) \
            .reindex(uni)
        rng = np.random.default_rng(int(p.value) % (2**32))
        jit = pd.Series(rng.uniform(0, 1e-9, len(s)), index=s.index)
        q5 = pd.qcut((s + jit).rank(), 5, labels=False)
        exit_flag = fwd.isna()
        row = {"period": p}
        for q in range(5):
            row[f"q{q + 1}"] = float(exit_flag[q5 == q].mean())
        rows.append(row)
        log(f"{p.date()}: exits "
            + " ".join(f"{row[f'q{q + 1}']:.3f}" for q in range(5)))

    E = pd.DataFrame(rows).set_index("period")
    E.to_csv(Path(__file__).parent / "results" / "exit_by_quintile.csv")
    print("\nmean exit rate by NCB quintile (Q1=no votes, Q5=top):")
    print(E.mean().round(4).to_string())
    d = E["q1"] - E["q5"]
    print(f"delta Q1-Q5: {d.mean():+.4f} (t={nw_tstat(d):+.2f})")


if __name__ == "__main__":
    main()
