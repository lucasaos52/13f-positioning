"""Overhang restante - a oferta que ainda nao chegou.

Refina o distress_mom com a variavel que o 13F entrega de graca: quanto os
vendedores forcados AINDA seguram do nome depois da venda observada.
Liquidacao leva 2-4 tri (hazard 40%, medido) -> overhang alto = mais oferta
a caminho -> continuacao forte; overhang ~zero = liquidacao completa ->
pressao acabou (onset da reversao tardia de 12-15m).

P1: dentro do coorte vendido, spread(overhang alto - baixo) NEGATIVO q+1
P2: excesso dos "zerados" (overhang<=0.5 dia ADV) ~0 ou positivo
P3: short do distress_mom so em overhang alto > short original (pareado)
"""
import sys
from pathlib import Path
import numpy as np, pandas as pd
HERE = Path(__file__).resolve().parent
for sub in ("", "general_plan", "fire_calendar"):
    sys.path.insert(0, str(HERE.parent / sub))
import panel as pn
from backtest_gp import forward_return, nw_tstat
from run_all import load_market, log
from run_fire import implied_flows

RESULTS = HERE / "results"
LAG = 50
smoke = "--smoke" in sys.argv

cmap, mdta = load_market()
dates = mdta.prices.index
cum = mdta.returns.cumsum()
adv = mdta.dollar_volume.rolling(63, min_periods=20).median()
qs = [q for q in pn.quarters() if pd.Timestamp("2013-06-30") <= q <= dates[-1] - pd.Timedelta(days=125)]
if smoke: qs = qs[-12:]

rows = []
for qi in range(1, len(qs)):
    p1, p = qs[qi-1], qs[qi]
    dec = p + pd.Timedelta(days=LAG)
    if dec >= dates[-1] - pd.Timedelta(days=95): break
    cur = pn.snapshot_as_of(p, dec)
    prev = pn.snapshot_as_of(p1, dec)
    if min(len(cur), len(prev)) < 1000: continue
    i1 = dates.searchsorted(p1, side="right") - 1
    i0 = dates.searchsorted(p, side="right") - 1
    di = dates.searchsorted(dec, side="right") - 1
    px0 = mdta.prices_raw.iloc[i0]; pxd = mdta.prices_raw.iloc[di]
    adv_d = adv.iloc[di]
    ret_q = cum.iloc[i0] - cum.iloc[i1]

    fl = implied_flows(cur, prev, cmap, ret_q)
    dis = set(fl.index[fl["flow"] < -0.10])
    if len(dis) < 15: continue

    m = cur[["filer_id","instrument_id","shares"]].merge(
        prev[["filer_id","instrument_id","shares"]],
        on=["filer_id","instrument_id"], how="outer", suffixes=("","_p"))
    m["tk"] = m["instrument_id"].map(cmap)
    m = m.dropna(subset=["tk"]); m = m[m["tk"].map(pxd).notna()]
    m["dq"] = m["shares"].fillna(0) - m["shares_p"].fillna(0)
    m["px"] = m["tk"].map(px0)
    md_ = m[m["filer_id"].isin(dis)]
    sold_usd = ((-md_["dq"]).clip(lower=0) * md_["px"]).groupby(md_["tk"]).sum()
    remain_usd = (md_["shares"].fillna(0) * md_["px"]).groupby(md_["tk"]).sum()
    sold_adv = (sold_usd / adv_d.reindex(sold_usd.index)).replace([np.inf,-np.inf], np.nan).dropna()
    over_adv = (remain_usd.reindex(sold_adv.index).fillna(0.0)
                / adv_d.reindex(sold_adv.index))

    cohort = sold_adv[sold_adv >= sold_adv.quantile(2/3)].index
    cohort = [t for t in cohort if pxd.get(t, 0) >= 1.0]
    if len(cohort) < 60: continue
    ov = over_adv.reindex(cohort)

    nxt = qs[qi+1] + pd.Timedelta(days=LAG) if qi+1 < len(qs) else dates[-1]
    fwd = forward_return(cum, dates, dec, min(nxt, dates[-1]))
    f_c = fwd.reindex(cohort).dropna()
    uni_mean = float(fwd.reindex(pxd.index[pxd >= 1.0]).dropna().mean())

    hi = [t for t in cohort if ov.get(t, 0) >= ov.quantile(2/3)]
    lo = [t for t in cohort if ov.get(t, 0) <= ov.quantile(1/3)]
    done = [t for t in cohort if ov.get(t, 0) <= 0.5]      # <= meio dia de ADV
    fh, fl_, fd = f_c.reindex(hi).dropna(), f_c.reindex(lo).dropna(), f_c.reindex(done).dropna()
    if min(len(fh), len(fl_)) < 10: continue
    rows.append({
        "period": p, "n_cohort": len(cohort), "n_done": len(fd),
        "p1_spread": float(fh.mean() - fl_.mean()),
        "p2_done_exc": float(fd.mean() - uni_mean) if len(fd) >= 8 else np.nan,
        "p3_short_all": float(f_c.mean() - uni_mean),
        "p3_short_hi": float(fh.mean() - uni_mean)})
    log(f"{p.date()}: coorte {len(cohort)}, zerados {len(fd)}, "
        f"P1 {rows[-1]['p1_spread']:+.4f}")

e = pd.DataFrame(rows)
e.to_csv(RESULTS / "overhang_events.csv", index=False)
d3 = (e["p3_short_hi"] - e["p3_short_all"]).dropna()
L = ["# Overhang restante - resultados", "",
     f"- coorte medio {e.n_cohort.mean():.0f} | zerados/tri {e.n_done.mean():.0f}", "",
     f"## P1 (gradiente): spread overhang alto-baixo q+1: {e.p1_spread.mean():+.4f}/tri "
     f"t={nw_tstat(e.p1_spread):+.2f} | pre-registro: NEGATIVO",
     f"## P2 (zerados param de cair): excesso {e.p2_done_exc.mean():+.4f}/tri "
     f"t={nw_tstat(e.p2_done_exc.dropna()):+.2f} | pre-registro: ~0 ou positivo "
     f"(coorte todo: {e.p3_short_all.mean():+.4f})",
     f"## P3 (refinamento do short): coorte {e.p3_short_all.mean():+.4f} vs "
     f"overhang alto {e.p3_short_hi.mean():+.4f} | delta pareado "
     f"{d3.mean():+.4f} t={nw_tstat(d3):+.2f} | pre-registro: MAIS negativo"]
(RESULTS / "OVERHANG_REPORT.md").write_text("\n".join(L), encoding="utf-8")
print("\n".join(L))
