"""Absorcao - a qualidade do comprador do outro lado da venda forcada.

    python run_absorcao.py [--smoke]

Cruzamento de duas maquinas validadas DESTE projeto:
  - venda forcada por acao (gestores em distress por fluxo implicito;
    detector validado t=+13,8 contra vendas realizadas);
  - compra de CONVICCAO FRESCA por acao (posicao nova/crescida >=25% que
    entra no top-decil do book do comprador - o nucleo do new_conviction,
    t=+3,27).

Hipotese (pre-registrada): a continuacao da queda pos-venda-forcada
(distress_mom) esconde dois regimes -
  ABSORVIDA por conviccao fresca  -> piso informado -> estabiliza/reverte
  absorvida por NINGUEM           -> continua caindo (o distress_mom puro)
Predicoes:
  P1 dentro do coorte de venda forcada alta: spread(absorcao alta - zero)
     POSITIVO em q+1;
  P2 refinamento: short do distress_mom restrito a absorcao BAIXA deve ser
     mais forte que o short original (delta pareado);
  P3 placebo: absorcao por compradores SEM conviccao (adds pequenos,
     pro-rata) nao deve separar nada - o que importa e QUEM absorve.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sps

HERE = Path(__file__).resolve().parent
for sub in ("", "general_plan", "fire_calendar"):
    sys.path.insert(0, str(HERE.parent / sub))

import panel as pn                                  # noqa: E402
from backtest_gp import forward_return, nw_tstat    # noqa: E402
from run_all import load_market, log                # noqa: E402
from run_fire import implied_flows                  # noqa: E402

RESULTS = HERE / "results"
LAG = 50


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
        px0 = mdta.prices_raw.iloc[i0]
        pxd = mdta.prices_raw.iloc[di]
        adv_d = adv.iloc[di]
        ret_q = cum.iloc[i0] - cum.iloc[i1]

        # ---- lado vendedor: venda forcada por acao ------------------------ #
        fl = implied_flows(cur, prev, cmap, ret_q)
        dis = set(fl.index[fl["flow"] < -0.10])
        if len(dis) < 15:
            continue
        m = cur[["filer_id", "instrument_id", "shares", "value_usd"]].merge(
            prev[["filer_id", "instrument_id", "shares"]],
            on=["filer_id", "instrument_id"], how="outer",
            suffixes=("", "_p"))
        m["tk"] = m["instrument_id"].map(cmap)
        m = m.dropna(subset=["tk"])
        m = m[m["tk"].map(pxd).notna()]
        m["dq"] = m["shares"].fillna(0) - m["shares_p"].fillna(0)
        m["px"] = m["tk"].map(px0)
        sold = m[m["filer_id"].isin(dis)]
        forced = ((-sold["dq"]).clip(lower=0) * sold["px"]) \
            .groupby(sold["tk"]).sum()
        forced_adv = (forced / adv_d.reindex(forced.index)).replace(
            [np.inf, -np.inf], np.nan).dropna()

        # ---- lado comprador: conviccao fresca em $ ------------------------ #
        c2 = cur.copy()
        c2["w"] = c2["value_usd"] / c2.groupby("filer_id")["value_usd"] \
            .transform("sum")
        thr = c2.groupby("filer_id")["w"].transform(lambda s: s.quantile(0.9))
        mm = c2.merge(prev[["filer_id", "instrument_id", "shares"]],
                      on=["filer_id", "instrument_id"], how="left",
                      suffixes=("", "_p"))
        mm["thr"] = thr.values
        mm["tk"] = mm["instrument_id"].map(cmap)
        mm = mm.dropna(subset=["tk"])
        mm["dq_buy"] = (mm["shares"] - mm["shares_p"].fillna(0)).clip(lower=0)
        mm["buy_usd"] = mm["dq_buy"] * mm["tk"].map(px0)
        fresh = (mm["shares_p"].isna()) | (mm["shares"] >= 1.25 * mm["shares_p"])
        conv = fresh & (mm["w"] >= mm["thr"]) & ~mm["filer_id"].isin(dis)
        nonconv = fresh & (mm["w"] < mm["thr"] * 0.5) & ~mm["filer_id"].isin(dis)
        buy_conv = mm.loc[conv].groupby("tk")["buy_usd"].sum()
        buy_non = mm.loc[nonconv].groupby("tk")["buy_usd"].sum()

        # ---- coorte e absorcao -------------------------------------------- #
        cohort = forced_adv[forced_adv >= forced_adv.quantile(2 / 3)].index
        cohort = [t for t in cohort if pxd.get(t, 0) >= 1.0]
        if len(cohort) < 60:
            continue
        fsold = forced.reindex(cohort)
        absorb = (buy_conv.reindex(cohort).fillna(0.0) / fsold).clip(0, 5)
        absorb_pl = (buy_non.reindex(cohort).fillna(0.0) / fsold).clip(0, 5)

        nxt = qs[qi + 1] + pd.Timedelta(days=LAG) if qi + 1 < len(qs) \
            else dates[-1]
        fwd = forward_return(cum, dates, dec, min(nxt, dates[-1]))
        f_c = fwd.reindex(cohort).dropna()
        rec = {"period": p, "n_cohort": len(cohort),
               "frac_absorbed": float((absorb > 0.25).mean())}
        for name, ab in [("tese", absorb), ("placebo", absorb_pl)]:
            hi = [t for t in cohort if ab.get(t, 0) >= 0.5]
            lo = [t for t in cohort if ab.get(t, 0) <= 0.05]
            fh, fl_ = f_c.reindex(hi).dropna(), f_c.reindex(lo).dropna()
            if min(len(fh), len(fl_)) >= 10:
                rec[f"{name}_spread"] = float(fh.mean() - fl_.mean())
                rec[f"{name}_n_hi"] = len(fh)
        # P2: short do distress_mom refinado (so nao-absorvidos)
        uni_mean = float(fwd.reindex(pxd.index[pxd >= 1.0]).dropna().mean())
        short_all = f_c.mean() - uni_mean
        lo_t = [t for t in cohort if absorb.get(t, 0) <= 0.05]
        f_lo = f_c.reindex(lo_t).dropna()
        if len(f_lo) >= 10:
            rec["short_all_exc"] = float(short_all)
            rec["short_unabs_exc"] = float(f_lo.mean() - uni_mean)
        rows.append(rec)
        log(f"{p.date()}: coorte {len(cohort)}, "
            f"absorvidos {rec['frac_absorbed']:.0%}")

    e = pd.DataFrame(rows)
    e.to_csv(RESULTS / "absorcao_events.csv", index=False)
    L = ["# Absorcao - quem compra do vendedor forcado", "",
         f"- coorte medio: {e.n_cohort.mean():.0f} nomes/tri | "
         f"fracao com absorcao >25%: {e.frac_absorbed.mean():.0%}", ""]
    for name, lbl in [("tese", "TESE (absorcao por conviccao fresca)"),
                      ("placebo", "placebo (compradores sem conviccao)")]:
        col = f"{name}_spread"
        if col in e:
            s = e[col].dropna()
            L.append(f"## {lbl}")
            L.append(f"- spread (absorvida alta - zero) q+1: "
                     f"{s.mean():+.4f}/tri t={nw_tstat(s):+.2f} (n={len(s)}) "
                     "| P1 pre-registrada: POSITIVO na tese")
            L.append("")
    if "short_unabs_exc" in e:
        d = (e["short_unabs_exc"] - e["short_all_exc"]).dropna()
        L += ["## P2: refinamento do short do distress_mom",
              f"- excesso do coorte todo: {e.short_all_exc.mean():+.4f}/tri",
              f"- excesso so dos NAO-absorvidos: "
              f"{e.short_unabs_exc.mean():+.4f}/tri",
              f"- delta pareado (deve ser MAIS negativo): {d.mean():+.4f} "
              f"t={nw_tstat(d):+.2f}"]
    (RESULTS / "ABSORCAO_REPORT.md").write_text("\n".join(L), encoding="utf-8")
    log("done -> results/")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    main(**vars(ap.parse_args()))
