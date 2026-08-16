"""Shadow Short Interest - implementation of README.md, premises P1-P5.

    python run_ssi.py [--smoke]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sps
from scipy.stats import norm

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "general_plan"))
sys.path.insert(0, str(HERE.parent / "general_predictive_signals"))

import panel as pn                                  # noqa: E402
import market_cap as mc                             # noqa: E402
from backtest_gp import forward_return, nw_tstat    # noqa: E402
from run_all import load_market, log                # noqa: E402
from run_signals import residualise                 # noqa: E402

RESULTS = HERE / "results"
LAG = 45


def ssi_cross_section(cur: pd.DataFrame, cmap: pd.Series, w_mkt: pd.Series,
                      min_holders: int = 10) -> pd.DataFrame:
    """Per-ticker SSI via censored-normal moment inversion (README block)."""
    g = cur.groupby("filer_id")["value_usd"]
    st = pd.DataFrame({"aum": g.sum(), "n": g.size()})
    elig = st[(st["n"].between(15, 500)) & (st["aum"] >= 250e6)].index
    N = float(len(elig))
    s = cur[cur["filer_id"].isin(elig)].copy()
    s["ticker"] = s["instrument_id"].map(cmap)
    s = s.dropna(subset=["ticker"])
    s["w"] = s["value_usd"] / s["filer_id"].map(st["aum"])
    # tilt of HOLDERS = w - w_mkt; aggregate across classes at ticker level
    hold = s.groupby(["ticker", "filer_id"])["w"].sum().reset_index()
    hold["tilt"] = hold["w"] - hold["ticker"].map(w_mkt).fillna(0.0)

    rows = []
    for tk, gtk in hold.groupby("ticker"):
        n_pos = gtk["filer_id"].nunique()
        if n_pos < min_holders:
            continue
        c = -float(w_mkt.get(tk, 0.0))
        p0 = 1.0 - n_pos / N
        if not (0.02 < p0 <= 0.995):
            continue
        t = gtk["tilt"].clip(gtk["tilt"].quantile(0.01),
                             gtk["tilt"].quantile(0.99))
        m1 = float(t.mean())
        alpha = norm.ppf(p0)
        lam = norm.pdf(alpha) / max(1.0 - norm.cdf(alpha), 1e-12)
        denom = max(lam - alpha, 1e-6)
        sigma = max((m1 - c) / denom, 1e-8)
        # SSI = E[(c - tau)+] = sigma * (alpha*Phi(alpha) + phi(alpha))
        ssi = sigma * (alpha * norm.cdf(alpha) + norm.pdf(alpha))
        rows.append({"ticker": tk, "ssi": ssi, "sigma": sigma,
                     "mu": c - alpha * sigma, "p0": p0, "n_pos": n_pos})
    return pd.DataFrame(rows).set_index("ticker")


def new_conviction_signal(cur, prev, cmap) -> pd.Series:
    """Same construction as general_predictive_signals (top-decile of own
    book among new/grown positions), replicated here for the conditioning
    test - counts per ticker, residualised by the caller."""
    n_filers = float(cur["filer_id"].nunique())
    cur2 = cur.assign(w=cur["value_usd"] /
                      cur.groupby("filer_id")["value_usd"].transform("sum"))
    thr = cur2.groupby("filer_id")["w"].transform(lambda x: x.quantile(0.9))
    m = cur2.merge(prev[["filer_id", "instrument_id", "shares"]],
                   on=["filer_id", "instrument_id"], how="left",
                   suffixes=("", "_p"))
    m["thr"] = thr.values
    grew = m[(m["shares_p"].isna()) | (m["shares"] >= 1.25 * m["shares_p"])]
    top = grew[grew["w"] >= grew["thr"]]
    nc = (top.groupby("instrument_id")["filer_id"].nunique() / n_filers)
    t = nc.index.to_series().map(cmap)
    return nc.groupby(t).sum().dropna()


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
        qs = qs[-10:]

    ev_solo, ev_cond, improve, fb = [], [], [], []
    last_ssi = None
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
        px, adv_d = mdta.prices_raw.iloc[di], adv.iloc[di]
        mc_d = mcap.iloc[di] if len(mcap) else pd.Series(dtype=float)
        w_mkt = (mc_d / mc_d.sum()).dropna()
        fb.append(float(1 - w_mkt.reindex(
            cur["instrument_id"].map(cmap).dropna().unique()).notna().mean()))

        X = ssi_cross_section(cur, cmap, w_mkt)
        if len(X) < 300:
            continue
        u = X.index[px.reindex(X.index) >= 1.0]
        X = X.loc[X.index.isin(u)]
        ctrl = pd.DataFrame({"log_mktcap": np.log(mc_d.reindex(X.index)),
                             "log_adv": np.log(adv_d.reindex(X.index))})
        ssi_raw = np.log1p(X["ssi"].clip(lower=0)).rank(pct=True)
        ssi_res = residualise(ssi_raw, ctrl).rank(pct=True)   # P4 headline
        last_ssi = X["ssi"]

        nxt = qs[qi + 1] + pd.Timedelta(days=LAG) if qi + 1 < len(qs) \
            else dates[-1]
        fwd = forward_return(cum, dates, dec, min(nxt, dates[-1]))

        # ---- test 2: standalone quintiles (pre-registered NEGATIVE) ------ #
        for ver, r in [("raw", ssi_raw), ("resid", ssi_res)]:
            df = pd.concat([r.rename("s"), fwd.reindex(r.index).rename("f")],
                           axis=1).dropna()
            if len(df) < 200:
                continue
            q = pd.qcut(df["s"].rank(method="first"), 5, labels=False) + 1
            ew = df.groupby(q)["f"].mean()
            ev_solo.append({"period": p, "version": ver,
                            "spread_ew": ew.get(5, np.nan) - ew.get(1, np.nan),
                            "ic": sps.spearmanr(df["s"], df["f"])[0]})

        # ---- test 1: conditioning new_conviction by SSI ------------------- #
        nc = new_conviction_signal(cur, prev, cmap)
        nc = nc.reindex(X.index).dropna()
        nc_r = residualise(nc.rank(pct=True), ctrl.reindex(nc.index)) \
            .rank(pct=True)
        both = pd.concat([nc_r.rename("nc"), ssi_res.rename("ssi"),
                          fwd.rename("f")], axis=1).dropna()
        if len(both) >= 300:
            both["st"] = pd.qcut(both["ssi"].rank(method="first"), 3,
                                 labels=False)
            for t3 in (0, 1, 2):
                sub = both[both["st"] == t3]
                q = pd.qcut(sub["nc"].rank(method="first"), 5, labels=False)
                if q.nunique() == 5:
                    ev_cond.append({
                        "period": p, "ssi_tercile": t3 + 1,
                        "nc_spread": sub["f"][q == 4].mean()
                        - sub["f"][q == 0].mean()})
            # improvement test: NC long leg with vs without high-SSI names
            top_nc = both[both["nc"] >= both["nc"].quantile(0.8)]
            filt = top_nc[top_nc["ssi"] <= both["ssi"].quantile(2 / 3)]
            improve.append({"period": p,
                            "long_all": float(top_nc["f"].mean()),
                            "long_filtered": float(filt["f"].mean()),
                            "n_all": len(top_nc), "n_filt": len(filt)})
        log(f"{p.date()} done ({len(X)} tickers)")

    # ---- test 3: external validation vs real short interest -------------- #
    val_txt = "skipped"
    if last_ssi is not None and not smoke:
        try:
            import time
            import yfinance as yf
            sample = pd.concat([last_ssi.nlargest(120), last_ssi.nsmallest(120),
                                last_ssi.sample(min(160, len(last_ssi)),
                                                random_state=7)]).index.unique()
            si = {}
            for tk in sample:
                try:
                    v = yf.Ticker(tk).info.get("shortPercentOfFloat")
                    if v is not None:
                        si[tk] = float(v)
                except Exception:
                    pass
                time.sleep(0.25)
            si = pd.Series(si)
            common = si.index.intersection(last_ssi.index)
            if len(common) > 60:
                rho = sps.spearmanr(last_ssi[common], si[common])[0]
                val_txt = (f"corr(SSI, short interest REAL) = {rho:+.2f} "
                           f"em {len(common)} nomes (snapshot corrente)")
        except Exception as e:  # noqa: BLE001
            val_txt = f"falhou: {type(e).__name__}"

    # ---- report ----------------------------------------------------------- #
    solo = pd.DataFrame(ev_solo)
    cond = pd.DataFrame(ev_cond)
    imp = pd.DataFrame(improve)
    solo.to_csv(RESULTS / "ssi_solo.csv", index=False)
    cond.to_csv(RESULTS / "ssi_conditioning.csv", index=False)
    imp.to_csv(RESULTS / "ssi_improvement.csv", index=False)

    L = ["# SSI - resultados", ""]
    for ver, g in solo.groupby("version"):
        L.append(f"## standalone {ver}"
                 + (" (HEADLINE)" if ver == "resid" else "")
                 + f": spread {g.spread_ew.mean():+.4f}/tri "
                 f"t={nw_tstat(g.spread_ew):+.2f} | IC {g.ic.mean():+.3f} "
                 f"| n={len(g)} | direcao pre-registrada: NEGATIVA")
    if len(cond):
        L += ["", "## new_conviction condicionado por SSI (spread por tercil)"]
        for t3, g in cond.groupby("ssi_tercile"):
            L.append(f"- SSI tercil {t3}: NC spread "
                     f"{g.nc_spread.mean():+.4f}/tri "
                     f"t={nw_tstat(g.nc_spread):+.2f} (n={len(g)})")
        L.append("Predicao: paga mais no tercil 1 (sem ursos represados).")
    if len(imp):
        d = imp["long_filtered"] - imp["long_all"]
        L += ["", "## melhoria da perna long do new_conviction",
              f"- long original: {imp.long_all.mean():+.4f}/tri | "
              f"filtrada (sem SSI alto): {imp.long_filtered.mean():+.4f}/tri",
              f"- delta: {d.mean():+.4f}/tri, t={nw_tstat(d):+.2f}"]
    L += ["", f"## validacao externa: {val_txt}",
          f"## fracao media sem mktcap (fallback): "
          f"{np.mean(fb):.0%}" if fb else ""]
    (RESULTS / "SSI_REPORT.md").write_text("\n".join(L), encoding="utf-8")
    log("done -> results/")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    main(**vars(ap.parse_args()))
