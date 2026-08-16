"""M5 - Fire-Sale Forward Calendar (see original_methods/M5_FIRE_CALENDAR.md).

    python run_fire.py [--smoke]

Stage 1 validates the MACHINE against realized sales (no returns involved);
stage 2 tests price pressure and reversal. Directions pre-registered:
  distress -> next-quarter selling, concentrated in liquid (pecking) names;
  predicted-supply names -> negative excess in the pressure quarter,
  positive in the reversal quarter. Placebo: supply built from healthy
  managers must show neither.
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
DISTRESS_FLOW = -0.10       # implied outflow worse than -10%/quarter
MIN_COVER = 0.60            # book value mapped to tickers


def implied_flows(cur, prev, cmap, ret_q):
    """Per-filer implied flow = AUM growth minus frozen-book return."""
    a_prev = prev.groupby("filer_id")["value_usd"].sum()
    a_cur = cur.groupby("filer_id")["value_usd"].sum()
    b = prev.copy()
    b["ticker"] = b["instrument_id"].map(cmap)
    b["r"] = b["ticker"].map(ret_q)
    b["v_ok"] = b["value_usd"].where(b["r"].notna(), 0.0)
    b["vr"] = b["value_usd"] * b["r"].fillna(0.0)
    g = b.groupby("filer_id")
    tot = g["value_usd"].sum()
    cover = g["v_ok"].sum() / tot.clip(lower=1.0)
    rbook = g["vr"].sum() / tot.clip(lower=1.0)
    n_pos = g.size()
    df = pd.DataFrame({"aum_prev": a_prev, "aum_cur": a_cur,
                       "rbook": rbook, "cover": cover, "n": n_pos}).dropna()
    df = df[(df["n"] >= 15) & (df["aum_prev"] >= 1e8)
            & (df["cover"] >= MIN_COVER)]
    df["flow"] = df["aum_cur"] / df["aum_prev"] - (1.0 + df["rbook"])
    return df


def main(smoke: bool = False) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    cmap, mdta = load_market()
    dates = mdta.prices.index
    cum = mdta.returns.cumsum()
    adv = mdta.dollar_volume.rolling(63, min_periods=20).median()

    qs = [q for q in pn.quarters()
          if pd.Timestamp("2013-06-30") <= q <= dates[-1] - pd.Timedelta(days=125)]
    if smoke:
        qs = qs[-10:]

    stage1, stage2 = [], []
    for qi in range(1, len(qs) - 1):
        p1, p, p_next = qs[qi - 1], qs[qi], qs[qi + 1]
        dec = p + pd.Timedelta(days=LAG)
        dec_next = p_next + pd.Timedelta(days=LAG)
        if dec_next >= dates[-1] - pd.Timedelta(days=5):
            break
        cur = pn.snapshot_as_of(p, dec)
        prev = pn.snapshot_as_of(p1, dec)
        if min(len(cur), len(prev)) < 1000:
            continue
        i_p1 = dates.searchsorted(p1, side="right") - 1
        i_p = dates.searchsorted(p, side="right") - 1
        di = dates.searchsorted(dec, side="right") - 1
        ret_q = cum.iloc[i_p] - cum.iloc[i_p1]
        adv_d = adv.iloc[di]
        px = mdta.prices_raw.iloc[di]

        fl = implied_flows(cur, prev, cmap, ret_q)
        distressed = fl.index[fl["flow"] < DISTRESS_FLOW]
        healthy = fl.index[fl["flow"] > fl["flow"].median()]
        if len(distressed) < 15:
            continue

        # ---- predicted supply (thesis) and placebo ----------------------- #
        def supply_from(managers):
            s = cur[cur["filer_id"].isin(managers)].copy()
            s["ticker"] = s["instrument_id"].map(cmap)
            s = s.dropna(subset=["ticker"])
            s["advj"] = s["ticker"].map(adv_d)
            s = s.dropna(subset=["advj"])
            # pecking: liquidity rank WITHIN each book (1 = most liquid)
            s["peck"] = s.groupby("filer_id")["advj"].rank(pct=True)
            fmag = fl["flow"].abs().reindex(s["filer_id"]).values
            aumc = fl["aum_cur"].reindex(s["filer_id"]).values
            s["sup"] = fmag * aumc * (s["value_usd"] /
                                      s.groupby("filer_id")["value_usd"]
                                      .transform("sum")) * s["peck"]
            out = s.groupby("ticker")["sup"].sum()
            return (out / adv_d.reindex(out.index)).replace(
                [np.inf, -np.inf], np.nan).dropna()

        sup_t = supply_from(distressed)
        sup_p = supply_from(healthy)

        # ---- stage 1: realized sales next quarter ------------------------- #
        nxt = pn.snapshot_as_of(p_next, dec_next)
        heal_sample = list(healthy[:300])
        keep = set(distressed) | set(heal_sample)
        m = cur[cur["filer_id"].isin(keep)][
            ["filer_id", "instrument_id", "shares"]].merge(
            nxt[["filer_id", "instrument_id", "shares"]],
            on=["filer_id", "instrument_id"], how="left",
            suffixes=("", "_n"))
        m["sold"] = (m["shares"] - m["shares_n"].fillna(0.0)) \
            .clip(lower=0) / m["shares"]
        m["adv_j"] = m["instrument_id"].map(pd.Series(cmap)).map(adv_d)
        sold_by = m.groupby("filer_id")["sold"].mean()
        sold_dis = sold_by.reindex(distressed).dropna().tolist()
        sold_heal = sold_by.reindex(heal_sample).dropna().tolist()
        peck_corrs = []
        for i, gm in m[m["filer_id"].isin(distressed)].groupby("filer_id"):
            ok = gm["adv_j"].notna() & gm["sold"].notna()
            if ok.sum() >= 10 and gm.loc[ok, "sold"].std() > 0:
                peck_corrs.append(float(sps.spearmanr(
                    gm.loc[ok, "adv_j"].rank(), gm.loc[ok, "sold"])[0]))
        stage1.append({
            "period": p,
            "n_distressed": len(distressed),
            "sold_frac_distressed": float(np.mean(sold_dis)) if sold_dis else np.nan,
            "sold_frac_healthy": float(np.mean(sold_heal)) if sold_heal else np.nan,
            "pecking_corr": float(np.mean(peck_corrs)) if peck_corrs else np.nan})

        # ---- stage 2: pressure window and reversal window ----------------- #
        i2 = dates.searchsorted(dec_next, side="right") - 1
        rev_end = min(dec_next + pd.Timedelta(days=91), dates[-1])
        fwd_press = forward_return(cum, dates, dec, dates[i2])
        fwd_rev = forward_return(cum, dates, dec_next, rev_end)
        uni = px.index[(px >= 1.0)]
        u_press = float(fwd_press.reindex(uni).dropna().mean())
        u_rev = float(fwd_rev.reindex(uni).dropna().mean())
        for name, sup in [("thesis", sup_t), ("placebo", sup_p)]:
            top = sup.nlargest(max(int(len(sup) * 0.2), 20)).index
            top = [x for x in top if x in px.index and px[x] >= 1.0]
            if len(top) < 15:
                continue
            stage2.append({
                "period": p, "kind": name, "n": len(top),
                "press_excess": float(fwd_press.reindex(top).dropna().mean()
                                      - u_press),
                "rev_excess": float(fwd_rev.reindex(top).dropna().mean()
                                    - u_rev)})
        log(f"{p.date()}: distressed {len(distressed)}, "
            f"peck_corr {stage1[-1]['pecking_corr']}")

    s1 = pd.DataFrame(stage1)
    s2 = pd.DataFrame(stage2)
    s1.to_csv(RESULTS / "stage1_flows.csv", index=False)
    s2.to_csv(RESULTS / "stage2_returns.csv", index=False)

    L = ["# M5 Fire-Sale Forward Calendar - resultados", "",
         "## Estagio 1 - validacao contra vendas REALIZADAS (sem retornos)"]
    if len(s1):
        d = s1["sold_frac_distressed"] - s1["sold_frac_healthy"]
        L += [f"- fracao vendida/tri: distressed {s1.sold_frac_distressed.mean():.3f} "
              f"vs healthy {s1.sold_frac_healthy.mean():.3f} "
              f"(delta t={nw_tstat(d):+.2f})",
              f"- pecking (corr liquidez x fracao vendida nos distressed): "
              f"{s1.pecking_corr.mean():+.3f} "
              f"(t={nw_tstat(s1.pecking_corr):+.2f}; >0 = vendem o liquido primeiro)",
              f"- media de distressed/tri: {s1.n_distressed.mean():.0f}", ""]
    L += ["## Estagio 2 - preco (pressao no tri seguinte, reversao no outro)"]
    for kind, g in s2.groupby("kind"):
        tag = "TESE" if kind == "thesis" else "placebo (healthy)"
        L += [f"### {tag}",
              f"- pressao: {g.press_excess.mean():+.4f}/tri "
              f"t={nw_tstat(g.press_excess):+.2f} (esperado NEGATIVO na tese)",
              f"- reversao: {g.rev_excess.mean():+.4f}/tri "
              f"t={nw_tstat(g.rev_excess):+.2f} (esperado POSITIVO na tese)", ""]
    (RESULTS / "FIRE_REPORT.md").write_text("\n".join(L), encoding="utf-8")
    log("done -> results/")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    main(**vars(ap.parse_args()))
