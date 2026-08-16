"""Common Fund-Flow Beta (doc idea #6, Dou-Kogan-Wu): stocks inherit the
funding-shock sensitivity of their holders - but state has no arrow, so
the tradable object is the INTERACTION with the current common shock.

    python run_fb.py            # full sample
    python run_fb.py --smoke    # shorter tail (still respects warm-up)

CAUSAL CHAIN:
    fund flows have a common component g_t (aggregate funding conditions)
      -> manager m's sensitivity beta_m = how hard HIS flows move with g
      -> stocks held by high-beta managers inherit joint-liquidation risk
      -> when g_t is NEGATIVE (common outflow), those stocks face
         correlated forced selling next quarter -> continuation pressure;
         when g_t is positive, correlated buying. Direction comes from
         g_t, never from the state alone.

CHOICES (each defensible):
  - g_t = AUM-weighted mean of current implied flows - observable,
    interpretable ("the average dollar's funding shock"), computed from
    snapshots at the decision date (public). PCA/ICA not needed here: the
    COMMON component is exactly the second-moment object PCA-style
    averaging captures; ICA was required for the idiosyncratic spiky
    components, a different object.
  - beta_m estimated STRICTLY on past quarters (>= 8 observations of
    manager m against the g series), expanding window.
  - stock exposure = sum_m value_mi * beta_m / ADV_i (dollar-fragility
    flavour, consistent with the pressure family).

PRE-REGISTERED:
  F1 state alone (FlowBeta_i, no shock) ~ 0        [the project's law]
  F2 signed version FlowBeta_i x g_t: POSITIVE spread (continuation in
     the direction of the common funding shock)
  F3 placebo: permute beta_m across managers -> F2 must die
  Paired delta F2 vs F1 on the same sample is the verdict statistic.
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

import market_cap as mc                             # noqa: E402
import panel as pn                                  # noqa: E402
from backtest_gp import forward_return, nw_tstat    # noqa: E402
from run_all import load_market, log                # noqa: E402
from run_fire import implied_flows                  # noqa: E402

RESULTS = HERE / "results"
LAG = 45
MIN_BETA_OBS = 8
MIN_WARM = 12


def main(smoke: bool = False) -> None:
    RESULTS.mkdir(exist_ok=True)
    cmap, mdta = load_market()
    dates = mdta.prices.index
    cum = mdta.returns.cumsum()
    adv = mdta.dollar_volume.rolling(63, min_periods=20).median()
    shares = mc.shares_panel(dates, mdta.tickers, mdta.prices, mdta.prices_raw)
    mcap = mc.mktcap_panel(mdta.prices_raw, shares)

    qs = [q for q in pn.quarters()
          if pd.Timestamp("2013-06-30") <= q <= dates[-1] - pd.Timedelta(days=120)]
    if smoke:
        qs = qs[-(10 + MIN_WARM):]
    log(f"{len(qs)} quarters")

    flow_hist: list[pd.Series] = []      # per past quarter: flow per manager
    g_hist: list[float] = []             # per past quarter: common shock
    events: list[dict] = []

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
        px, adv_d = mdta.prices_raw.iloc[di], adv.iloc[di_p]
        mc_d = mcap.iloc[di]
        ret_q = cum.iloc[di_p] - cum.iloc[di_p1]

        fl = implied_flows(cur, prev, cmap, ret_q)
        if len(fl) < 200:
            continue
        g_t = float(np.average(fl["flow"], weights=fl["aum_prev"]))

        # ---- beta_m from STRICTLY PAST quarters --------------------------- #
        beta = pd.Series(dtype=float)
        if len(flow_hist) >= MIN_WARM:
            F = pd.concat(flow_hist, axis=1)
            gv = pd.Series(g_hist, index=F.columns)
            gd = gv - gv.mean()
            Fd = F.sub(F.mean(axis=1), axis=0)
            num = (Fd * gd).sum(axis=1, min_count=MIN_BETA_OBS)
            den = ((Fd.notna() * gd**2).sum(axis=1))
            beta = (num / den.replace(0, np.nan)).dropna()

        # append AFTER use: beta never sees the current quarter
        flow_hist.append(fl["flow"].rename(str(p.date())))
        g_hist.append(g_t)
        if len(beta) < 200:
            continue

        # ---- stock-level exposure ---------------------------------------- #
        d = cur[["filer_id", "instrument_id", "value_usd"]].copy()
        d["ticker"] = d["instrument_id"].map(cmap)
        d = d.dropna(subset=["ticker"])
        d = d[d["filer_id"].isin(beta.index)]
        d["b"] = d["filer_id"].map(beta)
        rng = np.random.default_rng(int(p.value) % (2**32))
        perm = pd.Series(rng.permutation(beta.values), index=beta.index)
        d["b_pl"] = d["filer_id"].map(perm)
        g = d.groupby("ticker")
        fb_dollar = g.apply(lambda x: (x["value_usd"] * x["b"]).sum())
        fb_pl = g.apply(lambda x: (x["value_usd"] * x["b_pl"]).sum())
        n_hold = g["filer_id"].nunique()

        idx = fb_dollar.index
        adv_i = pd.Series(idx.map(adv_d), index=idx)
        state = (fb_dollar / adv_i).replace([np.inf, -np.inf], np.nan)
        signed = state * g_t
        signed_pl = (fb_pl / adv_i).replace(
            [np.inf, -np.inf], np.nan) * g_t

        uni = idx[(pd.Series(idx.map(px), index=idx) >= 1.0)
                  & (n_hold >= 5) & adv_i.gt(0)]
        nxt = qs[qi + 1] + pd.Timedelta(days=LAG) if qi + 1 < len(qs) \
            else dates[-1]
        fwd = forward_return(cum, dates, dec, min(nxt, dates[-1])).reindex(uni)

        row = {"period": p, "g_t": g_t, "n_beta": len(beta),
               "n_uni": len(uni)}
        for nm, s in [("state", state), ("signed", signed),
                      ("placebo", signed_pl)]:
            df = pd.concat([s.reindex(uni).rename("s"), fwd.rename("f")],
                           axis=1).dropna()
            if len(df) < 300:
                row[f"spread_{nm}"] = np.nan
                row[f"ic_{nm}"] = np.nan
                continue
            ss = df["s"].clip(df["s"].quantile(0.01), df["s"].quantile(0.99))
            jit = pd.Series(rng.uniform(0, 1e-9, len(df)), index=df.index)
            q5 = pd.qcut((ss + jit).rank(), 5, labels=False)
            gq = df.groupby(q5)["f"].mean()
            row[f"spread_{nm}"] = float(gq.get(4, np.nan)
                                        - gq.get(0, np.nan))
            row[f"ic_{nm}"] = float(sps.spearmanr(df["s"], df["f"])[0])
        events.append(row)
        log(f"{p.date()}: g_t {g_t:+.3f}, betas {len(beta)}, "
            f"signed spread {row.get('spread_signed')}")

    ev = pd.DataFrame(events)
    ev.to_csv(RESULTS / "fb_events.csv", index=False)

    L = ["# flow_beta - beta de funding comum x choque corrente", "",
         "g_t = fluxo implicito medio ponderado por AUM (o choque de "
         "funding do dolar medio); beta_m estimado so no passado (>=8 "
         "obs); exposicao = sum valor x beta / ADV.", ""]
    if len(ev):
        L.append(f"- {len(ev)} tri avaliados | betas medios/tri: "
                 f"{ev['n_beta'].mean():.0f} | g_t: media "
                 f"{ev['g_t'].mean():+.3f}, min {ev['g_t'].min():+.3f}, "
                 f"max {ev['g_t'].max():+.3f}\n")
        for nm, lbl, exp in [
                ("state", "F1 estado puro (FlowBeta sem choque)", "~0"),
                ("signed", "F2 TESE: FlowBeta x g_t", "POSITIVO"),
                ("placebo", "F3 placebo (beta permutado) x g_t", "~0")]:
            sp, ic = ev[f"spread_{nm}"].dropna(), ev[f"ic_{nm}"].dropna()
            L.append(f"- **{lbl}**: spread {sp.mean():+.4f}/tri "
                     f"(t={nw_tstat(sp):+.2f}), IC {ic.mean():+.4f} "
                     f"(t={nw_tstat(ic):+.2f}) - esperado {exp}")
        d = (ev["spread_signed"] - ev["spread_state"]).dropna()
        L.append(f"- **delta pareado F2-F1**: {d.mean():+.4f}/tri "
                 f"(t={nw_tstat(d):+.2f})")
        d2 = (ev["spread_signed"] - ev["spread_placebo"]).dropna()
        L.append(f"- **delta pareado F2-F3**: {d2.mean():+.4f}/tri "
                 f"(t={nw_tstat(d2):+.2f})")
    (RESULTS / "FB_REPORT.md").write_text("\n".join(L), encoding="utf-8")
    log("done -> results/")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    main(**vars(ap.parse_args()))
