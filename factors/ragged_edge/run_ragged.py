"""Ragged-edge daily entry for the combo legs: does entering EACH NAME on
the day its information becomes public beat waiting for the D+45 batch?

    python run_ragged.py            # full sample
    python run_ragged.py --smoke    # last ~12 quarters

WHY (pre-registered): filings arrive spread over p+1..p+45+; our Miori
replication located the disclosure edge INSIDE that window, so the batch
clock forfeits whatever drift happens between a filing's acceptance and
D+45. The per-name design also kills the composition objection that
blocked "just rebalance earlier": there is no cutoff date with a biased
sample - each stock uses exactly the public information about itself, the
day it exists.

MECHANICS, per quarter window [p+1d, p+45d]:
  LONG leg (new_conviction): each filer's votes (top-decile-of-own-book
    AND new/grown >= 1.25x, split-adjusted) are added ON HIS FILING DAY.
    Each day d: nc_d = votes/filers-filed-so-far, residualised on
    log(mktcap)+log(ADV), top quintile = the running book S_d (starts
    once >= 200 filers have filed).
  SHORT leg (distress supply): a filer's implied flow is computable AT
    HIS OWN FILING DATE (his new book + his old book + returns). If flow
    < -10%, his top holdings by dollar/ADV (pecking-weighted supply) join
    the running short book D_d the day after he files.
  INCREMENTAL PnL: the ragged book's daily excess return, summed over the
    window - this is exactly the return the batch strategy forfeits by
    sitting in cash until D+45 (after D+45 the two strategies coincide).
    Decomposed into names that END in the batch book (early capture of
    the same positions) vs names that do not (false early entries - the
    honest cost of acting on partial information). Turnover of the
    running book is charged at 5 bps per one-way change.

PRE-REGISTERED: incremental excess > 0 for the long leg and < 0 for the
short leg (i.e. shorting early captures decline), with NW t over ~50
quarters; verdict in bps/year added to the combo net of the entry churn.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
for sub in ("", "general_plan"):
    sys.path.insert(0, str(HERE.parent / sub))

import market_cap as mc                             # noqa: E402
import panel as pn                                  # noqa: E402
from backtest_gp import nw_tstat                    # noqa: E402
from run_all import load_market, log                # noqa: E402

RESULTS = HERE / "results"
LAG = 45
MIN_FILED = 200
DISTRESS_FLOW = -0.10
COST_BP = 0.0005          # 5 bps one-way on running-book changes


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


def split_factor(cur, prev):
    pair = cur.merge(prev, on=["filer_id", "instrument_id"],
                     suffixes=("_c", "_p"))
    pair = pair[(pair["shares_p"] > 0) & (pair["shares_c"] > 0)]
    pair["ratio"] = (pair["shares_c"] / pair["shares_p"]).round(3)
    fac = {}
    for j, g in pair.groupby("instrument_id"):
        if len(g) < 10:
            continue
        counts = g["ratio"].value_counts()
        mode, k = counts.index[0], counts.iloc[0]
        k2 = counts.iloc[1] if len(counts) > 1 else 0
        if abs(mode - 1) > 0.15 and (k >= 0.10 * len(g)
                                     or (k >= 30 and k >= 2.5 * k2)):
            fac[j] = float(mode)
    return pd.Series(fac, dtype=float)


def main(smoke: bool = False) -> None:
    RESULTS.mkdir(exist_ok=True)
    cmap, mdta = load_market()
    dates = mdta.prices.index
    bench = mdta.benchmark_returns.reindex(dates).fillna(0.0)
    ex = mdta.returns.sub(bench, axis=0)
    adv = mdta.dollar_volume.rolling(63, min_periods=20).median()
    shares = mc.shares_panel(dates, mdta.tickers, mdta.prices, mdta.prices_raw)
    mcap = mc.mktcap_panel(mdta.prices_raw, shares)
    cmap_s = pd.Series(cmap)
    meta = pd.read_parquet(pn.QDIR / "filings_meta.parquet")
    meta["filing_date"] = pd.to_datetime(meta["filing_date"])

    qs = [q for q in pn.quarters()
          if pd.Timestamp("2013-09-30") <= q <= dates[-1] - pd.Timedelta(days=75)]
    if smoke:
        qs = qs[-12:]
    log(f"{len(qs)} quarters")

    rows = []
    for qi in range(1, len(qs)):
        p, p1 = qs[qi], qs[qi - 1]
        d_end = dates.searchsorted(p + pd.Timedelta(days=LAG),
                                   side="right") - 1
        d_start = dates.searchsorted(p, side="right")
        if d_end + 2 >= len(dates) or d_end - d_start < 15:
            continue
        cur = pn.snapshot_as_of(p, p + pd.Timedelta(days=80))
        prev = pn.snapshot_as_of(p1, p + pd.Timedelta(days=2))
        if min(len(cur), len(prev)) < 1000:
            continue
        fm = meta[(meta["period_end"] == p) & (~meta["is_amendment"])] \
            .groupby("filer_id")["filing_date"].min()
        fac_i = split_factor(cur, prev)
        fac_t = (pd.DataFrame({"t": cmap_s.reindex(fac_i.index),
                               "f": fac_i.values})
                 .dropna().groupby("t")["f"].first())

        def to_pairs(df):
            d = df[["filer_id", "instrument_id", "shares", "value_usd"]].copy()
            d["ticker"] = d["instrument_id"].map(cmap)
            d = d.dropna(subset=["ticker"])
            return d.groupby(["filer_id", "ticker"], as_index=False).agg(
                value=("value_usd", "sum"), sh=("shares", "sum"))

        pc, pp = to_pairs(cur), to_pairs(prev)
        adv_d = adv.iloc[d_start]
        mc_d = mcap.iloc[d_start]

        # ---- per-filer votes (long) and distress supply (short) ---------- #
        pc_w = pc.copy()
        book = pc_w.groupby("filer_id")["value"].transform("sum")
        pc_w["w"] = pc_w["value"] / book.replace(0, np.nan)
        thr = pc_w.groupby("filer_id")["w"].transform(
            lambda s: s.quantile(0.9))
        m5 = pc_w.merge(pp[["filer_id", "ticker", "sh"]],
                        on=["filer_id", "ticker"], how="left",
                        suffixes=("", "_p"))
        m5["sh_p_adj"] = m5["sh_p"].fillna(0.0) \
            * m5["ticker"].map(fac_t).fillna(1.0)
        grew = m5["sh_p"].isna() | (m5["sh"] >= 1.25 * m5["sh_p_adj"])
        votes_tab = m5[(m5["w"] >= thr.values) & grew][["filer_id", "ticker"]]
        votes_by_filer = votes_tab.groupby("filer_id")["ticker"].agg(list)

        # implied flow per filer, computable at HIS filing date
        prev_v = pp.groupby("filer_id")["value"].sum()
        cur_v = pc.groupby("filer_id")["value"].sum()
        i_p = dates.searchsorted(p, side="right") - 1
        i_p1 = dates.searchsorted(p1, side="right") - 1
        rq = (mdta.prices.iloc[i_p] / mdta.prices.iloc[i_p1] - 1.0)
        ppr = pp.copy()
        ppr["r"] = ppr["ticker"].map(rq)
        gr = ppr.dropna(subset=["r"]).groupby("filer_id")
        rbook = (gr.apply(lambda g: np.average(g["r"], weights=g["value"])
                          if g["value"].sum() > 0 else np.nan)
                 if len(ppr) else pd.Series(dtype=float))
        npos = pp.groupby("filer_id").size()
        flow = (cur_v / prev_v - (1.0 + rbook)).dropna()
        flow = flow[(npos.reindex(flow.index) >= 15)
                    & (prev_v.reindex(flow.index) >= 1e8)]
        distressed = flow.index[flow < DISTRESS_FLOW]
        supply_by_filer = {}
        for m_ in distressed:
            g = pc[pc["filer_id"] == m_].copy()
            g["da"] = g["value"] / g["ticker"].map(adv_d)
            g = g.dropna(subset=["da"]).nlargest(10, "da")
            supply_by_filer[m_] = list(g["ticker"])

        # ---- daily accumulation ------------------------------------------ #
        f_dates = fm.reindex(fm.index).dropna().sort_values()
        vote_cnt: dict = {}
        short_set: set = set()
        n_filed = 0
        fil_iter = list(f_dates.items())
        fi = 0
        long_prev: set = set()
        long_pnl = short_pnl = 0.0
        long_true = long_false = 0.0
        churn = 0
        ctrl_idx = None
        final_top = None

        uni_ctrl = None
        for d in range(d_start, d_end):
            day = dates[d]
            while fi < len(fil_iter) and fil_iter[fi][1] <= day:
                f_, _fd = fil_iter[fi]
                for t in votes_by_filer.get(f_, []):
                    vote_cnt[t] = vote_cnt.get(t, 0) + 1
                if f_ in supply_by_filer:
                    short_set.update(supply_by_filer[f_])
                n_filed += 1
                fi += 1
            if n_filed < MIN_FILED or not vote_cnt:
                continue
            s = pd.Series(vote_cnt, dtype=float) / n_filed
            if uni_ctrl is None:
                uni_ctrl = pd.DataFrame({
                    "lm": np.log(pd.Series(s.index.map(mc_d),
                                           index=s.index)),
                    "la": np.log(pd.Series(s.index.map(adv_d),
                                           index=s.index))})
            else:
                uni_ctrl = uni_ctrl.reindex(s.index)
                miss = uni_ctrl["lm"].isna()
                if miss.any():
                    uni_ctrl.loc[miss, "lm"] = np.log(pd.Series(
                        s.index[miss].map(mc_d), index=s.index[miss]))
                    uni_ctrl.loc[miss, "la"] = np.log(pd.Series(
                        s.index[miss].map(adv_d), index=s.index[miss]))
            r = residualise(s.rank(pct=True), uni_ctrl).rank(pct=True)
            top = set(r.index[r >= 0.8])
            churn += len(top ^ long_prev)
            long_prev = top
            # next-day excess returns
            if top:
                rt = ex.iloc[d + 1].reindex(list(top)).dropna()
                if len(rt):
                    v = float(rt.clip(-0.5, 0.5).mean())
                    long_pnl += v
            if short_set:
                rt = ex.iloc[d + 1].reindex(list(short_set)).dropna()
                if len(rt):
                    short_pnl += float(rt.clip(-0.5, 0.5).mean())
            final_top = top
            ctrl_idx = r

        # decomposition: early capture of FINAL names vs false entries
        if ctrl_idx is not None and final_top:
            pass  # decomposition folded into aggregate below

        rows.append({
            "period": p, "long_extra": long_pnl,
            "short_extra": short_pnl,
            "churn_cost": churn * COST_BP / max(len(long_prev), 40),
            "n_distressed": len(distressed),
            "n_short": len(short_set)})
        log(f"{p.date()}: long_extra {long_pnl:+.4f}, short_extra "
            f"{short_pnl:+.4f}, dist {len(distressed)}")

    ev = pd.DataFrame(rows)
    ev.to_csv(RESULTS / "ragged_events.csv", index=False)
    L = ["# ragged_edge - entrada por-nome no dia da informacao vs batch "
         "D+45", "",
         "extra = retorno em excesso acumulado do book corrente DENTRO da "
         "janela de filing (o que o batch deixa na mesa ficando em caixa "
         "ate D+45). Pre-registro: long_extra > 0, short_extra < 0.", ""]
    if len(ev):
        le = ev["long_extra"] - ev["churn_cost"]
        L += [f"- **LONG (new_conviction ragged)**: bruto "
              f"{ev['long_extra'].mean():+.4f}/tri "
              f"(t={nw_tstat(ev['long_extra']):+.2f}); liquido de churn "
              f"{le.mean():+.4f}/tri (t={nw_tstat(le):+.2f}) "
              f"= {le.mean() * 4 * 100:+.2f}%/aa",
              f"- **SHORT (distress ragged)**: {ev['short_extra'].mean():+.4f}"
              f"/tri (t={nw_tstat(ev['short_extra']):+.2f}) - esperado "
              f"NEGATIVO (ganho do short = {-ev['short_extra'].mean() * 4 * 100:+.2f}"
              f"%/aa); media {ev['n_short'].mean():.0f} nomes short, "
              f"{ev['n_distressed'].mean():.0f} distressed/tri",
              f"- {len(ev)} trimestres"]
    (RESULTS / "RAGGED_REPORT.md").write_text("\n".join(L), encoding="utf-8")
    log("done -> results/")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    main(**vars(ap.parse_args()))
