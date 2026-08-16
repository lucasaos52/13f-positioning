"""Views implicitas por otimizacao reversa + encolhimento EB (nota BL).

    python run_bl.py [--smoke]

Cadeia aninhada (prevista: IC melhora monotonicamente; se M1 empatar com
M4, entrega-se M1 e escreve-se isso):
  M1  peso ativo cru agregado            f = sum_i w_a
  M2  view de risco completa             f = sum_i (Sigma w_a)_i, Sigma 1-fator
  M3  view idiossincratica               f = sum_i sigma2_eps * w_a  (exato)
  M4  skill-weighted (James-Stein)       f = sum_i a_til_i * q_idio_i

Furos corrigidos vs pratica comum (documentados na resposta):
  - Sigma SEMPRE trailing 252d (1-fator beta vs S&P + D idio); nunca
    full-sample; M2 sem formar a matriz (identidade do 1-fator);
  - pre-teste do tilt de vol ANTES do backtest (risco #1 da nota) +
    variante M3 residualizada contra vol idio;
  - skill a_i = excesso trailing do book vs mercado, EXPANSIVO (< t);
    tau2 por momentos, piso 0; sem filtro manual de historico (o EB e o
    filtro);
  - dois modelos de risco (1-fator vs diagonal pura) - dispersao reportada;
  - bandas de universo de ACOES: MEGA (top 500 mktcap), MID (500-1500),
    FULL (>=US$500M, >=US$5 - o corte da nota).
Avaliacao: protocolo padrao (D+50 por filed_date, quintis EW, fwd 1 tri,
NW), IC pareado entre modelos nos mesmos trimestres.
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

import panel as pn                                  # noqa: E402
import market_cap as mc                             # noqa: E402
from backtest_gp import forward_return, nw_tstat    # noqa: E402
from run_all import load_market, log                # noqa: E402

RESULTS = HERE / "results"
LAG = 50
BANDS = {"MEGA": (0, 500), "MID": (500, 1500), "FULL": (0, 10 ** 6)}
MODELS = ["m1_wa", "m2_sw", "m3_qidio", "m3v_volneu", "m4_skill", "m3d_diag"]


def main(smoke: bool = False) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    cmap, mdta = load_market()
    dates = mdta.prices.index
    cum = mdta.returns.cumsum()
    bench = mdta.benchmark_returns
    shares = mc.shares_panel(dates, mdta.tickers, mdta.prices, mdta.prices_raw)
    mcap = mc.mktcap_panel(mdta.prices_raw, shares)

    qs = [q for q in pn.quarters()
          if pd.Timestamp("2013-06-30") <= q <= dates[-1] - pd.Timedelta(days=125)]
    if smoke:
        qs = qs[-12:]

    skill_hist: dict[str, deque] = defaultdict(lambda: deque(maxlen=12))
    rows, pre_rows = [], []
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
        px = mdta.prices_raw.iloc[di]
        mc_d = mcap.iloc[di]
        ret_q = cum.iloc[i0] - cum.iloc[i1]
        bench_q = float(bench.iloc[i1:i0].sum())

        # ---- modelo de risco PIT: 1-fator (beta vs S&P) + D idio ---------- #
        w0 = max(0, di - 252)
        rs = mdta.returns.iloc[w0:di]
        rb = bench.iloc[w0:di]
        bvar = float(rb.var())
        beta = rs.apply(lambda c: c.cov(rb)) / max(bvar, 1e-10)
        sig2 = rs.var()
        sig2_eps = (sig2 - beta ** 2 * bvar).clip(lower=1e-6)

        # ---- pesos ativos por gestor -------------------------------------- #
        h = cur.copy()
        h["tk"] = h["instrument_id"].map(cmap)
        h = h.dropna(subset=["tk"])
        h = h[h["tk"].map(px).notna()]
        g = h.groupby("filer_id")["value_usd"]
        aum = g.sum()
        npos = g.size()
        elig = aum.index[(aum >= 1e8) & (npos >= 10)]
        h = h[h["filer_id"].isin(elig)]
        h["w"] = h["value_usd"] / h["filer_id"].map(aum)
        wmkt = (mc_d / mc_d.sum())
        h["wa"] = h["w"] - h["tk"].map(wmkt).fillna(0.0)

        # ---- skill EB (expansivo, so passado) ------------------------------ #
        a_hat, s2 = {}, {}
        for f_, dq in skill_hist.items():
            if len(dq) >= 2:
                arr = np.array(dq)
                a_hat[f_] = float(arr.mean())
                s2[f_] = float(arr.var() / len(arr))
        a_hat = pd.Series(a_hat)
        if len(a_hat) > 100:
            tau2 = max(float(a_hat.var() - np.mean(list(s2.values()))), 1e-8)
            shr = {f_: tau2 / (tau2 + s2[f_]) for f_ in a_hat.index}
            a_til = pd.Series({f_: shr[f_] * a_hat[f_]
                               + (1 - shr[f_]) * float(a_hat.mean())
                               for f_ in a_hat.index})
        else:
            a_til = pd.Series(dtype=float)
        # atualiza historico com o rbook excedente DESTE tri (uso futuro)
        b_ = prev.copy()
        b_["tk"] = b_["instrument_id"].map(cmap)
        b_ = b_.dropna(subset=["tk"])
        b_["r"] = b_["tk"].map(ret_q).fillna(0.0)
        rb_ = (b_["value_usd"] * b_["r"]).groupby(b_["filer_id"]).sum() \
            / b_.groupby("filer_id")["value_usd"].sum().clip(lower=1.0)
        for f_, v in (rb_ - bench_q).items():
            skill_hist[f_].append(float(v))

        # ---- views por gestor e agregacao ---------------------------------- #
        h["beta"] = h["tk"].map(beta)
        h["s2e"] = h["tk"].map(sig2_eps)
        h = h.dropna(subset=["beta", "s2e"])
        bw = (h["beta"] * h["wa"]).groupby(h["filer_id"]).sum()  # beta'w_a
        h["sw"] = h["beta"] * h["filer_id"].map(bw) * bvar + h["s2e"] * h["wa"]
        h["qidio"] = h["s2e"] * h["wa"]
        h["qdiag"] = h["tk"].map(sig2) * h["wa"]      # risco diagonal puro
        h["a_til"] = h["filer_id"].map(a_til).fillna(0.0)
        h["qskill"] = h["a_til"] * h["qidio"]

        agg = h.groupby("tk").agg(m1_wa=("wa", "sum"), m2_sw=("sw", "sum"),
                                  m3_qidio=("qidio", "sum"),
                                  m3d_diag=("qdiag", "sum"),
                                  m4_skill=("qskill", "sum"))

        # pre-teste da nota: corr com vol idio (ANTES do backtest)
        vol_r = sig2_eps.reindex(agg.index)
        pre_rows.append({"period": p, "corr_qidio_vol": float(sps.spearmanr(
            agg["m3_qidio"].rank(), vol_r.rank(), nan_policy="omit")[0])})
        # variante vol-neutralizada
        rk = agg["m3_qidio"].rank(pct=True)
        vr = vol_r.rank(pct=True)
        okv = rk.notna() & vr.notna()
        X = np.column_stack([np.ones(okv.sum()), vr[okv].values])
        bb, *_ = np.linalg.lstsq(X, rk[okv].values, rcond=None)
        res = rk.copy()
        res[okv] = rk[okv].values - X @ bb
        agg["m3v_volneu"] = res

        # ---- avaliacao por banda de universo ------------------------------- #
        ranks_mc = mc_d.reindex(agg.index).rank(ascending=False)
        nxt = qs[qi + 1] + pd.Timedelta(days=LAG) if qi + 1 < len(qs) \
            else dates[-1]
        fwd = forward_return(cum, dates, dec, min(nxt, dates[-1]))
        rec = {"period": p}
        for band, (lo, hi) in BANDS.items():
            sel = agg.index[(ranks_mc > lo) & (ranks_mc <= hi)
                            & (mc_d.reindex(agg.index) >= 5e8)
                            & (px.reindex(agg.index) >= 5.0)]
            A = agg.loc[agg.index.isin(sel)]
            if len(A) < 120:
                continue
            fw = fwd.reindex(A.index)
            for mname in MODELS:
                if mname == "m4_skill" and A["m4_skill"].abs().sum() == 0:
                    continue
                r = A[mname].rank(pct=True)
                df = pd.concat([r.rename("s"), fw.rename("f")], axis=1).dropna()
                if len(df) < 100:
                    continue
                q5 = pd.qcut(df["s"].rank(method="first"), 5, labels=False)
                rec[f"{band}_{mname}_ic"] = float(
                    sps.spearmanr(df["s"], df["f"])[0])
                rec[f"{band}_{mname}_sp"] = float(
                    df["f"][q5 == 4].mean() - df["f"][q5 == 0].mean())
        rows.append(rec)
        log(f"{p.date()}: {len(elig)} gestores, "
            f"corr_vol={pre_rows[-1]['corr_qidio_vol']:+.2f}")

    e = pd.DataFrame(rows)
    pre = pd.DataFrame(pre_rows)
    e.to_csv(RESULTS / "bl_events.csv", index=False)

    L = ["# Black-Litterman implicito - views por otimizacao reversa", "",
         "## Pre-teste da nota (rodado ANTES do backtest)",
         f"- corr(q_idio, vol idio) media: {pre.corr_qidio_vol.mean():+.2f} "
         "(alto = tilt de vol por construcao -> ver variante vol-neutra)", ""]
    for band in BANDS:
        L.append(f"## Banda {band} (cadeia aninhada: IC | spread EW/tri, t)")
        for mname, lbl in [("m1_wa", "M1 peso ativo cru"),
                           ("m2_sw", "M2 Sigma w (1-fator)"),
                           ("m3_qidio", "M3 q_idio (exato)"),
                           ("m3v_volneu", "M3v q_idio vol-neutro"),
                           ("m3d_diag", "M3d risco diagonal (robustez)"),
                           ("m4_skill", "M4 skill-weighted EB")]:
            ic_c, sp_c = f"{band}_{mname}_ic", f"{band}_{mname}_sp"
            if ic_c not in e:
                continue
            ic, sp = e[ic_c].dropna(), e[sp_c].dropna()
            L.append(f"- {lbl}: IC {ic.mean():+.4f} | spread {sp.mean():+.4f} "
                     f"t={nw_tstat(sp):+.2f} (n={len(sp)})")
        L.append("")
    (RESULTS / "BL_REPORT.md").write_text("\n".join(L), encoding="utf-8")
    log("done -> results/")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    main(**vars(ap.parse_args()))
