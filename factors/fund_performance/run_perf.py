"""Descriptive: historical performance of the FUNDS themselves - the
synthetic disclosed-book excess return and information ratio per filer.

    python run_perf.py

Not a signal test. For each filer and quarter: freeze the PRIOR disclosed
book, value-weight its price return over the quarter, subtract the S&P
proxy -> quarterly excess. Per filer with >= 12 quarters: annualized
excess, tracking error, IR (annualized, x sqrt(4)). Outputs:
  - fund_performance.csv (one row per filer)
  - PERF_REPORT.md: distribution, top/bottom 20 (min 20 quarters,
    >= $250M median book), and the split-half persistence check
    (IR 2013-2019 vs 2019-2026) - the number that explains why every
    smart-money strategy died.
Caveat printed in the report: this is the DISCLOSED LONG BOOK only (no
shorts/cash/derivatives/intra-quarter trading) and the price panel lacks
delisted names (survivorship makes everyone look slightly better).
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
for sub in ("", "general_plan"):
    sys.path.insert(0, str(HERE.parent / sub))

import market_cap as mc                             # noqa: E402
import panel as pn                                  # noqa: E402
from run_all import load_market, log                # noqa: E402

RESULTS = HERE / "results"
MIN_COVER = 0.5
MIN_Q = 12
SPLIT = pd.Timestamp("2019-06-30")


def main() -> None:
    RESULTS.mkdir(exist_ok=True)
    cmap, mdta = load_market()
    dates = mdta.prices.index
    cum = mdta.returns.cumsum()
    bench = mdta.benchmark_returns.reindex(dates).fillna(0.0).cumsum()

    qs = [q for q in pn.quarters()
          if pd.Timestamp("2013-06-30") <= q <= dates[-1] - pd.Timedelta(days=10)]
    log(f"{len(qs)} quarters")

    shares_p = mc.shares_panel(dates, mdta.tickers, mdta.prices,
                               mdta.prices_raw)
    mcap = mc.mktcap_panel(mdta.prices_raw, shares_p)

    hist: dict = defaultdict(dict)      # filer -> {period: excess}
    aums: dict = defaultdict(list)
    acts: dict = defaultdict(list)      # active share per quarter
    turns: dict = defaultdict(list)     # 0.5*sum|dw| vs prior book
    nposs: dict = defaultdict(list)
    prev_w: dict = {}                   # filer -> value weights (instrument)
    for qi in range(1, len(qs)):
        p, p1 = qs[qi], qs[qi - 1]
        dec = p + pd.Timedelta(days=50)
        cur = pn.snapshot_as_of(p1, min(dec, dates[-1] - pd.Timedelta(days=1)))
        if len(cur) < 1000:
            continue
        di_p = dates.searchsorted(p, side="right") - 1
        di_p1 = dates.searchsorted(p1, side="right") - 1
        if di_p <= di_p1:
            continue
        ret_q = cum.iloc[di_p] - cum.iloc[di_p1]
        mret = float(bench.iloc[di_p] - bench.iloc[di_p1])
        b = cur[["filer_id", "instrument_id", "value_usd"]].copy()
        b["ticker"] = b["instrument_id"].map(cmap)
        b["r"] = b["ticker"].map(ret_q)
        g = b.groupby("filer_id")
        tot = g["value_usd"].sum()
        cov = b.assign(v=b["value_usd"].where(b["r"].notna(), 0.0)) \
            .groupby("filer_id")["v"].sum() / tot.clip(lower=1.0)
        vr = b.assign(vr=b["value_usd"] * b["r"].fillna(0.0)) \
            .groupby("filer_id")["vr"].sum()
        rbook = vr / tot.clip(lower=1.0)
        ok = cov.index[(cov >= MIN_COVER) & (g.size() >= 10)]
        # active share vs VW market (mapped tickers, renormalized) and
        # turnover 0.5*sum|w - w_prev| (value weights, instrument level)
        di_now = dates.searchsorted(p1, side="right") - 1
        mc_d = mcap.iloc[di_now]
        bw = mc_d / mc_d.sum()
        bm = b.dropna(subset=["ticker"])
        cur_w: dict = {}
        for m, gg in bm[bm["filer_id"].isin(ok)].groupby("filer_id"):
            w = gg.groupby("ticker")["value_usd"].sum()
            w = w / w.sum()
            # TRUE active share = 1 - sum min(w_i, b_i): the one-sided
            # 0.5*sum|w-b| over held names only compresses everything
            # toward 0.5 (misses the unheld benchmark mass)
            ov = float(np.minimum(
                w, bw.reindex(w.index).fillna(0.0)).sum())
            acts[m].append(1.0 - ov)
        for m, gg in b[b["filer_id"].isin(ok)].groupby("filer_id"):
            w = gg.groupby("instrument_id")["value_usd"].sum()
            w = w / w.sum()
            cur_w[m] = w
            pw = prev_w.get(m)
            if pw is not None:
                turns[m].append(0.5 * float(
                    w.sub(pw, fill_value=0.0).abs().sum()))
            nposs[m].append(int(len(w)))
        prev_w = cur_w
        for m in ok:
            hist[m][p] = float(rbook[m] - mret)
            aums[m].append(float(tot[m]))
        log(f"{p.date()}: {len(ok)} fundos")

    meta = pd.read_parquet(pn.QDIR / "filings_meta.parquet")
    cikmap = meta.drop_duplicates("filer_id").set_index("filer_id")["cik"]
    names = {}
    try:
        sc = pd.read_csv(HERE.parent.parent / "crowdflow" / "data"
                         / "20_curated" / "succession_candidates.csv")
        for _, r in sc.iterrows():
            names[r["predecessor_cik"]] = r["predecessor_name"]
            names[r["successor_cik"]] = r["successor_name"]
    except Exception:
        pass

    rows = []
    for m, h in hist.items():
        s = pd.Series(h).sort_index()
        if len(s) < MIN_Q:
            continue
        first = s[s.index <= SPLIT]
        second = s[s.index > SPLIT]
        cik = cikmap.get(m)
        rows.append({
            "filer_id": m, "cik": cik,
            "name": names.get(cik, ""),
            "n_q": len(s),
            "ann_excess": s.mean() * 4,
            "te": s.std() * 2,
            "ir": s.mean() / (s.std() + 1e-12) * 2,
            "ir_1st": (first.mean() / (first.std() + 1e-12) * 2
                       if len(first) >= 8 else np.nan),
            "ir_2nd": (second.mean() / (second.std() + 1e-12) * 2
                       if len(second) >= 8 else np.nan),
            "med_aum": float(np.median(aums[m])),
            "act_share": (float(np.mean(acts[m])) if acts[m] else np.nan),
            "turnover": (float(np.mean(turns[m])) if turns[m] else np.nan),
            "n_pos": (float(np.mean(nposs[m])) if nposs[m] else np.nan)})
    df = pd.DataFrame(rows)
    df.to_csv(RESULTS / "fund_performance.csv", index=False)
    # per-quarter panel (periods x filers) for cumulative log curves
    pd.DataFrame(hist).sort_index().to_csv(
        RESULTS / "quarterly_excess.csv.gz", compression="gzip")

    big = df[(df["n_q"] >= 20) & (df["med_aum"] >= 250e6)]
    both = df.dropna(subset=["ir_1st", "ir_2nd"])
    pers = float(both["ir_1st"].rank().corr(both["ir_2nd"].rank())) \
        if len(both) > 100 else np.nan

    L = ["# Performance historica dos fundos (book sintetico, excesso vs "
         "S&P)", "",
         f"- {len(df)} fundos com >= {MIN_Q} trimestres | "
         f"{len(big)} com >= 20 tri e mediana >= $250M", "",
         "AVISO: e o book LONG divulgado (sem shorts/caixa/derivativos/"
         "trading intra-tri) e o painel de precos nao tem deslistadas "
         "(survivorship infla todo mundo um pouco).", "",
         "## Distribuicao (fundos com >= 20 tri, >= $250M)", ""]
    for col, lbl, fmt in [("ann_excess", "excesso anualizado", "{:+.1%}"),
                          ("ir", "information ratio", "{:+.2f}")]:
        qtl = big[col].quantile([0.05, 0.25, 0.5, 0.75, 0.95])
        L.append(f"- **{lbl}**: p5 {fmt.format(qtl[0.05])} | p25 "
                 f"{fmt.format(qtl[0.25])} | mediana "
                 f"{fmt.format(qtl[0.5])} | p75 {fmt.format(qtl[0.75])} "
                 f"| p95 {fmt.format(qtl[0.95])}")
    L += [f"- fundos com IR > 0: {(big['ir'] > 0).mean():.0%} | "
          f"IR > 0.5: {(big['ir'] > 0.5).mean():.0%} | IR > 1.0: "
          f"{(big['ir'] > 1.0).mean():.0%}", "",
          f"## Persistencia (a razao de o smart money morrer)", "",
          f"- rank corr do IR 2013-19 vs 2019-26 (mesmos fundos, "
          f"n={len(both)}): **{pers:+.3f}**", ""]
    for lbl, tab in [("Top 20 por IR", big.nlargest(20, "ir")),
                     ("Bottom 20 por IR", big.nsmallest(20, "ir"))]:
        L += [f"## {lbl}", "",
              tab[["cik", "name", "n_q", "ann_excess", "te", "ir",
                   "med_aum"]]
              .assign(ann_excess=lambda d: (d["ann_excess"] * 100).round(1),
                      te=lambda d: (d["te"] * 100).round(1),
                      ir=lambda d: d["ir"].round(2),
                      med_aum=lambda d: (d["med_aum"] / 1e9).round(2))
              .rename(columns={"ann_excess": "exc_%aa", "te": "te_%",
                               "med_aum": "aum_bi"})
              .to_markdown(index=False), ""]
    (RESULTS / "PERF_REPORT.md").write_text("\n".join(L), encoding="utf-8")
    log("done -> results/")


if __name__ == "__main__":
    main()
