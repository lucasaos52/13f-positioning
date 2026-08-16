"""Bootstrap-robust hyperparameter selection for the champion
(new_conviction), after Oliveira-Guzman-Firoozye (arXiv:2510.12725,
"(Non-Parametric) Bootstrap Robust Optimization for Portfolios and
Trading Strategies").

    python run_hyperopt.py

THE QUESTION THIS ANSWERS IN THE DEFENSE: "why w-quantile 0.90, growth
1.25, min holders 5?" Until now the honest answer was convention.

PROVENANCE FACT, important for interpreting every champion result: the
default (0.90, 1.25, 5) was set A PRIORI and was the ONLY combination
ever run - there was no grid, no tuning, no alternative tried before
this script. The champion's t=+3.4 therefore carries no hyperparameter
selection bias; conversely, nothing guaranteed the default was even a
good point of the surface. This script is the FIRST systematic
exploration, and it replaces convention with a selection *procedure*:

  1. Grid over the three champion hyperparameters that were set by hand:
       w_q   in {0.80, 0.85, 0.90, 0.95}   (conviction = position above
                                            this within-book weight qtile)
       grow  in {1.10, 1.25, 1.50}         (share growth vs split-adj prior)
       n_min in {3, 5, 10}                 (universe: min 13F holders)
     36 configs. LAG=45 and the quintile protocol are deliberately NOT
     in the grid - the clock is justified empirically by ragged_edge and
     quintiles are the project-wide evaluation convention.
  2. IN-SAMPLE (2013Q3..2020Q4): quarterly Q5-Q1 spread series per
     config, identical universe machinery to the canonical champion
     (rerun_champion_expanded: full universe with zeros, theorem
     residualisation on log mktcap + log ADV).
  3. The paper's step: utility (annualised Sharpe) is treated as a
     random variable - moving-block bootstrap (block=4 quarters,
     B=2000) of the IS spread series, with THE SAME bootstrap indices
     for every config (common random numbers, so configs are compared
     on coupled resamples). Selection maximises the 5th PERCENTILE of
     the bootstrap Sharpe distribution, not the point estimate - a
     config only wins by being good across resamples, which is exactly
     the overfitting penalty the paper formalises.
  4. OUT-OF-SAMPLE (2021Q1..): the selected config is FROZEN and
     evaluated. Compared against (a) the config a naive max-IS-Sharpe
     selector picks, (b) the pre-registered hand-set default
     (0.90/1.25/5). Also reported: rank correlation across the 36
     configs between each IS statistic (point Sharpe vs 5th-pct
     Sharpe) and the OOS Sharpe - "which selector ranks configs the
     way the future does".

Honest caveats, pre-registered: with ~30 IS quarters the bootstrap
percentile is itself noisy; and one IS/OOS split is one draw - the OOS
verdict is a check on the *selector*, not a new alpha claim. If the
robust pick lands on (or near) the default, the default stops being
convention and becomes "the robust-selection answer".
"""
from __future__ import annotations

import sys
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sps

ROOT = Path(__file__).resolve().parents[2]
for sub in ("factors", "factors/general_plan", "data-quality-check"):
    sys.path.insert(0, str(ROOT / sub))

import market_cap as mc                             # noqa: E402
import panel as pn                                  # noqa: E402
from backtest_gp import forward_return, nw_tstat    # noqa: E402
from rerun_champion_expanded import (               # noqa: E402
    residualise, split_factor)
from run_all import load_market, log                # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results"
LAG = 45
IS_END = pd.Timestamp("2020-12-31")
WQS = (0.80, 0.85, 0.90, 0.95)
GROWS = (1.10, 1.25, 1.50)
NMINS = (3, 5, 10)
DEFAULT = (0.90, 1.25, 5)
BLOCK, NDRAWS, PCTL = 4, 2000, 5.0


def cfg_name(wq, gr, nm):
    return f"wq{wq:.2f}_gr{gr:.2f}_n{nm}"


def main() -> None:
    RESULTS.mkdir(exist_ok=True)
    cmap, mdta = load_market()
    dates = mdta.prices.index
    cum = mdta.returns.cumsum()
    adv = mdta.dollar_volume.rolling(63, min_periods=20).median()
    shares = mc.shares_panel(dates, mdta.tickers, mdta.prices,
                             mdta.prices_raw)
    mcap = mc.mktcap_panel(mdta.prices_raw, shares)
    configs = list(product(WQS, GROWS, NMINS))
    log(f"{len(configs)} configs")

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
        px, adv_d = mdta.prices_raw.iloc[di], adv.iloc[di]
        mc_d = mcap.iloc[di] if len(mcap) else pd.Series(dtype=float)
        fac_i = split_factor(cur, prev)
        prev_sh = prev.groupby(["filer_id", "instrument_id"])["shares"].sum()

        b = cur.copy()
        tot = b.groupby("filer_id")["value_usd"].transform("sum")
        b["w"] = b["value_usd"] / tot.replace(0, np.nan)
        key = pd.MultiIndex.from_frame(b[["filer_id", "instrument_id"]])
        shp = pd.Series(prev_sh.reindex(key).values, index=b.index)
        fac = b["instrument_id"].map(fac_i).fillna(1.0)
        b["ticker"] = b["instrument_id"].map(cmap)
        growth = pd.Series(np.where(shp.isna(), np.inf,
                                    b["shares"] / (shp * fac)),
                           index=b.index)
        thr = {wq: b.groupby("filer_id")["w"].transform(
            lambda s, q=wq: s.quantile(q)) for wq in WQS}
        n_filers = float(cur["filer_id"].nunique())
        bt = b.dropna(subset=["ticker"])
        n_c = bt.groupby("ticker")["filer_id"].nunique()
        agg13f = bt.groupby("ticker")["value_usd"].sum()
        nxt = qs[qi + 1] + pd.Timedelta(days=LAG) if qi + 1 < len(qs) \
            else dates[-1]
        fwd_all = forward_return(cum, dates, dec, min(nxt, dates[-1]))
        rngq = np.random.default_rng(int(p.value) % (2**32))

        row = {"period": p}
        for wq, gr, nm in configs:
            v = b[(b["w"] >= thr[wq]) & (growth >= gr)].dropna(
                subset=["ticker"])
            nc = v.groupby("ticker")["filer_id"].nunique() / n_filers
            idx_all = n_c.index[n_c >= nm]
            uni = idx_all[pd.Series(idx_all.map(px), index=idx_all) >= 1.0]
            s = nc.reindex(uni).fillna(0.0)
            mcv = pd.Series(uni.map(mc_d), index=uni)
            mcv = mcv.fillna(agg13f.reindex(uni))
            ctrl = pd.DataFrame({
                "lm": np.log(mcv),
                "la": np.log(pd.Series(uni.map(adv_d), index=uni))})
            r = residualise(s.rank(pct=True), ctrl).rank(pct=True)
            df = pd.concat([r.rename("s"),
                            fwd_all.reindex(uni).rename("f")],
                           axis=1).dropna()
            if len(df) < 150:
                row[cfg_name(wq, gr, nm)] = np.nan
                continue
            jit = pd.Series(rngq.uniform(0, 1e-9, len(df)), index=df.index)
            q5 = pd.qcut((df["s"] + jit).rank(), 5, labels=False)
            g = df.groupby(q5)["f"].mean()
            row[cfg_name(wq, gr, nm)] = float(g.get(4, np.nan)
                                              - g.get(0, np.nan))
        rows.append(row)
        log(f"{p.date()}: done ({len(configs)} configs)")

    S = pd.DataFrame(rows).set_index("period").sort_index()
    S.to_csv(RESULTS / "hyperopt_spreads.csv")
    is_mask = S.index <= IS_END
    S_is, S_oos = S[is_mask].dropna(), S[~is_mask].dropna()
    T_is = len(S_is)
    log(f"IS {T_is} quarters, OOS {len(S_oos)} quarters")

    # ---- the paper's step: coupled block-bootstrap Sharpe ------------- #
    rng = np.random.default_rng(20260816)
    n_blocks = int(np.ceil(T_is / BLOCK))
    idxs = np.stack([
        np.concatenate([np.arange(s0, s0 + BLOCK) for s0 in
                        rng.integers(0, T_is - BLOCK + 1, n_blocks)])[:T_is]
        for _ in range(NDRAWS)])
    stats = []
    for c in S.columns:
        x = S_is[c].values
        draws = x[idxs]                                   # NDRAWS x T_is
        sh = draws.mean(axis=1) / draws.std(axis=1, ddof=1) * 2
        o = S_oos[c]
        stats.append({
            "config": c,
            "is_sharpe": float(x.mean() / x.std(ddof=1) * 2),
            "boot_p05": float(np.percentile(sh, PCTL)),
            "boot_p25": float(np.percentile(sh, 25)),
            "boot_p50": float(np.percentile(sh, 50)),
            "oos_sharpe": float(o.mean() / o.std(ddof=1) * 2),
            "oos_t": nw_tstat(o)})
    R = pd.DataFrame(stats).set_index("config")
    R.to_csv(RESULTS / "hyperopt_table.csv")

    pick_naive = R["is_sharpe"].idxmax()
    pick_robust = R["boot_p05"].idxmax()
    name_def = cfg_name(*DEFAULT)
    rc_naive = sps.spearmanr(R["is_sharpe"], R["oos_sharpe"])[0]
    rc_robust = sps.spearmanr(R["boot_p05"], R["oos_sharpe"])[0]

    L = ["# Bootstrap-robust hyperparameter selection for the champion "
         "(arXiv:2510.12725 protocol)", "",
         f"- grid: {len(R)} configs; IS {T_is} quarters "
         f"(<= {IS_END.date()}), OOS {len(S_oos)} quarters; "
         f"block bootstrap block={BLOCK}, B={NDRAWS}, coupled indices",
         "",
         "**Provenance:** the hand-set default (0.90/1.25/5) was fixed "
         "a priori and was the ONLY combination ever run before this "
         "script - no grid, no tuning, no alternatives tried. Every "
         "prior champion t-stat is therefore free of hyperparameter "
         "selection bias; this is the first systematic exploration of "
         "the surface.",
         "", "## Selections", "",
         "| selector | config | IS Sharpe | boot p05 | OOS Sharpe | "
         "OOS t |", "|---|---|---|---|---|---|"]
    for lbl, c in [("naive max-IS-Sharpe", pick_naive),
                   (f"robust max p{PCTL:.0f} (the paper)", pick_robust),
                   ("hand-set default", name_def)]:
        r = R.loc[c]
        L.append(f"| {lbl} | {c} | {r['is_sharpe']:+.2f} | "
                 f"{r['boot_p05']:+.2f} | {r['oos_sharpe']:+.2f} | "
                 f"{r['oos_t']:+.2f} |")
    L += ["", "## Which IS statistic ranks configs the way the "
          "future does?", "",
          f"- rank-corr(IS point Sharpe, OOS Sharpe) across configs: "
          f"{rc_naive:+.3f}",
          f"- rank-corr(boot p05 Sharpe, OOS Sharpe): {rc_robust:+.3f}",
          f"- best OOS config in hindsight: {R['oos_sharpe'].idxmax()} "
          f"({R['oos_sharpe'].max():+.2f})", "",
          "## Full table (sorted by boot p05)", "",
          R.sort_values("boot_p05", ascending=False).round(3)
          .to_markdown()]
    (RESULTS / "HYPEROPT_REPORT.md").write_text("\n".join(L),
                                                encoding="utf-8")
    log("done -> results/")


if __name__ == "__main__":
    main()
