"""Performance-sigmoid-weighted breadth: the holder count where each
fund's vote is weighted by a sigmoid of its OWN trailing 4-quarter
frozen-book excess performance vs the market.

    python run_wb.py            # full sample
    python run_wb.py --smoke

CONSTRUCTION (user spec):
  perf4_m = sum of the last 4 quarters of frozen-book excess return:
            each quarter, the manager's PRIOR disclosed book is frozen
            and its value-weighted return over the quarter is computed
            from prices, minus the market (S&P proxy) return - the same
            "frozen book" object the implied-flow instrument uses, so no
            new machinery and fully PIT (books public at each decision).
  weight_m = sigmoid(z(perf4_m))   z = cross-sectional z-score, so the
            sigmoid saturates: recent winners ~1, losers ~0, middle 0.5.
  wb_level_i = sum_m weight_m * 1(m holds i) / sum_m weight_m
  wdb_i      = wb_level(cur) - wb_level(prev), holding the WEIGHTS fixed
            at the current score for both quarters - so the delta
            isolates holding changes, not weight drift.

HONESTY UP FRONT: this is performance-weighting of votes, and the family
record is 0-for-3 (U3 performing universe, EB skill weights, vol-weighted
conviction all hurt). The sigmoid variant is untested though, and cheap.
PRE-REGISTERED expectation from the family record: paired deltas vs the
UNWEIGHTED counterparts (breadth_level resid / dbreadth raw, same
quarters, same universe) <= 0. If positive and significant, the sigmoid
saturation did something linear weights could not - report it as a
surprise, re-registration required before any promotion.

Headlines follow the theorem test: wb_level is a positive count scaling
with size (monkey books hold big stocks more often regardless of
weights) -> residual headline; wdb is a delta -> raw headline.
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict, deque
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sps

HERE = Path(__file__).resolve().parent
for sub in ("", "general_plan"):
    sys.path.insert(0, str(HERE.parent / sub))

import market_cap as mc                             # noqa: E402
import panel as pn                                  # noqa: E402
from backtest_gp import forward_return, nw_tstat    # noqa: E402
from run_all import load_market, log                # noqa: E402

RESULTS = HERE / "results"
LAG = 45
PERF_TRAIL = 4
PERF_MIN = 3
MIN_COVER = 0.5


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


def main(smoke: bool = False) -> None:
    RESULTS.mkdir(exist_ok=True)
    cmap, mdta = load_market()
    dates = mdta.prices.index
    cum = mdta.returns.cumsum()
    bench = mdta.benchmark_returns.reindex(dates).fillna(0.0)
    cumb = bench.cumsum()
    adv = mdta.dollar_volume.rolling(63, min_periods=20).median()
    shares = mc.shares_panel(dates, mdta.tickers, mdta.prices, mdta.prices_raw)
    mcap = mc.mktcap_panel(mdta.prices_raw, shares)

    qs = [q for q in pn.quarters()
          if pd.Timestamp("2013-06-30") <= q <= dates[-1] - pd.Timedelta(days=120)]
    if smoke:
        qs = qs[-(12 + PERF_TRAIL):]
    log(f"{len(qs)} quarters")

    perf_hist: dict = defaultdict(lambda: deque(maxlen=PERF_TRAIL))
    events: dict[tuple, list] = {}
    paired_rows = []

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
        di_p = dates.searchsorted(p, side="right") - 1
        di_p1 = dates.searchsorted(p1, side="right") - 1
        px, adv_d = mdta.prices_raw.iloc[di], adv.iloc[di]
        mc_d = mcap.iloc[di]

        # ---- update trailing frozen-book excess perf (quarter p1 -> p) ---- #
        ret_q = cum.iloc[di_p] - cum.iloc[di_p1]
        mret = float(cumb.iloc[di_p] - cumb.iloc[di_p1])
        b = prev[["filer_id", "instrument_id", "value_usd"]].copy()
        b["ticker"] = b["instrument_id"].map(cmap)
        b["r"] = b["ticker"].map(ret_q)
        g = b.groupby("filer_id")
        tot = g["value_usd"].sum()
        cov = b.assign(v=b["value_usd"].where(b["r"].notna(), 0.0)) \
            .groupby("filer_id")["v"].sum() / tot.clip(lower=1.0)
        vr = b.assign(vr=b["value_usd"] * b["r"].fillna(0.0)) \
            .groupby("filer_id")["vr"].sum()
        rbook = vr / tot.clip(lower=1.0)
        ok_m = cov.index[(cov >= MIN_COVER) & (g.size() >= 10)]
        for m_ in ok_m:
            perf_hist[m_].append(float(rbook[m_] - mret))

        perf4 = pd.Series({m_: float(np.sum(h))
                           for m_, h in perf_hist.items()
                           if len(h) >= PERF_MIN})
        if len(perf4) < 500:
            continue
        z = (perf4 - perf4.mean()) / (perf4.std() + 1e-12)
        wgt = 1.0 / (1.0 + np.exp(-z))          # sigmoid weights in (0,1)

        # ---- holder sets, ticker level ----------------------------------- #
        def holders(df):
            d = df[["filer_id", "instrument_id"]].copy()
            d["ticker"] = d["instrument_id"].map(cmap)
            return d.dropna(subset=["ticker"]) \
                .drop_duplicates(["filer_id", "ticker"])

        hc, hp = holders(cur), holders(prev)
        keep = set(wgt.index)
        hc_w = hc[hc["filer_id"].isin(keep)].copy()
        hp_w = hp[hp["filer_id"].isin(keep)].copy()
        hc_w["w"] = hc_w["filer_id"].map(wgt)
        hp_w["w"] = hp_w["filer_id"].map(wgt)     # SAME current weights
        wsum = float(wgt.reindex(list(keep)).sum())

        n_filers_c = float(hc["filer_id"].nunique())
        n_filers_p = float(hp["filer_id"].nunique())
        n_c = hc.groupby("ticker")["filer_id"].nunique()
        n_p = hp.groupby("ticker")["filer_id"].nunique()
        idx = n_c.index.union(n_p.index)

        sig = pd.DataFrame(index=idx)
        sig["breadth_level"] = (n_c / n_filers_c).reindex(idx)
        sig["dbreadth"] = (n_c.reindex(idx).fillna(0) / n_filers_c
                           - n_p.reindex(idx).fillna(0) / n_filers_p)
        wb_c = hc_w.groupby("ticker")["w"].sum() / wsum
        wb_p = hp_w.groupby("ticker")["w"].sum() / wsum
        sig["wb_level"] = wb_c.reindex(idx)
        sig["wdb"] = (wb_c.reindex(idx).fillna(0)
                      - wb_p.reindex(idx).fillna(0))
        # UNIFORM weights on the SAME scored electorate: the clean baseline
        # that isolates the sigmoid effect from the electorate restriction
        # (scored managers only) - without it, wb vs breadth confounds the
        # weighting with the exclusion of young filers.
        nk = float(len(keep))
        ub_c = hc_w.groupby("ticker")["filer_id"].nunique() / nk
        ub_p = hp_w.groupby("ticker")["filer_id"].nunique() / nk
        sig["ub_level"] = ub_c.reindex(idx)
        sig["udb"] = (ub_c.reindex(idx).fillna(0)
                      - ub_p.reindex(idx).fillna(0))

        n_max = pd.concat([n_c.reindex(idx), n_p.reindex(idx)],
                          axis=1).max(axis=1).fillna(0)
        uni = idx[(pd.Series(idx.map(px), index=idx) >= 1.0)
                  & (n_max >= 5)]
        ctrl = pd.DataFrame({
            "lm": np.log(pd.Series(uni.map(mc_d), index=uni)),
            "la": np.log(pd.Series(uni.map(adv_d), index=uni))})
        nxt = qs[qi + 1] + pd.Timedelta(days=LAG) if qi + 1 < len(qs) \
            else dates[-1]
        fwd = forward_return(cum, dates, dec, min(nxt, dates[-1])).reindex(uni)
        rng = np.random.default_rng(int(p.value) % (2**32))

        qm = {}
        for name in ("breadth_level", "wb_level", "ub_level",
                     "dbreadth", "wdb", "udb"):
            s = sig[name].reindex(uni).replace([np.inf, -np.inf], np.nan)
            s = s.clip(s.quantile(0.01), s.quantile(0.99))
            r = s.rank(pct=True)
            if name in ("breadth_level", "wb_level", "ub_level"):  # theorem
                r = residualise(r, ctrl).rank(pct=True)
            df = pd.concat([r.rename("s"), fwd.rename("f")], axis=1).dropna()
            if len(df) < 300:
                continue
            jit = pd.Series(rng.uniform(0, 1e-9, len(df)), index=df.index)
            q5 = pd.qcut((df["s"] + jit).rank(), 5, labels=False)
            gq = df.groupby(q5)["f"].mean()
            sp = float(gq.get(4, np.nan) - gq.get(0, np.nan))
            ic = float(sps.spearmanr(df["s"], df["f"])[0])
            events.setdefault(name, []).append(
                {"period": p, "spread": sp, "ic": ic})
            qm[name] = (sp, ic)
        row = {"period": p, "n_scored": len(perf4)}
        # decomposition: sigmoid effect (wb vs uniform, SAME electorate)
        # and electorate effect (uniform-scored vs full census)
        for tag, a, b_ in (("sig_level", "wb_level", "ub_level"),
                           ("sig_delta", "wdb", "udb"),
                           ("elec_level", "ub_level", "breadth_level"),
                           ("elec_delta", "udb", "dbreadth")):
            if a in qm and b_ in qm:
                row[f"d_{tag}"] = qm[a][0] - qm[b_][0]
                row[f"dic_{tag}"] = qm[a][1] - qm[b_][1]
        paired_rows.append(row)
        log(f"{p.date()}: {len(perf4)} gestores com score")

    pr = pd.DataFrame(paired_rows)
    pr.to_csv(RESULTS / "wb_paired.csv", index=False)
    L = ["# wbreadth - breadth ponderado por sigmoide de performance "
         "(4 tri, book congelado, excesso vs mercado)", "",
         f"peso_m = sigmoid(z(perf4)); media "
         f"{pr['n_scored'].mean():.0f} gestores com score/tri. "
         "Pre-registro (historico 0-de-3 da familia performance-weight): "
         "deltas <= 0.", "",
         "## Sinais (headline: nivel resid, delta raw)", ""]
    for name, evs in events.items():
        e = pd.DataFrame(evs)
        L.append(f"- **{name}**: {e['spread'].mean():+.4f}/tri "
                 f"(t={nw_tstat(e['spread']):+.2f}), Sharpe "
                 f"{e['spread'].mean() / e['spread'].std() * 2:+.2f}, IC "
                 f"{e['ic'].mean():+.4f}, {len(e)} tri")
    L += ["", "## Deltas pareados (decomposicao)", ""]
    for tag, lbl in (("sig_level", "efeito SIGMOIDE no nivel "
                      "(wb vs uniforme, mesmo eleitorado)"),
                     ("sig_delta", "efeito SIGMOIDE na variacao "
                      "(wdb vs udb)"),
                     ("elec_level", "efeito ELEITORADO no nivel "
                      "(uniforme-com-score vs censo)"),
                     ("elec_delta", "efeito ELEITORADO na variacao")):
        if f"d_{tag}" not in pr:
            continue
        d = pr[f"d_{tag}"].dropna()
        di_ = pr[f"dic_{tag}"].dropna()
        if len(d):
            L.append(f"- **{lbl}**: dSpread {d.mean():+.4f}/tri "
                     f"(t={nw_tstat(d):+.2f}), dIC {di_.mean():+.4f} "
                     f"(t={nw_tstat(di_):+.2f}), {len(d)} tri")
    (RESULTS / "WB_REPORT.md").write_text("\n".join(L), encoding="utf-8")
    log("done -> results/")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    main(**vars(ap.parse_args()))
