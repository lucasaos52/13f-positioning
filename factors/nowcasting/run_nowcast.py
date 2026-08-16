"""The nowcasting study, end to end.

    python run_nowcast.py            # full
    python run_nowcast.py --smoke    # last 10 quarters

Five experiments, each mapped to a section of plano_nowcasting_13F and each
with a published number to compare against:

  X1  The accounting table (§2, §6.1): R^2 of LEVELS under pure persistence
      (literature: ~99% - "levels are trivial"), vs the same statistic on
      DELTAS. Establishes on OUR data why the target must be the change.
  X2  Nested baselines (§6.2, models 0/1): predict next-quarter dIO with
      zero (persistence) and with an EMA of past discretionary changes.
      Literature: EMA adds almost nothing (NAVIS: heuristics ~0.889 NDCG,
      ML +2.4 points); Barardehi et al.: the best DAILY proxy in existence
      reaches only 13.8% OOS R^2. Our EMA should land in low single digits.
  X3  The ragged edge as information (§1, layer-2 anchor y5): at D+15/30/
      45/60, use the dIO already REVEALED by early filers to nowcast the
      final dIO. Two estimators: revealed-only, and revealed scaled up by
      1/coverage. This is the plan's "borda irregular vira parte do modelo",
      with the information-accumulation curve as the deliverable.
  X4  E1-lite (§7): does the PIT-legal early-revealed dIO predict returns
      from d to quarter+75d? Christoffersen-Danesh-Musto predict ~nothing
      (institutions don't fear copycats). A null here is a result.
  X5  NDCG replication (§3.6): persistence and EMA heuristics scored with
      NDCG@10 on a NAVIS-like universe (top ~99 eligible managers, large-cap
      names). Published: persistent 0.8891, EMA 0.8882, best ML 0.9127.
      Landing near 0.89 validates our panel against the benchmark's.
  X6  E3 (§7): real-time Days-ADV from the mixed-vantage (ragged) panel vs
      the stale uniform-lag version: rank correlation and decile migration.
      The case for nowcasting as RISK tool, where order of magnitude beats
      precision.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))            # factors/ (market_data)
sys.path.insert(0, str(HERE.parent / "general_plan"))

import panel as pn                               # noqa: E402
import market_cap as mc                          # noqa: E402
from nowcast_lib import (filed_sets, hit_rate, io_by_stock, log, ndcg_at_k,
                         r2_oos, rank_ic, weights_matrix)  # noqa: E402

RESULTS = HERE / "results"
NB_DATA = HERE.parents[1] / "notebooks" / "data"
HORIZONS = [15, 30, 45, 60]


def load_market():
    import os
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
    cum = mdta.returns.cumsum()
    adv = mdta.dollar_volume.rolling(63, min_periods=20).median()
    shares = mc.shares_panel(dates, mdta.tickers, mdta.prices, mdta.prices_raw)
    meta = pd.read_parquet(pn.QDIR / "filings_meta.parquet")

    qs = [q for q in pn.quarters()
          if pd.Timestamp("2013-06-30") <= q <= dates[-1] - pd.Timedelta(days=100)]
    if smoke:
        qs = qs[-11:]
    log(f"{len(qs)} quarters")

    FULL = pd.Timedelta(days=75)     # "all filings in" vantage
    rows_x1, rows_x23, rows_x4, rows_x5, rows_x6 = [], [], [], [], []
    dio_hist: dict[pd.Timestamp, pd.Series] = {}

    for qi in range(2, len(qs) - 1):
        p_prev, p, p_next = qs[qi - 1], qs[qi], qs[qi + 1]
        snap_prev = pn.snapshot_as_of(p_prev, p_prev + FULL)
        snap_cur = pn.snapshot_as_of(p, p + FULL)
        snap_next = pn.snapshot_as_of(p_next, p_next + FULL)
        if min(len(snap_prev), len(snap_cur), len(snap_next)) < 1000:
            continue

        # IO in ratio units; EVERY ratio uses the shares outstanding of its
        # own reference date, so splits cancel inside each ratio and deltas
        # across quarters are split-invariant with no adjustment machinery
        di_pp = dates.searchsorted(p_prev, side="right") - 1
        di_p = dates.searchsorted(p, side="right") - 1
        di_n = dates.searchsorted(p_next, side="right") - 1
        so_pp = shares.iloc[di_pp] if len(shares) else pd.Series(dtype=float)
        so_p = shares.iloc[di_p] if len(shares) else pd.Series(dtype=float)
        so_n = shares.iloc[di_n] if len(shares) else pd.Series(dtype=float)

        def io_ratio(snap, so_row, filers=None):
            sh = io_by_stock(snap, filers)
            t = sh.index.to_series().map(cmap)
            so = t.map(so_row)
            io = (sh / so).replace([np.inf, -np.inf], np.nan).dropna()
            return io[(io > 0) & (io < 1.5)]   # IO>150% = SO glitch, drop loud

        io_prev = io_ratio(snap_prev, so_pp)
        io_cur = io_ratio(snap_cur, so_p)
        io_next = io_ratio(snap_next, so_n)
        common = io_cur.index.intersection(io_next.index)
        if len(common) < 200:
            continue
        dio_next = (io_next - io_cur).reindex(common).dropna()   # target
        dio_cur = (io_cur - io_prev).reindex(common).dropna()    # last known
        dio_hist[p] = dio_cur

        # ---- X1: levels vs deltas ------------------------------------- #
        rows_x1.append({
            "period": p,
            "r2_level_persist": r2_oos(io_next.reindex(common),
                                       io_cur.reindex(common)),
            "sd_level": float(io_next.reindex(common).std()),
            "sd_dio": float(dio_next.std()),
        })

        # ---- X2: nested baselines on dIO ------------------------------ #
        hist = [dio_hist[q] for q in qs[max(2, qi - 4):qi] if q in dio_hist]
        if len(hist) >= 2:
            # manual EMA over past dIO series (alpha=0.5, most recent last)
            wts = np.array([0.5 ** (len(hist) - 1 - k) for k in range(len(hist))])
            wts /= wts.sum()
            ema = sum(w * h.reindex(common).fillna(0.0)
                      for w, h in zip(wts, hist))
        else:
            ema = dio_cur
        rows_x23.append({
            "period": p, "model": "ema_disc",
            "r2": r2_oos(dio_next, ema.reindex(common)),
            "ic": rank_ic(dio_next, ema.reindex(common)),
            "hit": hit_rate(dio_next, ema.reindex(common))})
        rows_x23.append({
            "period": p, "model": "last_dio",
            "r2": r2_oos(dio_next, dio_cur),
            "ic": rank_ic(dio_next, dio_cur),
            "hit": hit_rate(dio_next, dio_cur)})

        # ---- X3: ragged-edge anchor + X4: E1-lite ---------------------- #
        for h in HORIZONS:
            d = p_next + pd.Timedelta(days=h)
            F = filed_sets(meta, p_next, d)
            if not F:
                continue
            # coverage = share of PRIOR-quarter aggregate book already filed
            cov_num = snap_cur[snap_cur["filer_id"].isin(F)]["value_usd"].sum()
            cov = cov_num / snap_cur["value_usd"].sum()
            snap_next_d = pn.snapshot_as_of(p_next, d)
            rev_next = io_ratio(snap_next_d, so_n, F)
            rev_cur = io_ratio(snap_cur, so_p, F)
            d_rev = (rev_next - rev_cur).reindex(common).fillna(0.0)
            # winsorised R^2: SO glitches in single names dominate SSE and
            # mask an anchor whose RANK information is excellent; both views
            # reported, neither silently
            w_t = dio_next.clip(dio_next.quantile(0.01), dio_next.quantile(0.99))
            for name, pred in [("revealed", d_rev),
                               ("revealed_scaled", d_rev / max(cov, 0.15))]:
                w_p = pred.clip(pred.quantile(0.01), pred.quantile(0.99))
                rows_x4.append({
                    "period": p_next, "h": h, "model": name, "coverage": cov,
                    "r2": r2_oos(dio_next, pred),
                    "r2_wins": r2_oos(w_t, w_p.reindex(w_t.index)),
                    "ic": rank_ic(dio_next, pred),
                    "hit": hit_rate(dio_next, pred)})
            # E1-lite: early-revealed dIO -> return d .. p_next+75d (PIT)
            i0 = dates.searchsorted(d, side="right")
            i1 = dates.searchsorted(p_next + FULL, side="right") - 1
            if 0 < i0 < i1:
                fwd = cum.iloc[i1] - cum.iloc[i0 - 1]
                sig = d_rev[d_rev != 0]
                # instrument -> ticker (returns are ticker-indexed)
                sig = (sig.groupby(sig.index.to_series().map(cmap)).sum()
                       .dropna())
                df = pd.concat([sig.rename("s"), fwd.reindex(sig.index)
                                .rename("f")], axis=1).dropna()
                if len(df) >= 100:
                    q = pd.qcut(df["s"].rank(method="first"), 5, labels=False)
                    rows_x5.append({
                        "period": p_next, "h": h,
                        "spread": df["f"][q == 4].mean() - df["f"][q == 0].mean(),
                        "n": len(df)})

        # ---- X6: real-time vs stale Days-ADV --------------------------- #
        for h in (15, 45):
            d = p_next + pd.Timedelta(days=h)
            di = dates.searchsorted(d, side="right") - 1
            if di <= 0 or di >= len(dates):
                continue
            F = filed_sets(meta, p_next, d)
            snap_next_d = pn.snapshot_as_of(p_next, d)
            fresh = snap_next_d[snap_next_d["filer_id"].isin(F)]
            lagg = snap_cur[~snap_cur["filer_id"].isin(F)]
            mixed_sh = pd.concat([fresh, lagg]).groupby("instrument_id")["shares"].sum()
            stale_sh = snap_cur.groupby("instrument_id")["shares"].sum()
            t_m = mixed_sh.index.to_series().map(cmap)
            px, av = mdta.prices_raw.iloc[di], adv.iloc[di]
            da_rt = (mixed_sh * t_m.map(px)) / t_m.map(av)
            t_s = stale_sh.index.to_series().map(cmap)
            da_st = (stale_sh * t_s.map(px)) / t_s.map(av)
            both = pd.concat([da_rt.rename("rt"), da_st.rename("st")],
                             axis=1).dropna()
            both = both[(both > 0).all(axis=1)]
            if len(both) < 200:
                continue
            r_rt = both["rt"].rank(pct=True)
            r_st = both["st"].rank(pct=True)
            rows_x6.append({
                "period": p_next, "h": h,
                "rank_corr": float(r_rt.corr(r_st)),
                "migr_2dec": float(((r_rt - r_st).abs() > 0.2).mean()),
                "n": len(both)})
        log(f"{p.date()} done")

    # ---- X5-NDCG: heuristics on two NAVIS-like universes ----------------- #
    # NAVIS used "99 managers" without disclosing selection. Manager TYPE
    # drives persistence, so we score BOTH: the 99 biggest books (passive-
    # heavy: Vanguard-like, maximally persistent) and the 99 biggest ACTIVE
    # books (the plan's endogenous filter, minus the turnover cut which
    # needs history) - the user's emphasis: the informative universe is the
    # active one, and it should be strictly harder to predict.
    ndcg_rows = []
    stats_last = pn.filer_stats(pn.snapshot_as_of(qs[-2], qs[-2] + FULL))
    act = stats_last[stats_last["n_pos"].between(15, 200)
                     & (stats_last["hhi_norm"] > stats_last["hhi_norm"].median())
                     & (stats_last["aum"] > 250e6)]
    panels = {"mega": stats_last.nlargest(150, "aum").index.tolist(),
              "active": act.nlargest(150, "aum").index.tolist()}
    for pane, mgr_pool in panels.items():
        for qi in range(3, len(qs) - 1):
            p_prev, p, p_next = qs[qi - 1], qs[qi], qs[qi + 1]
            W_prev = weights_matrix(pn.snapshot_as_of(p_prev, p_prev + FULL), mgr_pool)
            W_cur = weights_matrix(pn.snapshot_as_of(p, p + FULL), mgr_pool)
            W_next = weights_matrix(pn.snapshot_as_of(p_next, p_next + FULL), mgr_pool)
            mgrs = W_cur.index.intersection(W_next.index)[:99]
            for m in mgrs:
                true_w = W_next.loc[m].dropna()
                pers = W_cur.loc[m].dropna()
                ndcg_rows.append({"period": p_next, "panel": pane,
                                  "model": "persist",
                                  "ndcg": ndcg_at_k(true_w, pers)})
                if m in W_prev.index:
                    ema_w = 0.7 * pers + 0.3 * W_prev.loc[m].reindex(
                        pers.index).fillna(0.0)
                    ndcg_rows.append({"period": p_next, "panel": pane,
                                      "model": "ema",
                                      "ndcg": ndcg_at_k(true_w, ema_w)})
            if smoke and qi > 6:
                break

    # ---- write ----------------------------------------------------------- #
    x1 = pd.DataFrame(rows_x1)
    x23 = pd.DataFrame(rows_x23)
    x4 = pd.DataFrame(rows_x4)
    x5 = pd.DataFrame(rows_x5)
    x6 = pd.DataFrame(rows_x6)
    nd = pd.DataFrame(ndcg_rows)
    for name, df in [("x1_levels", x1), ("x2_baselines", x23),
                     ("x3_anchor", x4), ("x4_e1_returns", x5),
                     ("x6_crowding_rt", x6), ("x5_ndcg", nd)]:
        df.to_csv(RESULTS / f"{name}.csv", index=False)
    write_report(x1, x23, x4, x5, x6, nd)
    log("done -> results/")


def write_report(x1, x23, x4, x5, x6, nd) -> None:
    L = ["# nowcasting - resultados vs literatura", ""]
    if len(x1):
        L += [f"## X1 Niveis vs variacoes (§2)",
              f"- R2 do NIVEL sob persistencia pura: media "
              f"**{x1.r2_level_persist.mean():.4f}** (literatura: ~0,99 - "
              f"'niveis sao triviais')",
              f"- desvio do nivel {x1.sd_level.mean():.4f} vs desvio do dIO "
              f"{x1.sd_dio.mean():.4f}", ""]
    if len(x23):
        g = x23.groupby("model")[["r2", "ic", "hit"]].mean()
        L += ["## X2 Baselines aninhados no dIO (§6.2)",
              g.round(4).to_markdown(),
              "", "Literatura: melhor proxy diario existente (lendable) = "
              "13,8% OOS; heuristicas de nivel nao ajudam no delta; hit "
              "rate esperado 52-58%.", ""]
    if len(x4):
        g = (x4.groupby(["model", "h"])[["r2", "r2_wins", "ic", "hit",
                                         "coverage"]].mean().round(4))
        L += ["## X3 Borda irregular como informacao (ancora y5)",
              g.to_markdown(), "",
              "R2 cresce com h porque a cobertura dos filers revelados "
              "cresce - a curva de acumulacao de informacao do filing "
              "season.", ""]
    if len(x5):
        g = x5.groupby("h")["spread"].agg(["mean", "std", "size"])
        g["t"] = g["mean"] / g["std"] * np.sqrt(g["size"])
        L += ["## X4 E1-lite: dIO revelado cedo preve retorno? (PIT)",
              g.round(4).to_markdown(), "",
              "Christoffersen-Danesh-Musto preveem ~nada; um nulo aqui e "
              "resultado, nao fracasso.", ""]
    if len(nd):
        g = nd.groupby(["panel", "model"])["ndcg"].agg(["mean", "count"])
        L += ["## X5 NDCG@10 das heuristicas (replica §3.6)",
              g.round(4).to_markdown(), "",
              "Publicado: persistent 0,8891 | EMA 0,8882 | melhor ML 0,9127. "
              "Aterrissar perto de 0,89 valida o painel; o ganho do ML "
              "publicado e de 2,4 pontos - o argumento para NAO treinar "
              "grafos aqui.", ""]
    if len(x6):
        g = x6.groupby("h")[["rank_corr", "migr_2dec"]].mean()
        L += ["## X6 E3: Days-ADV tempo real vs defasado",
              g.round(4).to_markdown(), "",
              "migr_2dec = fracao dos nomes cujo rank de crowding muda mais "
              "de 2 decis quando medido em tempo real - o valor do nowcast "
              "como ferramenta de RISCO.", ""]
    (RESULTS / "REPORT.md").write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    main(**vars(ap.parse_args()))
