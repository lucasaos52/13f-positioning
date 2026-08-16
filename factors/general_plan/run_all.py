"""One command, whole study: signals -> transforms -> event backtest -> report.

    python run_all.py            # full sample, lags {30,45,60}
    python run_all.py --smoke    # 8 quarters, lag 45 only, no permutations

Produces in results/:
    summary.csv        one row per (factor, lag): spread, NW t, Sharpe, IC,
                       monotonicity, turnover, cost ladder, breakeven bps
    events_*.csv       per-formation-date event tables
    conditional.csv    dACWB quintiles inside Days-ADV terciles (plan's 5x3)
    diagnostics.csv    falsification battery + momentum-overlap measurements
    REPORT.md          the human-readable verdict, written from the numbers

Design choices that need one-line defenses (the memo carries the long form):
  - Coverage boundary: only stocks mappable to a live Yahoo ticker trade;
    the signal is computed on the FULL 13F cross-section, then restricted.
    Survivorship affects returns, not signal construction.
  - w_mkt fallback: instruments without market cap use the aggregate-13F
    weight; the fraction using the fallback is logged each quarter.
  - No overlapping-portfolio machinery: with quarterly formation and
    quarterly holding there is nothing to overlap; the D+30/45/60 grid is
    the timing experiment instead.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))          # factors/ for market_data

import backtest_gp as bt                      # noqa: E402
import diagnostics as dg                      # noqa: E402
import market_cap as mc                       # noqa: E402
import panel as pn                            # noqa: E402
import signals as sg                          # noqa: E402
import transform as tf                        # noqa: E402

RESULTS = HERE / "results"
NB_DATA = HERE.parents[1] / "notebooks" / "data"


def log(msg: str) -> None:
    print(f"{datetime.now():%H:%M:%S} - {msg}", flush=True)


def load_market():
    """Yahoo panels via the factors MarketData (cache lives in factors/data)."""
    os.chdir(HERE.parent)
    from market_data import MarketData
    cmap = (pd.read_csv(NB_DATA / "cm_map_wide.csv", dtype=str)
            .dropna().set_index("instrument_id")["ticker"])
    mdta = MarketData(sorted(cmap.unique()), start="2012-06-01", benchmark="SPY")
    os.chdir(HERE)
    return cmap, mdta


def main(smoke: bool = False) -> None:
    RESULTS.mkdir(exist_ok=True)
    cmap, mdta = load_market()
    dates = mdta.prices.index
    ret = mdta.returns
    cum = ret.cumsum()
    adv = mdta.dollar_volume.rolling(63, min_periods=20).median()
    mom = (cum.shift(21) - cum.shift(252))            # 12-1 momentum
    retq = (cum - cum.shift(63))                      # prior-quarter return

    shares = mc.shares_panel(dates, mdta.tickers, mdta.prices, mdta.prices_raw)
    mcap = mc.mktcap_panel(mdta.prices_raw, shares)
    log(f"mktcap panel: {mcap.shape[1]} tickers")

    meta = pd.read_parquet(pn.QDIR / "filings_meta.parquet")
    all_q = [q for q in pn.quarters()
             if pd.Timestamp("2013-06-30") <= q <= dates[-1] - pd.Timedelta(days=120)]
    if smoke:
        all_q = all_q[-9:]
    lags = [45] if smoke else [30, 45, 60]
    log(f"{len(all_q)} quarters x lags {lags}")

    FACTORS = ["dacwb", "days_adv", "dio", "dnuminst", "pso"]
    events: dict[tuple, list] = {(f, L): [] for f in FACTORS for L in lags}
    members: dict[tuple, tuple[set, set]] = {}
    sig_store: dict[tuple, pd.Series] = {}
    fwd_store: dict[tuple, pd.Series] = {}
    cond_rows, overlap_rows, fallback_frac = [], [], []

    for qi in range(1, len(all_q)):
        p, p_prev = all_q[qi], all_q[qi - 1]
        for L in lags:
            dec = p + pd.Timedelta(days=L)
            if dec >= dates[-1] - pd.Timedelta(days=95):
                continue
            cur = pn.snapshot_as_of(p, dec)
            prev = pn.snapshot_as_of(p_prev, dec)
            if len(cur) < 1000 or len(prev) < 1000:
                continue

            # --- endogenous filer universe ------------------------------ #
            stats = pn.filer_stats(cur)
            turns = []
            snaps = {p: cur, p_prev: prev}
            for k in range(1, 5):
                if qi - k < 1:
                    break
                a_, b_ = all_q[qi - k], all_q[qi - k - 1] if qi - k - 1 >= 0 else None
                if b_ is None:
                    break
                for x in (a_, b_):
                    if x not in snaps:
                        snaps[x] = pn.snapshot_as_of(x, dec)
                turns.append(pn.turnover(snaps[a_], snaps[b_]))
            turn4 = (pd.concat(turns, axis=1).mean(axis=1)
                     if turns else pd.Series(dtype=float))
            hist = (meta[meta["filing_date"] <= dec]
                    .groupby("filer_id")["period_end"].nunique())
            elig = pn.universe_mask(stats, turn4, hist)
            if elig.sum() < 50:
                # too few eligible managers for a crowd signal (early ramp-up
                # quarters where turnover history is not yet computable)
                continue
            conv = (stats["hhi_norm"] / stats["hhi_norm"].median()).clip(upper=1.0)

            # --- per-instrument market context at dec ------------------- #
            di = dates.searchsorted(dec, side="right") - 1
            px_raw = mdta.prices_raw.iloc[di]
            mcap_d = mcap.iloc[di] if len(mcap) else pd.Series(dtype=float)
            adv_d = adv.iloc[di]
            inst = cur.groupby("instrument_id")["value_usd"].sum()
            tick = inst.index.to_series().map(cmap)

            mcap_i = tick.map(mcap_d)
            agg_w = inst / inst.sum()
            w_mkt = (mcap_i / mcap_d.sum()).fillna(agg_w)
            fallback_frac.append({"period": p, "lag": L,
                                  "frac_fallback": float(mcap_i.isna().mean())})
            # quarter stock return prev-end -> decision date (drift r_j)
            i_prev = dates.searchsorted(p_prev, side="right") - 1
            r_q = tick.map(cum.iloc[di] - cum.iloc[i_prev]).fillna(0.0)

            # --- signals ------------------------------------------------ #
            acwb = sg.dacwb(cur, prev, elig, conv, w_mkt, r_q)
            dadv = sg.days_adv(cur, tick.map(adv_d).rename("adv"))
            so_i = tick.map(shares.iloc[di] if len(shares) else pd.Series(dtype=float))
            nul = sg.nulls(cur, prev, so_i)

            raw = pd.concat([acwb[["dacwb", "dacwb_nodrift"]], dadv, nul], axis=1)
            raw["ticker"] = raw.index.to_series().map(cmap)
            raw = raw.dropna(subset=["ticker"])
            byt = raw.groupby("ticker").sum(min_count=1)   # share classes -> issuer

            # --- stock universe + controls at dec ----------------------- #
            u = byt.index
            u = u[(px_raw.reindex(u) >= 5.0)]
            advu = adv_d.reindex(u)
            u = u[advu >= advu.quantile(0.20)]
            ctrl = pd.DataFrame({
                "log_mktcap": np.log(mcap_d.reindex(u)),
                "mom_12_1": mom.iloc[di].reindex(u),
                "ret_prev_q": retq.iloc[di].reindex(u)})

            sigs = {}
            for f in FACTORS:
                s = byt.loc[byt.index.isin(u), f]
                sigs[f] = tf.pipeline(s, log_first=f in ("days_adv", "pso"),
                                      controls=ctrl)

            # --- forward window: dec -> next formation ------------------ #
            nxt = p + pd.offsets.QuarterEnd(1) + pd.Timedelta(days=L)
            fwd = bt.forward_return(cum, dates, dec, min(nxt, dates[-1]))
            for f in FACTORS:
                ev = bt.quintile_event(sigs[f], fwd.reindex(sigs[f].index),
                                       mcap_d)
                if not ev:
                    continue
                q5, q1 = ev.pop("_members_q5"), ev.pop("_members_q1")
                key = (f, L, p)
                pkey = (f, L, all_q[qi - 1])
                if pkey in members:
                    o5, o1 = members[pkey]
                    ev["turnover_1s"] = 1 - (len(q5 & o5) + len(q1 & o1)) / max(
                        len(q5) + len(q1), 1)
                members[key] = (q5, q1)
                ev["period"], ev["lag"] = p, L
                events[(f, L)].append(ev)
                if f == "dacwb":
                    sig_store[(L, p)] = sigs[f]
                    fwd_store[(L, p)] = fwd.reindex(sigs[f].index)

            # conditional 5x3: dacwb quintiles inside days_adv terciles
            both = pd.concat([sigs["dacwb"].rename("a"),
                              sigs["days_adv"].rename("c"),
                              fwd.rename("f")], axis=1).dropna()
            if len(both) >= 150:
                both["ct"] = pd.qcut(both["c"], 3, labels=False, duplicates="drop")
                for t in both["ct"].dropna().unique():
                    sub = both[both["ct"] == t]
                    q = pd.qcut(sub["a"], 5, labels=False, duplicates="drop")
                    if q.nunique() == 5:
                        cond_rows.append({
                            "period": p, "lag": L, "adv_tercile": int(t) + 1,
                            "spread": sub["f"][q == 4].mean() - sub["f"][q == 0].mean()})
            ov = dg.momentum_overlap(byt["dacwb"], byt["dacwb_nodrift"],
                                     mom.iloc[di].reindex(byt.index))
            if ov:
                ov.update({"period": p, "lag": L})
                overlap_rows.append(ov)
        log(f"{p.date()} done ({qi}/{len(all_q) - 1})")

    # ---- aggregate ------------------------------------------------------ #
    rows = []
    for (f, L), evs in events.items():
        if not evs:
            continue
        evd = pd.DataFrame(evs)
        evd.to_csv(RESULTS / f"events_{f}_D{L}.csv", index=False)
        res = bt.summarise(evd)
        res.update({"factor": f, "lag": L})
        rows.append(res)
    summary = pd.DataFrame(rows).set_index(["factor", "lag"]).sort_index()
    summary.to_csv(RESULTS / "summary.csv")
    if cond_rows:
        cond = (pd.DataFrame(cond_rows)
                .groupby(["lag", "adv_tercile"])["spread"]
                .agg(["mean", "std", "size"]))
        cond["t"] = cond["mean"] / cond["std"] * np.sqrt(cond["size"])
        cond.to_csv(RESULTS / "conditional.csv")

    # ---- falsification -------------------------------------------------- #
    diag = {}
    L0 = 45 if 45 in lags else lags[0]
    ev_pairs = [(sig_store[k], fwd_store[k]) for k in sorted(sig_store)
                if k[0] == L0]
    if ev_pairs and not smoke:
        diag.update({f"perm_{k}": v for k, v in
                     dg.permutation_pvalue(ev_pairs).items()})
    diag.update({f"lead_{k}": v for k, v in dg.lead_signal_test(
        {k[1]: v for k, v in sig_store.items() if k[0] == L0},
        {k[1]: v for k, v in fwd_store.items() if k[0] == L0}).items()})
    dac_ev = events.get(("dacwb", L0), [])
    if dac_ev:
        diag.update({f"half_{k}": v for k, v in
                     dg.split_halves(pd.DataFrame(dac_ev)).items()})
    if overlap_rows:
        od = pd.DataFrame(overlap_rows)
        diag["corr_dacwb_mom_avg"] = float(od["corr_sig_mom"].mean())
        diag["corr_nodrift_mom_avg"] = float(od["corr_nodrift_mom"].mean())
    diag["w_mkt_fallback_frac_avg"] = float(
        pd.DataFrame(fallback_frac)["frac_fallback"].mean())
    pd.Series(diag).to_csv(RESULTS / "diagnostics.csv")

    # ---- report --------------------------------------------------------- #
    write_report(summary, diag)
    log("done -> results/")


def write_report(summary: pd.DataFrame, diag: dict) -> None:
    lines = ["# general_plan - resultado do estudo", "",
             "Fatores do plano_pesquisa_13F implementados sobre a base 13F "
             "curada, relogio event-driven por filed_date (D+30/45/60), "
             "universo endogeno de gestores, pipeline §4.1 identico para "
             "todos os fatores.", "",
             "## Sumario (spread Q5-Q1 trimestral, EW)", ""]
    cols = [c for c in ("ew_spread_mean_q", "ew_spread_t_nw", "ew_spread_sharpe",
                        "vw_spread_t_nw", "ic_mean", "monotonicity",
                        "turnover_1s", "breakeven_bps") if c in summary.columns]
    lines.append(summary[cols].round(4).to_markdown())
    lines += ["", "## Falsificacao e diagnosticos", ""]
    for k, v in diag.items():
        lines.append(f"- {k}: {v}")
    (RESULTS / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    main(**vars(ap.parse_args()))
