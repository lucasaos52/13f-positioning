"""All paper figures. Senior-quant aesthetics: log-scale cumulative
returns, muted palette, subtle grid, no chartjunk, >=150 dpi, English.

    python make_figs.py

Figures that depend on engine PnL dumps (F1, F3, F4) are skipped
gracefully until factors/production_suite/data/pnl/*.csv exist.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
FIGS = HERE / "figs"
DATA = HERE / "data"
FIGS.mkdir(exist_ok=True)

plt.rcParams.update({
    "figure.dpi": 150, "savefig.dpi": 200, "font.size": 9,
    "axes.grid": True, "grid.alpha": 0.25, "grid.linewidth": 0.5,
    "axes.spines.top": False, "axes.spines.right": False,
    "font.family": "serif", "axes.titlesize": 10, "legend.frameon": False,
})
PAL = ["#1f4e5f", "#c0392b", "#7f8c8d", "#2c6e49", "#b8860b", "#5b4a70",
       "#4a7ba6", "#a04000"]


def _save(fig, name):
    fig.tight_layout()
    fig.savefig(FIGS / name, bbox_inches="tight")
    plt.close(fig)
    print("fig:", name)


def f1_engine_curves():
    pnl = ROOT / "factors" / "production_suite" / "data" / "pnl"
    want = {"champion_v1": "NCB (residualized)",
            "new_conviction": "NCB v2 (catalogue spec)",
            "dbreadth_common": "dBreadth (common filers)",
            "combo": "NCB+FSS book",
            "fm_score": "FM score (10 predictors)",
            "distress_mom": "FSS short leg"}
    have = {k: v for k, v in want.items() if (pnl / f"{k}.csv").exists()}
    if not have:
        print("F1 skipped (no engine pnl yet)")
        return
    fig, ax = plt.subplots(figsize=(8.2, 4.4))
    for i, (k, lbl) in enumerate(have.items()):
        rr = pd.read_csv(pnl / f"{k}.csv", index_col=0, parse_dates=True)
        rr = rr.iloc[:, 0]
        ax.plot(rr.index, np.log1p(rr).cumsum(), lw=1.1,
                color=PAL[i % len(PAL)], label=lbl)
    spx = _spx()
    if spx is not None:
        ax.plot(spx.index, spx, lw=1.0, ls="--", color="#444",
                label="S&P 500 (unhedged, reference)")
    ax.set_ylabel("cumulative log net return")
    ax.set_title("Net long-short performance, production engine "
                 "(5 bps/side commissions, 50 bps p.a. borrow)")
    ax.legend(fontsize=8, ncol=2)
    _save(fig, "f1_engine_curves.png")


def _spx():
    try:
        import sys
        sys.path.insert(0, str(ROOT / "factors" / "general_plan"))
        from run_all import load_market
        _, mdta = load_market()
        b = mdta.benchmark_returns.dropna()
        return np.log1p(b).cumsum()
    except Exception as e:
        print("no spx:", e)
        return None


def f2_combiner_race():
    r = pd.read_csv(ROOT / "factors/score_model/results/race_events.csv",
                    parse_dates=["period"]).set_index("period")
    i = pd.read_csv(ROOT / "factors/ipca/results/ipca_oos.csv",
                    parse_dates=["period"]).set_index("period")
    fig, ax = plt.subplots(figsize=(7.6, 4.0))
    series = [("spread_A_fm", "A: Fama-MacBeth / Lewellen", r, 0),
              ("spread_B_ic", "B: IC-weighted (Grinold-Kahn)", r, 2),
              ("spread_C_naive", "C: naive rank average", r, 4),
              ("spread_u", "IPCA(K=3) + alpha (candidate)", i, 1)]
    for col, lbl, df, ci in series:
        s = df[col].dropna()
        ax.plot(s.index, np.log1p(s).cumsum(), lw=1.2, color=PAL[ci],
                label=lbl)
    ax.set_ylabel("cumulative log quintile spread (quarterly, gross)")
    ax.set_title("Expected-return combiners, strictly expanding "
                 "out-of-sample")
    ax.legend(fontsize=8)
    _save(fig, "f2_combiner_race.png")


def f6_mechanism():
    m = pd.read_csv(ROOT / "factors/distress_hyperopt/results/"
                    "dh_mechanism.csv", parse_dates=["period"])
    thrs = [-0.05, -0.075, -0.10, -0.15, -0.20]
    means = [m[f"sold_{t:+.3f}"].mean() for t in thrs]
    healthy = m["sold_healthy"].mean()
    fig, ax = plt.subplots(figsize=(5.6, 3.4))
    ax.plot([abs(t) * 100 for t in thrs], [v * 100 for v in means],
            marker="o", ms=4, lw=1.2, color=PAL[0],
            label="distressed (flow < threshold)")
    ax.axhline(healthy * 100, ls="--", lw=1.0, color=PAL[1],
               label="healthy managers (flow > 0)")
    ax.axvline(10, ls=":", lw=0.9, color="#666")
    ax.text(10.3, healthy * 100 + 1, "default (−10%)", fontsize=8,
            color="#444")
    ax.set_xlabel("implied-flow threshold (%, absolute)")
    ax.set_ylabel("shares sold next quarter (%)")
    ax.set_title("Forced-sale mechanism is monotone in the threshold")
    ax.legend(fontsize=8)
    _save(fig, "f6_mechanism.png")


def f7_surfaces():
    ch = pd.read_csv(ROOT / "factors/champion_hyperopt/results/"
                     "hyperopt_table.csv").set_index("config")
    dh = pd.read_csv(ROOT / "factors/distress_hyperopt/results/"
                     "dh_table.csv").set_index("config")
    fig, axes = plt.subplots(1, 2, figsize=(8.4, 3.6))
    for ax, df, dflt, ttl in [
            (axes[0], ch, "wq0.90_gr1.25_n5",
             "NCB surface (36 configs): IS ranks OOS"),
            (axes[1], dh, "thr-0.100_top20",
             "FSS surface (15 configs): regime flip")]:
        ax.scatter(df["is_sharpe"], df["oos_sharpe"], s=18, alpha=0.8,
                   color=PAL[0])
        d = df.loc[dflt]
        ax.scatter([d["is_sharpe"]], [d["oos_sharpe"]], s=60, marker="D",
                   color=PAL[1], zorder=5, label="a-priori default")
        ax.set_xlabel("in-sample Sharpe (2013–2020)")
        ax.set_ylabel("OOS Sharpe (2021–2025)")
        ax.set_title(ttl)
        ax.legend(fontsize=8)
    _save(fig, "f7_surfaces.png")


def f8_ic_bars():
    s = pd.read_csv(ROOT / "factors/general_predictive_signals/results/"
                    "signals_summary.csv")
    s = s[s["headline"]].sort_values("ic", ascending=True)
    fig, ax = plt.subplots(figsize=(6.4, 4.6))
    colors = [PAL[0] if v > 0 else PAL[2] for v in s["ic"]]
    ax.barh(s["signal"], s["ic"], color=colors, height=0.62)
    ax.axvline(0, lw=0.8, color="#333")
    ax.set_xlabel("mean Spearman IC vs next-quarter return")
    ax.set_title("Signal catalogue: information coefficients "
                 "(headline versions, fixed ex ante)")
    _save(fig, "f8_ic_bars.png")


def f9_delays():
    f = DATA / "filing_delays.csv"
    if not f.exists():
        print("F9 skipped")
        return
    d = pd.read_csv(f)["delay_days"]
    fig, ax = plt.subplots(figsize=(5.8, 3.2))
    ax.hist(d.clip(0, 120), bins=60, color=PAL[0], alpha=0.85)
    ax.axvline(45, ls="--", lw=1.1, color=PAL[1])
    ax.text(46, ax.get_ylim()[1] * 0.9, "D+45 statutory deadline",
            fontsize=8, color=PAL[1])
    ax.set_xlabel("filing delay after quarter end (days, clipped at 120)")
    ax.set_ylabel("filings")
    ax.set_title("When 13F information actually becomes public")
    _save(fig, "f9_delays.png")


def f10_universe():
    f1_, f2_ = DATA / "manager_count.csv", DATA / "etf_share.csv"
    if not (f1_.exists() and f2_.exists()):
        print("F10 skipped")
        return
    mc = pd.read_csv(f1_, parse_dates=["period"])
    es = pd.read_csv(f2_, parse_dates=["period"])
    fig, axes = plt.subplots(1, 2, figsize=(8.4, 3.0))
    axes[0].plot(mc["period"], mc["n_filers"], lw=1.2, color=PAL[0])
    axes[0].set_title("13F filers per quarter (census)")
    axes[1].plot(es["period"], es["etf_share"] * 100, lw=1.2, color=PAL[1])
    axes[1].set_title("ETF lines as % of reported book value")
    axes[1].set_ylabel("%")
    _save(fig, "f10_universe.png")


DISPLAY = {"champion_v1": "NCB", "new_conviction": "NCB v2",
           "conviction_top": "conviction top", "dbreadth_common":
           "dBreadth common", "net_entry": "net entry", "entry_rate":
           "entry rate", "days_adv": "days-ADV", "d_days_adv":
           "d(days-ADV)", "herf_holders": "holder HHI", "pso":
           "pct shares held", "dio": "dIO", "breadth_level":
           "breadth level", "ica_rev": "ICA reversal", "ica_comb":
           "ICA combined", "nmf_crowd": "NMF crowding", "ssi": "SSI",
           "copycat_flow": "copycat flow"}


def f3_class_curves():
    pnl = ROOT / "factors" / "production_suite" / "data" / "pnl"
    classes = {
        "A. Conviction / positioning changes":
            ["champion_v1", "new_conviction", "conviction_top",
             "dbreadth_common", "net_entry", "entry_rate"],
        "C. Crowding / ownership states":
            ["days_adv", "d_days_adv", "herf_holders", "pso", "dio",
             "breadth_level"],
        "E. Latent structure / flows":
            ["ica_rev", "ica_comb", "nmf_crowd", "ssi", "copycat_flow"],
    }
    if not pnl.exists():
        print("F3 skipped")
        return
    fig, axes = plt.subplots(1, 3, figsize=(10.5, 3.4), sharey=True)
    for ax, (ttl, names) in zip(axes, classes.items()):
        for i, n in enumerate(names):
            f = pnl / f"{n}.csv"
            if not f.exists():
                continue
            rr = pd.read_csv(f, index_col=0, parse_dates=True).iloc[:, 0]
            ax.plot(rr.index, np.log1p(rr).cumsum(), lw=0.9,
                    color=PAL[i % len(PAL)], label=DISPLAY.get(n, n))
        ax.set_title(ttl, fontsize=9)
        ax.legend(fontsize=6.5)
    axes[0].set_ylabel("cumulative log net return")
    _save(fig, "f3_class_curves.png")


if __name__ == "__main__":
    for fn in (f2_combiner_race, f6_mechanism, f7_surfaces, f8_ic_bars,
               f9_delays, f10_universe, f1_engine_curves, f3_class_curves):
        try:
            fn()
        except Exception as e:
            print(f"{fn.__name__} FAILED: {e}")
