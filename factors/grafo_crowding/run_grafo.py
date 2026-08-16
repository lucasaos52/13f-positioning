"""Grafo de co-ownership x difusao de choques de venda forcada (M3).

    python run_grafo.py [--smoke]

Tese (Anton-Polk 2014 + a licao da reversao condicional): quando gestores
chocados vendem o papel j, os papeis k que dividem DONOS com j estao na fila
- o distress do dono comum continua (hazard ~40%) e o proximo corte cai onde
ele ainda tem posicao. O sinal e SO o spillover (nomes com choque direto
baixo), difundido um passo pelo grafo:

    G_jk  = soma_{i detem j e k} (v_ij + v_ik) / (ADV$_j + ADV$_k)
    P     = G row-normalizada, diagonal zero
    spill = P @ choque_direto        [choque = venda forcada realizada / ADV]
    universo do sinal: metade de MENOR choque direto (spillover puro)

Zero parametros ajustados (um passo de difusao, theta=1). Direcao
PRE-REGISTRADA: NEGATIVA no 1o trimestre (contagio-continuacao - a reversao
condicional provou que a pressao continua, nao reverte, nessa janela);
janela +2 reportada como check de reversao tardia.

Falsificacao embutida: placebo de permutacao - o MESMO grafo difundindo o
vetor de choques EMBARALHADO entre as acoes (seeded). Se o placebo render
igual, o grafo nao esta propagando nada e a tese cai.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse
from scipy import stats as sps

HERE = Path(__file__).resolve().parent
for sub in ("", "general_plan"):
    sys.path.insert(0, str(HERE.parent / sub))

import panel as pn                                  # noqa: E402
from backtest_gp import forward_return, nw_tstat    # noqa: E402
from run_all import load_market, log                # noqa: E402

RESULTS = HERE / "results"
LAG = 50
SHOCK_PCTL = 0.10


def main(smoke: bool = False) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    cmap, mdta = load_market()
    dates = mdta.prices.index
    cum = mdta.returns.cumsum()
    adv = mdta.dollar_volume.rolling(63, min_periods=20).median()

    qs = [q for q in pn.quarters()
          if pd.Timestamp("2013-06-30") <= q <= dates[-1] - pd.Timedelta(days=125)]
    if smoke:
        qs = qs[-12:]

    rows = []
    panel_cross = {}
    rng_master = np.random.default_rng(13)
    for qi in range(1, len(qs)):
        p1, p = qs[qi - 1], qs[qi]
        dec = p + pd.Timedelta(days=LAG)
        if dec >= dates[-1] - pd.Timedelta(days=95):
            break
        cur = pn.snapshot_as_of(p, dec)
        prev = pn.snapshot_as_of(p1, dec)
        if min(len(cur), len(prev)) < 1000:
            continue
        i_p1 = dates.searchsorted(p1, side="right") - 1
        i_p = dates.searchsorted(p, side="right") - 1
        di = dates.searchsorted(dec, side="right") - 1
        px_p = mdta.prices_raw.iloc[i_p]
        px_p1 = mdta.prices_raw.iloc[i_p1]
        px_d = mdta.prices_raw.iloc[di]
        adv_lag = adv.iloc[i_p1]

        # ---- gestores elegiveis, choque f, chocados ----------------------- #
        m = cur[["filer_id", "instrument_id", "shares", "value_usd"]].merge(
            prev[["filer_id", "instrument_id", "shares"]],
            on=["filer_id", "instrument_id"], how="outer",
            suffixes=("", "_p"))
        m["tk"] = m["instrument_id"].map(cmap)
        m = m.dropna(subset=["tk"])
        m = m[m["tk"].map(px_d).notna()]                 # anti-fantasma
        m["q_p"] = m["shares_p"].fillna(0.0)
        m["q_c"] = m["shares"].fillna(0.0)
        m["dq"] = m["q_c"] - m["q_p"]
        m["pxp"] = m["tk"].map(px_p)
        m["pxp1"] = m["tk"].map(px_p1)
        m = m.dropna(subset=["pxp", "pxp1"])
        vprev = (m["q_p"] * m["pxp1"]).groupby(m["filer_id"]).sum()
        trade = (m["dq"] * m["pxp"]).groupby(m["filer_id"]).sum()
        npos = m[m["q_p"] > 0].groupby("filer_id").size()
        elig = vprev.index[(vprev >= 1e8) & (npos.reindex(vprev.index)
                                             .fillna(0) >= 15)]
        f = (trade / vprev).reindex(elig).replace(
            [np.inf, -np.inf], np.nan).dropna().clip(-1, 1)
        shocked = set(f.index[f <= f.quantile(SHOCK_PCTL)])
        if len(shocked) < 15:
            continue

        # ---- choque direto por acao (venda forcada realizada / ADV$) ------ #
        sold = m[m["filer_id"].isin(shocked)].copy()
        sold["sell_usd"] = (-sold["dq"]).clip(lower=0) * sold["pxp"]
        shock = sold.groupby("tk")["sell_usd"].sum()
        shock = (shock / adv_lag.reindex(shock.index)).replace(
            [np.inf, -np.inf], np.nan).fillna(0.0)

        # ---- grafo de co-ownership dos ativos elegiveis -------------------- #
        h = m[(m["q_c"] > 0) & m["filer_id"].isin(elig)].copy()
        h["v"] = h["q_c"] * h["tk"].map(px_p)
        held = h.groupby("tk")["filer_id"].nunique()
        stocks = held.index[held >= 5]
        h = h[h["tk"].isin(stocks)]
        tk_list = sorted(h["tk"].unique())
        tk_ix = {t: i for i, t in enumerate(tk_list)}
        mg_list = sorted(h["filer_id"].unique())
        mg_ix = {g: i for i, g in enumerate(mg_list)}
        r_ = h["filer_id"].map(mg_ix).values
        c_ = h["tk"].map(tk_ix).values
        V = sparse.csr_matrix((h["v"].values, (r_, c_)),
                              shape=(len(mg_list), len(tk_list)))
        B = sparse.csr_matrix((np.ones(len(h)), (r_, c_)), shape=V.shape)
        NUM = (V.T @ B + B.T @ V).toarray()              # sum_{i both}(v_ij+v_ik)
        np.fill_diagonal(NUM, 0.0)
        advv = adv_lag.reindex(tk_list).fillna(np.inf).values
        DEN = advv[:, None] + advv[None, :]
        G = NUM / DEN
        rs = G.sum(axis=1, keepdims=True)
        P = np.divide(G, rs, out=np.zeros_like(G), where=rs > 0)

        sh_vec = shock.reindex(tk_list).fillna(0.0).values
        spill = pd.Series(P @ sh_vec, index=tk_list)
        # placebo: mesmo grafo, choque embaralhado
        rng = np.random.default_rng(int(p.value) % (2**32))
        spill_pl = pd.Series(P @ rng.permutation(sh_vec), index=tk_list)

        # ---- sinal: spillover puro (metade de menor choque direto) -------- #
        direct = pd.Series(sh_vec, index=tk_list)
        low_direct = direct.index[direct <= direct.median()]
        nxt = qs[qi + 1] + pd.Timedelta(days=LAG) if qi + 1 < len(qs) \
            else dates[-1]
        fwd1 = forward_return(cum, dates, dec, min(nxt, dates[-1]))
        rev_end = min(nxt + pd.Timedelta(days=91), dates[-1])
        fwd2 = forward_return(cum, dates, min(nxt, dates[-1]), rev_end)

        for name, sp in [("tese", spill), ("placebo", spill_pl)]:
            s = sp.reindex(low_direct).dropna()
            s = s[px_d.reindex(s.index) >= 1.0]
            if len(s) < 150:
                continue
            r = s.rank(pct=True)
            hi = r.index[r >= 0.8]
            lo = r.index[r <= 0.2]
            f1h, f1l = fwd1.reindex(hi).dropna(), fwd1.reindex(lo).dropna()
            f2h, f2l = fwd2.reindex(hi).dropna(), fwd2.reindex(lo).dropna()
            if min(len(f1h), len(f1l)) < 15:
                continue
            rows.append({"period": p, "kind": name, "n": len(s),
                         "spread_q1": float(f1h.mean() - f1l.mean()),
                         "spread_q2": float(f2h.mean() - f2l.mean())
                         if min(len(f2h), len(f2l)) >= 15 else np.nan})
            if name == "tese":
                panel_cross[dates[min(di + 1, len(dates) - 1)]] = (1 - r)
        log(f"{p.date()}: {len(shocked)} chocados, grafo {len(tk_list)} nomes")

    e = pd.DataFrame(rows)
    e.to_csv(RESULTS / "grafo_events.csv", index=False)
    pd.DataFrame(panel_cross).T.sort_index().to_parquet(
        RESULTS / "grafo_panel.parquet")
    L = ["# Grafo de crowding - difusao de choques (M3)", ""]
    for kind, g in e.groupby("kind"):
        tag = "TESE" if kind == "tese" else "placebo (choque embaralhado)"
        L += [f"## {tag}",
              f"- spread spillover alto-baixo, tri+1: {g.spread_q1.mean():+.4f} "
              f"t={nw_tstat(g.spread_q1):+.2f} (pre-registrado NEGATIVO na tese)",
              f"- tri+2 (check de reversao tardia): {g.spread_q2.mean():+.4f} "
              f"t={nw_tstat(g.spread_q2.dropna()):+.2f}",
              f"- eventos: {len(g)} | nomes/tri: {g.n.mean():.0f}", ""]
    (RESULTS / "GRAFO_REPORT.md").write_text("\n".join(L), encoding="utf-8")
    log("done -> results/")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    main(**vars(ap.parse_args()))
