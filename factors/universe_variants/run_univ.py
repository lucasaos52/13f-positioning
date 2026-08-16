"""Variantes de universo de FUNDOS para dbreadth e new_conviction.

    python run_univ.py [--smoke]

Universos (limiares na data de decisao, PIT):
  U0  todos os filers (baseline atual)
  U1  top 10% turnover E top 20% AUM      (grandes E ativos - trade caro =
                                           revelacao de preferencia sob custo)
  U2  top tercil de ACTIVE SHARE           (Cremers-Petajisto: distancia do
                                           indice e caracteristica estrutural)
  U3  U2 E book-return trailing (ate 4q, expansivo) acima da mediana
                                           ("ativo E indo bem" - smart money
                                           como subconjunto ex-ante, plano §3D)

Adaptacoes declaradas: turnover de 1 trimestre (nao media de 4 - mais barato,
mesma ordenacao); performance trailing = media expansiva dos ultimos <=4
rbooks ja observados (estritamente antes da decisao - o vetor de lookahead
do §3D evitado por construcao).

Avaliacao: protocolo padrao (D+50, quintis EW, fwd ate a proxima decisao,
NW) + DELTA PAREADO de cada universo vs U0 nos mesmos trimestres. dbreadth
cru (nao-teorema), new_conviction residualizado (teorema). n de fundos por
universo reportado - eleitorado pequeno = ruido, dito antes de olhar.
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
for sub in ("", "general_plan", "general_predictive_signals", "ssi"):
    sys.path.insert(0, str(HERE.parent / sub))

import panel as pn                                  # noqa: E402
import market_cap as mc                             # noqa: E402
from backtest_gp import forward_return, nw_tstat    # noqa: E402
from run_all import load_market, log                # noqa: E402
from run_signals import residualise                 # noqa: E402
from run_ssi import new_conviction_signal           # noqa: E402

RESULTS = HERE / "results"
LAG = 50
UNIVERSES = ["U0", "U1", "U2", "U3"]


def main(smoke: bool = False) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    cmap, mdta = load_market()
    dates = mdta.prices.index
    cum = mdta.returns.cumsum()
    adv = mdta.dollar_volume.rolling(63, min_periods=20).median()
    shares = mc.shares_panel(dates, mdta.tickers, mdta.prices, mdta.prices_raw)
    mcap = mc.mktcap_panel(mdta.prices_raw, shares)

    qs = [q for q in pn.quarters()
          if pd.Timestamp("2013-06-30") <= q <= dates[-1] - pd.Timedelta(days=125)]
    if smoke:
        qs = qs[-12:]

    rbook_hist: dict[str, deque] = defaultdict(lambda: deque(maxlen=4))
    rows = []
    for qi in range(1, len(qs)):
        p1, p = qs[qi - 1], qs[qi]
        dec = p + pd.Timedelta(days=LAG)
        if dec >= dates[-1] - pd.Timedelta(days=95):
            break
        cur = pn.snapshot_as_of(p, dec)
        prev = pn.snapshot_as_of(p1, dec)
        if min(len(cur), len(prev)) < 1000:
            continue
        i1 = dates.searchsorted(p1, side="right") - 1
        i0 = dates.searchsorted(p, side="right") - 1
        di = dates.searchsorted(dec, side="right") - 1
        px, adv_d, mc_d = mdta.prices_raw.iloc[di], adv.iloc[di], mcap.iloc[di]
        ret_q = cum.iloc[i0] - cum.iloc[i1]

        # ---- stats por fundo (PIT) ---------------------------------------- #
        st = pn.filer_stats(cur)
        turn = pn.turnover(cur, prev)
        h = cur.copy()
        h["tk"] = h["instrument_id"].map(cmap)
        hm = h.dropna(subset=["tk"])
        hm["w"] = hm["value_usd"] / hm.groupby("filer_id")["value_usd"] \
            .transform("sum")
        wmkt = (mc_d / mc_d.sum())
        hm["aw_abs"] = (hm["w"] - hm["tk"].map(wmkt).fillna(0.0)).abs()
        act_share = hm.groupby("filer_id")["aw_abs"].sum() / 2.0
        # rbook trailing (media dos <=4 rbooks JA observados, antes de add)
        b = prev.copy()
        b["tk"] = b["instrument_id"].map(cmap)
        b = b.dropna(subset=["tk"])
        b["r"] = b["tk"].map(ret_q).fillna(0.0)
        rbook = (b["value_usd"] * b["r"]).groupby(b["filer_id"]).sum() \
            / b.groupby("filer_id")["value_usd"].sum().clip(lower=1.0)
        trail = pd.Series({f: np.mean(dq) for f, dq in rbook_hist.items()
                           if len(dq) >= 2})
        for f, v in rbook.items():
            rbook_hist[f].append(float(v))

        base = st[st["n_pos"] >= 10]
        U = {"U0": set(base.index)}
        U["U1"] = set(base.index[
            (turn.reindex(base.index) >= turn.reindex(base.index).quantile(0.90))
            & (base["aum"] >= base["aum"].quantile(0.80))])
        a3 = act_share.reindex(base.index).dropna()
        U["U2"] = set(a3.index[a3 >= a3.quantile(2 / 3)])
        if len(trail) > 200:
            good = set(trail.index[trail >= trail.median()])
            U["U3"] = U["U2"] & good
        else:
            U["U3"] = set()

        nxt = qs[qi + 1] + pd.Timedelta(days=LAG) if qi + 1 < len(qs) \
            else dates[-1]
        fwd_full = forward_return(cum, dates, dec, min(nxt, dates[-1]))

        rec = {"period": p}
        for uname in UNIVERSES:
            uset = U[uname]
            rec[f"nf_{uname}"] = len(uset)
            if len(uset) < 80:
                continue
            cu = cur[cur["filer_id"].isin(uset)]
            pu = prev[prev["filer_id"].isin(uset)]
            # dbreadth no eleitorado U (denominador |U|, cru)
            nc_ = cu.groupby("instrument_id")["filer_id"].nunique()
            np_ = pu.groupby("instrument_id")["filer_id"].nunique()
            db = (nc_.reindex(nc_.index.union(np_.index)).fillna(0)
                  - np_.reindex(nc_.index.union(np_.index)).fillna(0)) / len(uset)
            t_ = db.index.to_series().map(cmap)
            db = db.groupby(t_).sum().dropna()
            db = db[px.reindex(db.index) >= 1.0]
            # new_conviction no eleitorado U (residualizado - teorema)
            ncv = new_conviction_signal(cu, pu, cmap)
            ncv = ncv[px.reindex(ncv.index) >= 1.0]
            ctrl = pd.DataFrame({"log_mktcap": np.log(mc_d.reindex(ncv.index)),
                                 "log_adv": np.log(adv_d.reindex(ncv.index))})
            ncv = residualise(ncv.rank(pct=True), ctrl).rank(pct=True).dropna()
            for sname, sig in [("db", db), ("nc", ncv)]:
                if len(sig) < 150:
                    continue
                r = sig.rank(pct=True)
                df = pd.concat([r.rename("s"), fwd_full.reindex(r.index)
                                .rename("f")], axis=1).dropna()
                if len(df) < 150:
                    continue
                q5 = pd.qcut(df["s"].rank(method="first"), 5, labels=False)
                rec[f"{sname}_{uname}"] = float(df["f"][q5 == 4].mean()
                                                - df["f"][q5 == 0].mean())
        rows.append(rec)
        log(f"{p.date()}: U1={rec.get('nf_U1', 0)} U2={rec.get('nf_U2', 0)} "
            f"U3={rec.get('nf_U3', 0)}")

    e = pd.DataFrame(rows)
    e.to_csv(RESULTS / "univ_events.csv", index=False)
    L = ["# Variantes de universo de fundos - dbreadth e new_conviction", "",
         f"n medio de fundos: " + " | ".join(
             f"{u}={e[f'nf_{u}'].mean():.0f}" for u in UNIVERSES
             if f"nf_{u}" in e), ""]
    for sname, lbl in [("db", "dbreadth (cru)"),
                       ("nc", "new_conviction (resid)")]:
        L.append(f"## {lbl}")
        base_col = f"{sname}_U0"
        for u in UNIVERSES:
            col = f"{sname}_{u}"
            if col not in e:
                continue
            s = e[col].dropna()
            line = (f"- {u}: spread {s.mean():+.4f}/tri "
                    f"t={nw_tstat(s):+.2f} (n={len(s)})")
            if u != "U0" and base_col in e:
                d = (e[col] - e[base_col]).dropna()
                if len(d) > 8:
                    line += (f" | DELTA vs U0: {d.mean():+.4f} "
                             f"t(pareado)={nw_tstat(d):+.2f}")
            L.append(line)
        L.append("")
    (RESULTS / "UNIV_REPORT.md").write_text("\n".join(L), encoding="utf-8")
    log("done -> results/")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    main(**vars(ap.parse_args()))
