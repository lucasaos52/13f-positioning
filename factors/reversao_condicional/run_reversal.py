"""Reversao condicional - Coval-Stafford com decomposicao forcado/discricionario.

    python run_reversal.py [--smoke]

Pipeline (adaptacoes vs spec declaradas no cabecalho de cada etapa):
 1. snapshot PIT em d = t+50 (>99% arquivado; ragged real afeta <1%)
 2. V[j] por shares x preco Yahoo (nunca o campo value), cobertura >=60%
 3. choque f[j,t] = trade liquido a precos de fim de periodo / book anterior,
    com split (atomo modal) e guarda anti-venda-fantasma (so nomes vivos)
 4. decomposicao: Dq/q ~ a + b f + g (f x illiq), OLS expansivo via matrizes
    de Gram acumuladas SO com trimestres < t; Dq_forcado = fitted; residuo =
    discricionario (nao entra no sinal - Huang-Ringgenberg-Zhang)
 5. transitoriedade: hazard empirico P(choque repetir | k consecutivos),
    tabela expansiva por k in {1,2,3+} (adaptacao: logit -> nao-parametrico)
 6. Pressao[i] = -sum_chocados (1-pi) Dq_forcado / ShareADV defasado (Wardlaw)
 7. gate: %redutores nao-chocados - %redutores chocados; alto = noticia ->
    gate 0 (binario na mediana)
 8. score = pressao x gate; long = quintil superior; avaliacao no protocolo
    padrao (excesso vs universo + spread interno), NW. Direcao pre-registrada:
    POSITIVA (compra-se a reversao da pressao ja ocorrida).
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
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


def modal_split(cur, prev):
    pair = cur.merge(prev, on=["filer_id", "instrument_id"],
                     suffixes=("_c", "_p"))
    pair = pair[(pair["shares_p"] > 0) & (pair["shares_c"] > 0)]
    pair["ratio"] = (pair["shares_c"] / pair["shares_p"]).round(3)
    fac = {}
    for j, g in pair.groupby("instrument_id"):
        if len(g) < 10:
            continue
        c = g["ratio"].value_counts()
        mode, k = c.index[0], c.iloc[0]
        k2 = c.iloc[1] if len(c) > 1 else 0
        if abs(mode - 1) > 0.15 and (k >= 0.10 * len(g)
                                     or (k >= 30 and k >= 2.5 * k2)):
            fac[j] = float(mode)
    return pd.Series(fac, dtype=float)


def main(smoke: bool = False) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    cmap, mdta = load_market()
    dates = mdta.prices.index
    cum = mdta.returns.cumsum()
    vol_sh = mdta.volume.rolling(63, min_periods=20).median()   # ADV em ACOES

    qs = [q for q in pn.quarters()
          if pd.Timestamp("2013-06-30") <= q <= dates[-1] - pd.Timedelta(days=125)]
    if smoke:
        qs = qs[-12:]

    # expanding state
    G = np.zeros((3, 3))          # Gram X'X (1, f, f*illiq)
    Gy = np.zeros(3)              # X'y
    n_obs = 0
    shock_hist: dict[str, list] = defaultdict(list)   # filer -> consec count
    hazard_num = defaultdict(int)
    hazard_den = defaultdict(int)
    prev_shocked: dict[str, int] = {}
    rows, betas = [], []
    panel_cross = {}

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
        shadv = vol_sh.iloc[i_p1]                     # defasado (Wardlaw)

        # ---- 2/3: books e choque f via Dq a precos de fim de periodo ----- #
        fac = modal_split(cur, prev)
        m = cur[["filer_id", "instrument_id", "shares"]].merge(
            prev[["filer_id", "instrument_id", "shares"]],
            on=["filer_id", "instrument_id"], how="outer",
            suffixes=("_c", "_p"))
        m["tk"] = m["instrument_id"].map(cmap)
        m = m.dropna(subset=["tk"])
        m["alive"] = m["tk"].map(px_d).notna()
        m = m[m["alive"]]                              # anti-venda-fantasma
        f_split = m["instrument_id"].map(fac).fillna(1.0)
        m["q_p"] = m["shares_p"].fillna(0.0) * f_split
        m["q_c"] = m["shares_c"].fillna(0.0)
        m["dq"] = m["q_c"] - m["q_p"]
        m["px_p"] = m["tk"].map(px_p)
        m["px_p1"] = m["tk"].map(px_p1)
        m = m.dropna(subset=["px_p", "px_p1"])
        vprev = (m["q_p"] * m["px_p1"]).groupby(m["filer_id"]).sum()
        trade = (m["dq"] * m["px_p"]).groupby(m["filer_id"]).sum()
        npos = m[m["q_p"] > 0].groupby("filer_id").size()
        elig = vprev.index[(vprev >= 1e8) & (npos.reindex(vprev.index) >= 15)]
        f = (trade / vprev).reindex(elig).replace(
            [np.inf, -np.inf], np.nan).dropna().clip(-1, 1)
        thr = f.quantile(SHOCK_PCTL)
        shocked = set(f.index[f <= thr])

        # ---- 5: hazard update (com dados ate t-1) e pesos (1-pi) ---------- #
        pi_w = {}
        for j in shocked:
            k = min(prev_shocked.get(j, 0), 3)
            den = hazard_den.get(k, 0)
            pi = hazard_num.get(k, 0) / den if den >= 20 else 0.4
            pi_w[j] = 1.0 - pi
        # update hazard com a transicao t-1 -> t (informacao ja publica em d)
        for j, k in prev_shocked.items():
            kk = min(k, 3)
            hazard_den[kk] += 1
            if j in shocked:
                hazard_num[kk] += 1
        nxt_state = {}
        for j in shocked:
            nxt_state[j] = prev_shocked.get(j, 0) + 1
        prev_shocked = nxt_state

        # ---- 4: decomposicao com Gram ANTERIOR a t ------------------------ #
        if n_obs > 50000:
            beta = np.linalg.solve(G + 1e-8 * np.eye(3), Gy)
        else:
            beta = np.array([0.0, 1.0, 0.0])          # prior: pro-rata puro
        betas.append({"period": p, "beta_f": beta[1], "gamma": beta[2],
                      "n_obs": n_obs})

        mm = m[(m["q_p"] > 0) & m["filer_id"].isin(f.index)].copy()
        mm["y"] = (mm["dq"] / mm["q_p"]).clip(-1, 3)
        mm["fj"] = mm["filer_id"].map(f)
        illiq = (1.0 / mm["tk"].map(shadv)).rank(pct=True).fillna(0.5)
        mm["fx"] = mm["fj"] * illiq
        # fitted (forcado) com beta de ATE t-1
        mm["dq_forced"] = (beta[1] * mm["fj"] + beta[2] * mm["fx"]) * mm["q_p"]
        # acumula Gram com o trimestre t para uso FUTURO
        X = np.column_stack([np.ones(len(mm)), mm["fj"].values, mm["fx"].values])
        ok = np.isfinite(X).all(axis=1) & np.isfinite(mm["y"].values)
        G += X[ok].T @ X[ok]
        Gy += X[ok].T @ mm["y"].values[ok]
        n_obs += int(ok.sum())

        # ---- 6: pressao por papel ----------------------------------------- #
        sh = mm[mm["filer_id"].isin(shocked)].copy()
        if len(sh) < 200:
            continue
        sh["w"] = sh["filer_id"].map(pi_w).fillna(0.6)
        raw = (sh["w"] * sh["dq_forced"]).groupby(sh["tk"]).sum()
        pressure = (-raw / shadv.reindex(raw.index)).replace(
            [np.inf, -np.inf], np.nan).dropna()
        pressure = pressure[pressure > 0]              # sofreu venda forcada

        # ---- 7: gate de informacao ---------------------------------------- #
        red = mm.assign(is_red=(mm["dq"] < 0).astype(float),
                        is_shk=mm["filer_id"].isin(shocked))
        g_ns = red[~red["is_shk"]].groupby("tk")["is_red"].mean()
        g_sh = red[red["is_shk"]].groupby("tk")["is_red"].mean()
        disc = (g_ns - g_sh).reindex(pressure.index)
        gate = (disc <= disc.median()).astype(float).fillna(0.0)

        score = (pressure * gate)
        score = score[score > 0]
        if len(score) < 60:
            continue
        r = np.log1p(score).rank(pct=True)
        panel_cross[dates[min(di + 1, len(dates) - 1)]] = r

        # ---- 8: avaliacao -------------------------------------------------- #
        nxt = qs[qi + 1] + pd.Timedelta(days=LAG) if qi + 1 < len(qs) else dates[-1]
        fwd = forward_return(cum, dates, dec, min(nxt, dates[-1]))
        uni = px_d.index[px_d >= 1.0]
        u_mean = float(fwd.reindex(uni).dropna().mean())
        top = r.index[r >= r.quantile(0.8)]
        bot = r.index[r <= r.quantile(0.2)]
        ftop = fwd.reindex(top).dropna()
        fbot = fwd.reindex(bot).dropna()
        if len(ftop) < 12:
            continue
        rows.append({"period": p, "n_scored": len(score),
                     "n_shocked_mgrs": len(shocked),
                     "long_excess": float(ftop.mean() - u_mean),
                     "spread_internal": float(ftop.mean() - fbot.mean()),
                     "gate_pass": float(gate.mean())})
        log(f"{p.date()}: {len(shocked)} chocados, {len(score)} nomes, "
            f"long_exc {rows[-1]['long_excess']:+.4f}")

    e = pd.DataFrame(rows)
    b = pd.DataFrame(betas)
    e.to_csv(RESULTS / "reversal_events.csv", index=False)
    b.to_csv(RESULTS / "betas.csv", index=False)
    pd.DataFrame(panel_cross).T.sort_index().to_parquet(
        RESULTS / "reversal_panel.parquet")

    L = ["# Reversao condicional - resultados", ""]
    if len(e):
        L += [f"- long (quintil top do score) excesso vs universo: "
              f"{e.long_excess.mean():+.4f}/tri t={nw_tstat(e.long_excess):+.2f}"
              f" | Sharpe {e.long_excess.mean()/e.long_excess.std()*2:.2f}",
              f"- spread interno top-bottom: {e.spread_internal.mean():+.4f}/tri "
              f"t={nw_tstat(e.spread_internal):+.2f}",
              f"- eventos: {len(e)} | nomes scorados/tri: {e.n_scored.mean():.0f} "
              f"| gestores chocados/tri: {e.n_shocked_mgrs.mean():.0f}",
              "",
              f"- beta_f final: {b.beta_f.iloc[-1]:+.3f} (1 = pro-rata; "
              f"Coval-Stafford) | gamma final: {b.gamma.iloc[-1]:+.3f} "
              f"(0 = corte horizontal, !=0 = pecking)",
              "- direcao pre-registrada: POSITIVA (compra da reversao)"]
    (RESULTS / "REVERSAL_REPORT.md").write_text("\n".join(L), encoding="utf-8")
    log("done -> results/")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    main(**vars(ap.parse_args()))
