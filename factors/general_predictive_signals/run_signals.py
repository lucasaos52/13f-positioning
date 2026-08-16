"""Evaluate the 17-signal catalogue under one identical protocol.

    python run_signals.py           # full sample
    python run_signals.py --smoke   # last 10 quarters

Protocol (fixed BEFORE any return was seen):
  clock       decision at p+45d, snapshots via filed_date (event-driven PIT)
  universe    mapped ticker, price >= $1 (literature floor; NO ADV cut so
              the illiquid short leg the literature uses stays in)
  versions    every signal evaluated BOTH raw and residualised on
              log(mktcap)+log(ADV) (+extra controls); the HEADLINE version
              is fixed by the theorem flag in signal_defs, not by results
  portfolio   quintiles, EW and VW(mktcap), quarterly hold to next decision
  metrics     mean spread, NW(4) t, annualised Sharpe, Spearman IC,
              monotonicity fraction, per-leg means
  extras      signal correlation matrix (two signals at 0.8 = one factor),
              conf_reveal scored as flagged-group excess (coverage too thin
              for quintiles)

Outputs: results/signals_summary.csv, signals_corr.csv, REPORT.md.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sps

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "general_plan"))

import market_cap as mc                     # noqa: E402
import panel as pn                          # noqa: E402
from backtest_gp import forward_return, nw_tstat  # noqa: E402
from run_all import load_market, log        # noqa: E402
from signal_defs import CATALOGUE, build_all  # noqa: E402

RESULTS = HERE / "results"
LAG = 45
EARLY_CUT = 40          # filers filed <= p+40d = early (plan §5.1: ~50% by d43)


def residualise(y: pd.Series, X: pd.DataFrame) -> pd.Series:
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


def main(smoke: bool = False) -> None:
    RESULTS.mkdir(exist_ok=True)
    cmap, mdta = load_market()
    dates = mdta.prices.index
    cum = mdta.returns.cumsum()
    adv = mdta.dollar_volume.rolling(63, min_periods=20).median()
    shares = mc.shares_panel(dates, mdta.tickers, mdta.prices, mdta.prices_raw)
    mcap = mc.mktcap_panel(mdta.prices_raw, shares)
    meta = pd.read_parquet(pn.QDIR / "filings_meta.parquet")
    nh = meta[meta["amendment_type"] == "NEW HOLDINGS"]

    qs = [q for q in pn.quarters()
          if pd.Timestamp("2013-06-30") <= q <= dates[-1] - pd.Timedelta(days=120)]
    if smoke:
        qs = qs[-12:]
    log(f"{len(qs)} quarters, {len(CATALOGUE)} signals")

    sig_names = list(CATALOGUE)
    events: dict[tuple, list] = {}
    corr_acc: list[pd.DataFrame] = []
    conf_rows = []

    for qi in range(2, len(qs)):
        p, p1, p2 = qs[qi], qs[qi - 1], qs[qi - 2]
        dec = p + pd.Timedelta(days=LAG)
        if dec >= dates[-1] - pd.Timedelta(days=95):
            continue
        cur = pn.snapshot_as_of(p, dec)
        prev = pn.snapshot_as_of(p1, dec)
        prev2 = pn.snapshot_as_of(p2, dec)
        if min(len(cur), len(prev)) < 1000:
            continue

        di = dates.searchsorted(dec, side="right") - 1
        di_p = dates.searchsorted(p, side="right") - 1
        di_p1 = dates.searchsorted(p1, side="right") - 1
        di_p2 = dates.searchsorted(p2, side="right") - 1
        px, adv_d = mdta.prices_raw.iloc[di], adv.iloc[di]
        mc_d = mcap.iloc[di] if len(mcap) else pd.Series(dtype=float)

        def so_at(dix):
            row = shares.iloc[dix] if len(shares) else pd.Series(dtype=float)
            t = pd.Series(cmap)
            return pd.Series(t.map(row).values, index=t.index)

        orig = meta[(meta["period_end"] == p) & (~meta["is_amendment"])]
        early = set(orig.loc[orig["filing_date"] <= p + pd.Timedelta(days=EARLY_CUT),
                             "filer_id"])

        # ---- split adjustment for share-DELTA signals -------------------- #
        # ti/vi/late_minus_early/new_conviction compare share counts across
        # quarters; a 4:1 split fakes a buy from every holder. Price-implied
        # detection is IMPOSSIBLE here (Yahoo's raw Close is retroactively
        # split-adjusted; adj/raw only carries dividends - verified on
        # NVDA/AAPL/TSLA). The detector that works is the MODAL ATOM from
        # the holders themselves (validated 6/6 on famous splits in
        # analysis_v1): an untouched holder's cur/prev share ratio equals
        # the split factor EXACTLY, and dozens of holders landing on the
        # same rounded atom is not a coincidence.
        pair = cur.merge(prev, on=["filer_id", "instrument_id"],
                         suffixes=("_c", "_p"))
        pair = pair[(pair["shares_p"] > 0) & (pair["shares_c"] > 0)]
        pair["ratio"] = (pair["shares_c"] / pair["shares_p"]).round(3)
        fac_map = {}
        for j, g in pair.groupby("instrument_id"):
            if len(g) < 10:
                continue
            counts = g["ratio"].value_counts()
            mode, k = counts.index[0], counts.iloc[0]
            k2 = counts.iloc[1] if len(counts) > 1 else 0
            if abs(mode - 1) > 0.15 and (k >= 0.10 * len(g)
                                         or (k >= 30 and k >= 2.5 * k2)):
                fac_map[j] = float(mode)
        fac_i = pd.Series(fac_map, dtype=float)
        # passed INTO build_all, applied ONLY to share-delta computations:
        # IO-ratio signals stay split-safe via contemporaneous SO
        # confidential reveals: instruments in NEW HOLDINGS amendments of the
        # last 4 quarters whose amendment was PUBLIC by the decision date
        nh_recent = nh[(nh["period_end"] >= qs[max(0, qi - 4)])
                       & (nh["filing_date"] <= dec)]
        accs = set(nh_recent["accession"])
        parts = []
        for q_ in qs[max(0, qi - 4):qi + 1]:
            qdf = pn._load_quarter(str(q_)[:10])
            parts.append(qdf.loc[qdf["accession"].isin(accs), "instrument_id"])
        nh_instr = (pd.Index(pd.concat(parts).unique())
                    if parts else pd.Index([]))

        sig = build_all(cur, prev, prev2, so_at(di_p), so_at(di_p1),
                        so_at(di_p2), early, nh_instr, split_fac=fac_i)
        # crowding: one ADV date for both quarters -> the delta is holdings
        # change, not liquidity change
        t = sig.index.to_series().map(cmap)
        adv_i = t.map(adv_d)
        sig["days_adv"] = sig.pop("inst_value") / adv_i
        sig["d_days_adv"] = (sig["days_adv"]
                             - sig.pop("inst_value_prev") / adv_i)

        # ticker level: sum flows/counts, mean bounded ratios
        sig["ticker"] = t
        sig = sig.dropna(subset=["ticker"])
        # pso must SUM across share classes of one issuer (total shares held
        # over total SO); bounded ratios and level shares average
        agg = {n: ("mean" if n in ("ti", "vi", "breadth_level",
                                   "herf_holders", "conf_reveal")
                   else "sum") for n in sig_names}
        agg["log_n_holders"] = "max"
        byt = sig.groupby("ticker").agg(agg)

        u = byt.index[px.reindex(byt.index) >= 1.0]
        byt = byt.loc[byt.index.isin(u)]
        ctrl = pd.DataFrame({
            "log_mktcap": np.log(mc_d.reindex(byt.index)),
            "log_adv": np.log(adv_d.reindex(byt.index))})

        nxt = qs[qi + 1] + pd.Timedelta(days=LAG) if qi + 1 < len(qs) \
            else dates[-1]
        fwd = forward_return(cum, dates, dec, min(nxt, dates[-1]))
        fwd = fwd.reindex(byt.index)

        ranks = {}
        for name in sig_names:
            m = CATALOGUE[name]
            s = byt[name].replace([np.inf, -np.inf], np.nan)
            s = s.clip(s.quantile(0.01), s.quantile(0.99))
            r_raw = s.rank(pct=True)
            X = ctrl.copy()
            for ec in m.extra_controls:
                X[ec] = byt[ec]
            r_res = residualise(r_raw, X).rank(pct=True)
            ranks[name] = r_raw
            if name == "conf_reveal":
                flag = byt[name] > 0
                if flag.sum() >= 10:
                    conf_rows.append({
                        "period": p, "n_flag": int(flag.sum()),
                        "excess": float(fwd[flag].mean() - fwd.mean())})
                continue
            for ver, r in [("raw", r_raw), ("resid", r_res)]:
                df = pd.concat([r.rename("s"), fwd.rename("f")], axis=1).dropna()
                if len(df) < 150:
                    continue
                # tie-break RANDOMLY (seeded by date): rank(method="first")
                # splits tied blocks alphabetically by ticker - a
                # deterministic artefact exactly where the sort should be
                # indifferent (mass ties at zero in the breadth/entry family)
                rng = np.random.default_rng(int(p.value) % (2**32))
                jitter = pd.Series(rng.uniform(0, 1e-9, len(df)), index=df.index)
                q = pd.qcut((df["s"] + jitter).rank(), 5, labels=False) + 1
                ew = df.groupby(q)["f"].mean()
                w = mc_d.reindex(df.index).fillna(0.0)
                vw = df.assign(w=w).groupby(q).apply(
                    lambda g: np.average(g["f"], weights=g["w"])
                    if g["w"].sum() > 0 else np.nan)
                events.setdefault((name, ver), []).append({
                    "period": p,
                    "spread_ew": ew.get(5, np.nan) - ew.get(1, np.nan),
                    "spread_vw": vw.get(5, np.nan) - vw.get(1, np.nan),
                    "ic": sps.spearmanr(df["s"], df["f"])[0],
                    "mono": float(np.mean(np.diff(
                        [ew.get(k, np.nan) for k in range(1, 6)]) >= 0)),
                    "q1": ew.get(1, np.nan), "q5": ew.get(5, np.nan),
                    "n": len(df)})
        corr_acc.append(pd.DataFrame(ranks).corr(method="spearman"))
        log(f"{p.date()} done ({qi}/{len(qs) - 1})")

    # ---- aggregate -------------------------------------------------------- #
    rows = []
    for (name, ver), evs in events.items():
        e = pd.DataFrame(evs)
        m = CATALOGUE[name]
        rows.append({
            "signal": name, "version": ver,
            "headline": (ver == "resid") == m.theorem,
            "theorem": m.theorem, "n_events": len(e),
            "spread_ew_q": e["spread_ew"].mean(),
            "t_ew": nw_tstat(e["spread_ew"]),
            "sharpe_ew": (e["spread_ew"].mean() / e["spread_ew"].std()
                          * np.sqrt(4)),
            "spread_vw_q": e["spread_vw"].mean(),
            "t_vw": nw_tstat(e["spread_vw"]),
            "ic": e["ic"].mean(),
            "ic_ir": (e["ic"].mean() / e["ic"].std()
                      if e["ic"].std() > 0 else np.nan),
            "mono": e["mono"].mean(),
            "expected": m.expected})
    summ = (pd.DataFrame(rows)
            .sort_values(["headline", "t_ew"], ascending=[False, False]))
    summ.to_csv(RESULTS / "signals_summary.csv", index=False)
    corr = sum(corr_acc) / len(corr_acc)
    corr.to_csv(RESULTS / "signals_corr.csv")
    conf = pd.DataFrame(conf_rows)

    # ---- report ----------------------------------------------------------- #
    L = ["# general_predictive_signals - 17 sinais, protocolo unico", "",
         "Headline fixado ANTES dos retornos pelo teste do teorema "
         "(neutraliza ex-ante so o que correlacionaria com size/liquidez "
         "num mundo de gestores-macaco). raw e resid reportados para todos.",
         "", "## Sumario (headline primeiro, ordenado por t EW)", ""]
    cols = ["signal", "version", "theorem", "spread_ew_q", "t_ew",
            "sharpe_ew", "spread_vw_q", "t_vw", "ic", "ic_ir", "mono",
            "n_events"]
    hl = summ[summ["headline"]]
    L.append(hl[cols].round(4).to_markdown(index=False))
    L += ["", "## Versao alternativa (nao-headline)", "",
          summ[~summ["headline"]][cols].round(4).to_markdown(index=False)]
    if len(conf):
        t = conf["excess"].mean() / conf["excess"].std() * np.sqrt(len(conf))
        L += ["", "## conf_reveal (grupo flagged vs universo)",
              f"- excesso medio {conf['excess'].mean():+.4f}/tri, "
              f"t={t:.2f}, {len(conf)} trimestres, "
              f"mediana {conf['n_flag'].median():.0f} nomes/tri"]
    L += ["", "## Alvos de literatura", ""]
    for name, m in CATALOGUE.items():
        L.append(f"- **{name}**: {m.expected}")
    L += ["", "## Pares com |corr|>0.6 (um fator, nao dois)", ""]
    cc = corr.abs()
    for i, a in enumerate(cc.index):
        for b in cc.columns[i + 1:]:
            if cc.loc[a, b] > 0.6:
                L.append(f"- {a} x {b}: {corr.loc[a, b]:+.2f}")
    (RESULTS / "REPORT.md").write_text("\n".join(L), encoding="utf-8")
    log("done -> results/")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    main(**vars(ap.parse_args()))
