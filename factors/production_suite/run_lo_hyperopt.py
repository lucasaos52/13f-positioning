"""Bootstrap-robust justification of the LO tilt strength k
(arXiv:2510.12725 protocol, third application).

    python run_lo_hyperopt.py

Utility = information ratio of quarterly excess vs the cap-weighted
benchmark (the LO product's objective). Grid k in {0.5,1,1.5,2,3,4};
IS 2013-2020, coupled moving-block bootstrap (block 4, B=2000) of the
IS quarterly excess -> one IR distribution per k (reported as
percentile boxes); frozen; OOS 2021+ IR. Also reported: per-k TE, so
the reader sees what k actually selects.

Expected reading, stated before running: the research says the signal
is one and k only scales exposure, so the IR distributions should
OVERLAP heavily -- in which case k is a client risk-appetite dial
(TE target), not a data-mined parameter, and THAT is the honest
justification. If instead some k dominates the distribution, the
surface says so and the default moves.
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# reuse the LO machinery (module-level build: benchmark, stamps, run)
import run_long_only as LO                          # noqa: E402

PAPER = HERE.parent.parent / "docs" / "paper"
KS = (0.5, 1.0, 1.5, 2.0, 3.0, 4.0)
IS_END = pd.Timestamp("2020-12-31")
BLOCK, NDRAWS, PCTL = 4, 2000, 5.0


def main() -> None:
    bench = LO.run(0.0)
    exq = {}
    for k in KS:
        rr = LO.run(k)
        d = (rr - bench.reindex(rr.index)).dropna()
        exq[k] = d.resample("QE").sum()
    E = pd.DataFrame(exq).dropna()
    E_is, E_oos = E[E.index <= IS_END], E[E.index > IS_END]
    T_is = len(E_is)
    print(f"IS {T_is} quarters, OOS {len(E_oos)}")

    rng = np.random.default_rng(20260816)
    n_blocks = int(np.ceil(T_is / BLOCK))
    idxs = np.stack([
        np.concatenate([np.arange(s0, s0 + BLOCK) for s0 in
                        rng.integers(0, T_is - BLOCK + 1, n_blocks)])[:T_is]
        for _ in range(NDRAWS)])

    dists, rows = {}, []
    for k in KS:
        x = E_is[k].values
        draws = x[idxs]
        ir = draws.mean(axis=1) / draws.std(axis=1, ddof=1) * 2
        dists[k] = ir
        o = E_oos[k]
        rows.append({
            "k": k,
            "is_ir": float(x.mean() / x.std(ddof=1) * 2),
            "p05": float(np.percentile(ir, PCTL)),
            "p50": float(np.percentile(ir, 50)),
            "te_ann": float(E[k].std() * 2),
            "oos_ir": float(o.mean() / o.std(ddof=1) * 2)})
    R = pd.DataFrame(rows).set_index("k")
    R.to_csv(HERE / "results" / "lo_hyperopt.csv")
    print(R.round(3).to_string())

    # ---- figure: one bootstrap distribution per k --------------------- #
    plt.rcParams.update({
        "figure.dpi": 150, "savefig.dpi": 200, "font.size": 9,
        "axes.grid": True, "grid.alpha": 0.25,
        "axes.spines.top": False, "axes.spines.right": False,
        "font.family": "serif", "legend.frameon": False})
    fig, ax = plt.subplots(figsize=(6.8, 3.6))
    ax.boxplot([dists[k] for k in KS], positions=range(len(KS)),
               widths=0.55, showfliers=False,
               medianprops={"color": "#1f4e5f", "lw": 1.4},
               boxprops={"color": "#555"}, whiskerprops={"color": "#555"},
               capprops={"color": "#555"})
    ax.scatter(range(len(KS)), R["oos_ir"], marker="D", s=42,
               color="#c0392b", zorder=5, label="OOS IR (2021--2025)")
    ax.set_xticks(range(len(KS)))
    ax.set_xticklabels([f"k={k:g}\nTE {R.loc[k, 'te_ann']:.1%}"
                        for k in KS], fontsize=8)
    ax.set_ylabel("information ratio vs benchmark")
    ax.set_title("LO tilt strength: bootstrap IR distribution per k "
                 "(IS 2013–2020, B=2,000, coupled) and frozen OOS")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(PAPER / "figs" / "f12_lo_surface.png",
                bbox_inches="tight")
    print("fig saved")


if __name__ == "__main__":
    main()
