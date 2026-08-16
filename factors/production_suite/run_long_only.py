"""Long-only implementation that respects the regime: cap-weighted
benchmark tilted by the NCB+FSS combo rank (institutional LO design,
tracking-error controlled), instead of the EW long basket that eats
the Bessembinder tax.

    python run_long_only.py

Design (mirrors the user's multifactor LO: benchmark weights x
exponential tilt, renormalized):
  benchmark   cap-weighted portfolio of the tradable universe
              (Filters: $4 / $5M ADV / 252d), quarterly refresh
  tilt        w_i propto w_bench,i * exp(k * 2*(rank_i - 0.5)),
              k in {1, 2, 3}; rank = combo cross-sectional pct rank;
              names without a signal keep benchmark weight (rank 0.5)
  rebal       at combo decision stamps (quarterly); weights held
              static between rebals (renormalized daily drift approx)
  costs       5 bps per side on turnover at each rebal
Outputs: pnl series (LO tilted, benchmark), metrics incl. excess vs
benchmark (TE, IR, maxDD-vs-bench) and vs the S&P index, and the
paper figure f11_long_only.png.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
for sub in ("", "general_plan"):
    sys.path.insert(0, str(HERE.parent / sub))

import market_cap as mc                             # noqa: E402
from run_all import load_market, log                # noqa: E402

PAPER = HERE.parent.parent / "docs" / "paper"
FEE = 0.0005

cmap, mdta = load_market()
dates = mdta.prices.index
rets = mdta.returns
# Benchmark = true cap weights over the top-500 names by REPAIRED
# market cap (an S&P-500 proxy; official constituent weights are
# licensed data). Repair: the shares-inferred mktcap panel is fine as
# a ranked regression control but has a corrupt tail as portfolio
# weights (reverse splits break the shares inference - a micro-cap
# was getting 6% weight). Per rebal date we regress log(mcap) on
# log(ADV) cross-sectionally and replace |resid| > 2.5 sigma outliers
# with the fitted value.
adv = mdta.dollar_volume.rolling(63, min_periods=20).median()
shares = mc.shares_panel(dates, mdta.tickers, mdta.prices,
                         mdta.prices_raw)
mcap = mc.mktcap_panel(mdta.prices_raw, shares)
W_CAP = 0.10
N_BENCH = 500


def repaired_capw(i0, uni):
    m = np.log(mcap.iloc[i0].reindex(uni))
    a = np.log(adv.iloc[i0].reindex(uni))
    df = pd.concat([m.rename("m"), a.rename("a")], axis=1) \
        .replace([np.inf, -np.inf], np.nan).dropna()
    if len(df) < 100:
        return None
    A = np.column_stack([np.ones(len(df)), df["a"].values])
    b, *_ = np.linalg.lstsq(A, df["m"].values, rcond=None)
    fit = A @ b
    res = df["m"].values - fit
    z = res / res.std()
    mrep = np.where(np.abs(z) > 2.5, fit, df["m"].values)
    w = pd.Series(np.exp(mrep), index=df.index)
    w = w.nlargest(N_BENCH)
    w = (w / w.sum()).clip(upper=W_CAP)
    return w / w.sum()
os.chdir(HERE.parent)
from filters import Filters                         # noqa: E402
flt = Filters(mdta)
os.chdir(HERE)

# ---- combo panel and its quarterly stamps ----------------------------- #
rv = 1.0 - pd.read_parquet(
    HERE.parent / "reversao_condicional/results/reversal_panel.parquet")
rv = rv.reindex(dates).ffill(limit=75)
ch = pd.read_parquet(HERE / "data/panels/champion_v1.parquet") \
    .reindex(dates)
cols = sorted(set(ch.columns) | set(rv.columns))
combo = pd.concat([
    ch.reindex(columns=cols).rank(axis=1, pct=True),
    rv.reindex(columns=cols).rank(axis=1, pct=True)]) \
    .groupby(level=0).mean()
combo = combo[[c for c in combo.columns if c in mdta.prices.columns]] \
    .reindex(index=dates)
val = combo.notna()
chg = ((combo != combo.shift(1)) & val & val.shift(1)).sum(axis=1)
appeared = (val & ~val.shift(1).fillna(False)).sum(axis=1)
trigger = (val.sum(axis=1) > 40) & ((chg > 20) | (appeared > 100))
idx = np.flatnonzero(trigger.values)
keep = [idx[0]]
for i in idx[1:]:
    if i - keep[-1] > 40:
        keep.append(i)
stamps = np.array(keep)
log(f"{len(stamps)} rebal stamps, {dates[stamps[0]].date()} -> "
    f"{dates[stamps[-1]].date()}")


def run(k: float):
    """Return daily net return series for tilt strength k (k=0 =>
    benchmark itself)."""
    out = []
    prev_w = None
    for j, i0 in enumerate(stamps):
        i1 = stamps[j + 1] if j + 1 < len(stamps) else len(dates) - 1
        u = flt.universe.iloc[i0]
        uni = [c for c in u.index[u > 0] if c in adv.columns]
        wb = repaired_capw(i0, uni)
        if wb is None:
            continue
        r = combo.iloc[i0].reindex(wb.index).rank(pct=True).fillna(0.5)
        w = wb * np.exp(k * 2.0 * (r - 0.5))
        w = w / w.sum()
        # commissions on turnover
        if prev_w is None:
            cost = FEE
        else:
            aligned = pd.concat([prev_w.rename("a"), w.rename("b")],
                                axis=1).fillna(0.0)
            cost = FEE * float((aligned["a"] - aligned["b"]).abs().sum())
        rwin = rets.iloc[i0 + 1:i1 + 1].reindex(columns=w.index) \
            .fillna(0.0)
        pr = rwin @ w.values
        if len(pr):
            pr.iloc[0] -= cost
        out.append(pr)
        prev_w = w
    return pd.concat(out)


def metr(rr, bench=None):
    ann, vol = rr.mean() * 252, rr.std() * np.sqrt(252)
    eq = np.log1p(rr).cumsum()
    dd = float((eq - eq.cummax()).min())
    m = {"ann": ann, "vol": vol, "sharpe": ann / vol, "maxdd": dd}
    if bench is not None:
        d = rr - bench.reindex(rr.index).fillna(0.0)
        te = d.std() * np.sqrt(252)
        eqd = np.log1p(rr).cumsum() - np.log1p(
            bench.reindex(rr.index).fillna(0.0)).cumsum()
        m |= {"exc": d.mean() * 252, "te": te,
              "ir": d.mean() * 252 / te if te > 0 else np.nan,
              "dd_vs_bench": float((eqd - eqd.cummax()).min())}
    return m


bench = run(0.0)
spx = mdta.benchmark_returns.reindex(bench.index).fillna(0.0)
rows = {}
series = {"cap-weighted 500 (S&P proxy)": bench}
for k in (1.0, 2.0, 3.0):
    rr = run(k)
    series[f"combo tilt k={k:.0f}"] = rr
    rows[f"tilt k={k:.0f} vs bench"] = metr(rr, bench)
    rows[f"tilt k={k:.0f} vs SPX"] = metr(rr, spx)
rows["benchmark vs SPX"] = metr(bench, spx)

T = pd.DataFrame(rows).T
T.to_csv(HERE / "results" / "long_only_metrics.csv")
print(T.round(3).to_string())
for nm, rr in series.items():
    key = nm.split()[0] + nm.split()[-1].replace("=", "")
    rr.rename("ret").to_csv(HERE / "data" / "pnl" / f"lo_{key}.csv")

# ---- figure ----------------------------------------------------------- #
plt.rcParams.update({
    "figure.dpi": 150, "savefig.dpi": 200, "font.size": 9,
    "axes.grid": True, "grid.alpha": 0.25, "axes.spines.top": False,
    "axes.spines.right": False, "font.family": "serif",
    "legend.frameon": False})
PAL = ["#7f8c8d", "#1f4e5f", "#c0392b", "#2c6e49", "#444444"]
fig, axes = plt.subplots(2, 1, figsize=(8.0, 5.6), sharex=True,
                         gridspec_kw={"height_ratios": [2.2, 1.0]})
for i, (nm, rr) in enumerate(series.items()):
    axes[0].plot(rr.index, np.log1p(rr).cumsum(), lw=1.1,
                 color=PAL[i % len(PAL)], label=nm)
axes[0].plot(spx.index, np.log1p(spx).cumsum(), lw=1.0, ls="--",
             color=PAL[4], label="S&P 500")
axes[0].set_ylabel("cumulative log return")
axes[0].set_title("Long-only: cap-weighted benchmark tilted by the "
                  "NCB+FSS combo (net of 5 bps/side)")
axes[0].legend(fontsize=8, ncol=2)
for i, k in enumerate((1.0, 2.0, 3.0)):
    rr = series[f"combo tilt k={k:.0f}"]
    d = np.log1p(rr).cumsum() - np.log1p(bench).cumsum()
    axes[1].plot(d.index, d, lw=1.1, color=PAL[i + 1],
                 label=f"k={k:.0f} excess vs benchmark")
axes[1].axhline(0, lw=0.8, color="#333")
axes[1].set_ylabel("log excess vs bench")
axes[1].legend(fontsize=8)
fig.tight_layout()
fig.savefig(PAPER / "figs" / "f11_long_only.png", bbox_inches="tight")
log("done")
