"""Decomposicao drift-fluxo-rotacao (nota de desenho 15/08/2026).

    python run_dfr.py [--smoke]

Cadeia aninhada, do sujo ao limpo (cada seta = uma hipotese testada):
    dW_bruto (w_t - w_{t-1})  ->  D (w_t - w_til, mata fluxo+drift)
                              ->  D_perp (M_B D, mata rotacao de fator)
Previsao pre-registrada: IC melhora monotonicamente na cadeia; na corrida
Fama-MacBeth so D_perp sobrevive; o placebo de drift (w_til - w_{t-1})
preve retorno como momento defasado (controle positivo).

Adaptacoes declaradas vs a nota:
  - retorno de preco = Yahoo Close cru (split-ajustado retroativo, sem
    dividendo) - exatamente o exigido pelo passo 2;
  - B sem book-to-market e sem setor (sem Compustat/GICS gratis PIT);
    duas especificacoes reportadas: B1=[1,size,mom], B2=[1,size,mom,beta,vol]
    - a dispersao entre elas e o teste de robustez da propria nota (secao 7);
  - extensao 1 (desconto de redundancia GLS, c_i = 1/sum_j S_ij) como
    variante do agregador;
  - confidential reveals nao sinalizados na v1 (declarado).
Tudo PIT em D+50 por filed_date; pesos = shares x preco (nunca o campo
value); entradas/saidas automaticas via uniao de nomes (D=w_t na entrada,
D=-w_til na saida); 1'D = 0 preservado pela projecao (intercepto em B).
"""
from __future__ import annotations

import argparse
import sys
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


def main(smoke: bool = False) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    cmap, mdta = load_market()
    dates = mdta.prices.index
    cum = mdta.returns.cumsum()                       # total (avaliacao)
    px_raw = mdta.prices_raw                          # preco split-adj s/ div
    cum_adj = mdta.prices.pct_change(fill_method=None).fillna(0).cumsum()
    mom = cum_adj.shift(21) - cum_adj.shift(252)
    beta_w = mdta.returns.rolling(252, min_periods=126)
    shares = mc.shares_panel(dates, mdta.tickers, mdta.prices, px_raw)
    mcap = mc.mktcap_panel(px_raw, shares)
    bench = mdta.benchmark_returns

    qs = [q for q in pn.quarters()
          if pd.Timestamp("2013-06-30") <= q <= dates[-1] - pd.Timedelta(days=125)]
    if smoke:
        qs = qs[-12:]

    ev, fm_rows, var_rows, panel_cross = [], [], [], {}
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
        r_px = (px_raw.iloc[i0] / px_raw.iloc[i1] - 1.0)   # retorno de PRECO
        pxd = px_raw.iloc[di]
        mc_d = mcap.iloc[di]

        # ---- pesos por gestor (shares x preco), uniao de nomes ----------- #
        m = cur[["filer_id", "instrument_id", "shares"]].merge(
            prev[["filer_id", "instrument_id", "shares"]],
            on=["filer_id", "instrument_id"], how="outer",
            suffixes=("_c", "_p"))
        m["tk"] = m["instrument_id"].map(cmap)
        m = m.dropna(subset=["tk"])
        m = m[m["tk"].map(pxd).notna()]
        m["v_c"] = m["shares_c"].fillna(0.0) * m["tk"].map(px_raw.iloc[i0])
        m["v_p"] = m["shares_p"].fillna(0.0) * m["tk"].map(px_raw.iloc[i1])
        m = m.dropna(subset=["v_c", "v_p"])
        tot_c = m.groupby("filer_id")["v_c"].transform("sum")
        tot_p = m.groupby("filer_id")["v_p"].transform("sum")
        stats = m.groupby("filer_id").agg(aum=("v_c", "sum"),
                                          n=("v_c", lambda x: (x > 0).sum()))
        elig = stats.index[(stats["n"] >= 20) & (stats["aum"] >= 5e8)]
        m = m[m["filer_id"].isin(elig) & (tot_c > 0) & (tot_p > 0)]
        tot_c, tot_p = tot_c.loc[m.index], tot_p.loc[m.index]
        m["w"] = m["v_c"] / tot_c
        m["w_prev"] = m["v_p"] / tot_p
        # contrafactual buy-and-hold em retorno de PRECO
        m["grow"] = m["w_prev"] * (1.0 + m["tk"].map(r_px).fillna(0.0))
        m["w_til"] = m["grow"] / m.groupby("filer_id")["grow"].transform("sum")
        m["d_raw"] = m["w"] - m["w_prev"]
        m["d"] = m["w"] - m["w_til"]
        m["drift"] = m["w_til"] - m["w_prev"]          # placebo

        # ---- projecao fora dos fatores (por gestor), duas specs B -------- #
        bmat = pd.DataFrame({
            "size": np.log(mc_d), "mom": mom.iloc[di],
            "beta": pd.Series(dtype=float), "vol": mdta.volatility.iloc[di]})
        # beta simples 252d vs benchmark
        rb = bench.iloc[max(0, di - 252):di + 1]
        rs = mdta.returns.iloc[max(0, di - 252):di + 1]
        bvar = float(rb.var())
        if bvar > 0:
            bmat["beta"] = rs.apply(lambda c: c.cov(rb)) / bvar
        m["b_size"] = m["tk"].map(bmat["size"])
        m["b_mom"] = m["tk"].map(bmat["mom"])
        m["b_beta"] = m["tk"].map(bmat["beta"])
        m["b_vol"] = m["tk"].map(bmat["vol"])

        def project(g, cols):
            X = np.column_stack([np.ones(len(g))]
                                + [g[c].fillna(g[c].median()).values
                                   for c in cols])
            y = g["d"].values
            try:
                b, *_ = np.linalg.lstsq(X, y, rcond=None)
                return y - X @ b
            except np.linalg.LinAlgError:
                return y - y.mean()

        for spec, cols in [("B1", ["b_size", "b_mom"]),
                           ("B2", ["b_size", "b_mom", "b_beta", "b_vol"])]:
            m[f"dperp_{spec}"] = np.concatenate(
                [project(g, cols) for _, g in m.groupby("filer_id", sort=True)]) \
                if False else m.groupby("filer_id", group_keys=False) \
                .apply(lambda g: pd.Series(project(g, cols), index=g.index))

        # extensao 1: desconto de redundancia (cosseno entre gestores)
        piv = m.pivot_table(index="filer_id", columns="tk", values="w",
                            aggfunc="sum").fillna(0.0)
        W = piv.values
        norms = np.linalg.norm(W, axis=1, keepdims=True)
        Wn = W / np.maximum(norms, 1e-12)
        S = Wn @ Wn.T
        c_i = pd.Series(1.0 / np.maximum(S.sum(axis=1), 1e-6), index=piv.index)
        m["c_red"] = m["filer_id"].map(c_i)

        # ---- agregacao por acao ------------------------------------------- #
        agg = m.groupby("tk").agg(
            f_raw=("d_raw", "sum"), f_mid=("d", "sum"),
            f_perp=("dperp_B1", "sum"), f_perp2=("dperp_B2", "sum"),
            f_drift=("drift", "sum"))
        wred = (m["dperp_B1"] * m["c_red"]).groupby(m["tk"]).sum()
        agg["f_gls"] = wred

        # atribuicao de variancia (media entre gestores)
        v_raw = m.groupby("filer_id")["d_raw"].var()
        v_d = m.groupby("filer_id")["d"].var()
        v_perp = m.groupby("filer_id")["dperp_B1"].var()
        var_rows.append({"period": p,
                         "share_drift_seq": float(1 - (v_d / v_raw).median()),
                         "share_rot": float(1 - (v_perp / v_d).median())})

        # ---- avaliacao: universo, quintis, IC, FM -------------------------- #
        uni = agg.index[(pxd.reindex(agg.index) >= 5.0)
                        & (mc_d.reindex(agg.index) >= 5e8)]
        A = agg.loc[agg.index.isin(uni)]
        if len(A) < 300:
            continue
        nxt = qs[qi + 1] + pd.Timedelta(days=LAG) if qi + 1 < len(qs) \
            else dates[-1]
        fwd = forward_return(cum, dates, dec, min(nxt, dates[-1])).reindex(A.index)
        rec = {"period": p, "n": len(A)}
        for col in ("f_raw", "f_mid", "f_perp", "f_perp2", "f_gls", "f_drift"):
            r = A[col].rank(pct=True)
            df = pd.concat([r.rename("s"), fwd.rename("f")], axis=1).dropna()
            q5 = pd.qcut(df["s"].rank(method="first"), 5, labels=False)
            rec[f"ic_{col}"] = float(sps.spearmanr(df["s"], df["f"])[0])
            rec[f"sp_{col}"] = float(df["f"][q5 == 4].mean()
                                     - df["f"][q5 == 0].mean())
        # FM horse race: fwd ~ ranks dos tres aninhados
        X = pd.concat([A["f_raw"].rank(pct=True), A["f_mid"].rank(pct=True),
                       A["f_perp"].rank(pct=True)], axis=1)
        df = pd.concat([X, fwd.rename("y")], axis=1).dropna()
        Xn = np.column_stack([np.ones(len(df)), df.iloc[:, :3].values])
        try:
            bfm, *_ = np.linalg.lstsq(Xn, df["y"].values, rcond=None)
            fm_rows.append({"period": p, "b_raw": bfm[1], "b_mid": bfm[2],
                            "b_perp": bfm[3]})
        except np.linalg.LinAlgError:
            pass
        # corr do placebo de drift com momento (controle positivo)
        rec["corr_drift_mom"] = float(sps.spearmanr(
            A["f_drift"].rank(), mom.iloc[di].reindex(A.index).rank(),
            nan_policy="omit")[0])
        ev.append(rec)
        panel_cross[dates[min(di + 1, len(dates) - 1)]] = \
            A["f_perp"].rank(pct=True)
        log(f"{p.date()}: {len(A)} nomes, {len(elig)} gestores")

    e = pd.DataFrame(ev)
    fm = pd.DataFrame(fm_rows)
    vr = pd.DataFrame(var_rows)
    e.to_csv(RESULTS / "dfr_events.csv", index=False)
    fm.to_csv(RESULTS / "dfr_fm.csv", index=False)
    pd.DataFrame(panel_cross).T.sort_index().to_parquet(
        RESULTS / "dfr_panel.parquet")

    L = ["# Drift-fluxo-rotacao - resultados", "",
         "## Cadeia aninhada (IC medio | spread EW/tri, t NW)"]
    for col, lbl in [("f_raw", "dW bruto (sujo)"), ("f_mid", "D (sem drift/fluxo)"),
                     ("f_perp", "D_perp B1 (so aposta de nome)"),
                     ("f_perp2", "D_perp B2 (robustez)"),
                     ("f_gls", "D_perp + desconto GLS")]:
        L.append(f"- {lbl}: IC {e[f'ic_{col}'].mean():+.4f} | "
                 f"spread {e[f'sp_{col}'].mean():+.4f} "
                 f"t={nw_tstat(e[f'sp_{col}']):+.2f}")
    L += ["", "## Placebo de drift (controle positivo)",
          f"- IC do drift puro: {e['ic_f_drift'].mean():+.4f} | spread "
          f"{e['sp_f_drift'].mean():+.4f} t={nw_tstat(e['sp_f_drift']):+.2f}",
          f"- corr(drift, momento 12-1): {e['corr_drift_mom'].mean():+.2f} "
          "(deve ser ALTA - drift e momento disfarcado)"]
    if len(fm):
        L += ["", "## Corrida Fama-MacBeth (so D_perp deve sobreviver)"]
        for c in ("b_raw", "b_mid", "b_perp"):
            s = fm[c]
            L.append(f"- {c}: {s.mean():+.5f} t={nw_tstat(s):+.2f}")
    if len(vr):
        L += ["", "## Atribuicao de variancia (medianas, sequencial)",
              f"- fatia drift+fluxo em dW bruto: {vr.share_drift_seq.mean():.0%}",
              f"- fatia rotacao de fator em D: {vr.share_rot.mean():.0%}",
              "- (aposta da nota: drift e a maior fatia - a literatura de dIO "
              "mede drift sem saber)"]
    (RESULTS / "DFR_REPORT.md").write_text("\n".join(L), encoding="utf-8")
    log("done -> results/")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    main(**vars(ap.parse_args()))
