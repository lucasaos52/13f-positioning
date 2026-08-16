"""M1 - Strategy-space crowding: NMF on the manager x stock holdings matrix.

    python nmf_crowding.py            # full sample
    python nmf_crowding.py --smoke    # last 10 quarters

Thesis. Fire-sale contagion lives at the STRATEGY level, not the stock level
(the 2007 quant quake propagated through a shared recipe, not shared names).
NMF on the holdings matrix extracts K latent strategies that are genuine
portfolios (non-negative weights - unlike PCA components, which carry
negative weights and are nobody's book). Each strategy gets a
crowding-with-capacity score - how many days of its basket's ADV the capital
parked in it represents - and each stock inherits the crowding of the
strategies it lives in.

Care taken (the things that make this defensible rather than a demo):

  K SELECTION never sees returns: K is chosen once, on the FIRST 8 quarters
  only, by held-out manager reconstruction (fit on 80% of managers, project
  the held-out 20%, measure error), picking the smallest K within 2% of the
  best. Frozen thereafter.

  PIT: each quarter's W is built from `snapshot_as_of(p, p+45d)` - only
  filings public at decision time. The factorisation is re-fit each quarter
  independently (no information travels backward). Strategy IDENTITY across
  quarters is matched by basket overlap (greedy Hungarian-style on S rows),
  used only for reporting, never for signal construction.

  RESIDUALISATION (the theorem test, applied before results): the strategy
  crowding score has basket ADV in the denominator. In a dart-throwing world
  NMF recovers ~market-portfolio strategies and the stock signal collapses
  to inverse basket liquidity - a mechanical illiquidity screen. THEOREM
  holds -> the headline is the residual against log(mktcap) + log(ADV);
  raw is reported alongside.

  SELF-DECEPTION CHECK: cross-sectional correlation with plain stock-level
  days-ADV is computed every quarter. If it averages > 0.8, this is
  days-ADV with extra steps and the report says so.

Manager universe: 15..500 positions, book >= $250M (broader than the
endogenous factor universe - NMF needs breadth to see strategies; the cuts
only remove degenerate books). Stock universe: held by >= 5 eligible
managers, mapped ticker, price >= $1.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sps

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
K_GRID = [6, 8, 10, 12, 15]
K_SELECT_QUARTERS = 8


def build_W(snap: pd.DataFrame, cmap: pd.Series, px: pd.Series):
    """Manager x stock weight matrix on the eligible universes."""
    g = snap.groupby("filer_id")["value_usd"]
    stats = pd.DataFrame({"aum": g.sum(), "n": g.size()})
    mgrs = stats[(stats["n"].between(15, 500)) & (stats["aum"] >= 250e6)].index
    s = snap[snap["filer_id"].isin(mgrs)].copy()
    s["ticker"] = s["instrument_id"].map(cmap)
    s = s.dropna(subset=["ticker"])
    s = s[s["ticker"].map(px) >= 1.0]
    held = s.groupby("ticker")["filer_id"].nunique()
    s = s[s["ticker"].isin(held[held >= 5].index)]
    W = s.pivot_table(index="filer_id", columns="ticker",
                      values="value_usd", aggfunc="sum").fillna(0.0)
    aum = W.sum(axis=1)
    keep = aum > 0            # zero-value books (old filings with missing
    W, aum = W.loc[keep], aum[keep]   # values) would produce 0/0 = NaN rows
    return W.div(aum, axis=0), aum


def heldout_error(W: pd.DataFrame, k: int, seed: int = 7) -> float:
    """Fit NMF on 80% of managers; project the rest; reconstruction error."""
    from sklearn.decomposition import NMF
    rng = np.random.default_rng(seed)
    idx = rng.permutation(len(W))
    cut = int(0.8 * len(W))
    tr, te = W.iloc[idx[:cut]], W.iloc[idx[cut:]]
    m = NMF(n_components=k, init="nndsvda", max_iter=400, random_state=0)
    m.fit(tr.values)
    A_te = m.transform(te.values)
    rec = A_te @ m.components_
    return float(np.linalg.norm(te.values - rec) / np.linalg.norm(te.values))


def fit_nmf(W: pd.DataFrame, k: int):
    from sklearn.decomposition import NMF
    m = NMF(n_components=k, init="nndsvda", max_iter=400, random_state=0)
    A = m.fit_transform(W.values)          # managers x K
    S = m.components_                       # K x stocks
    return A, S


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

    # ---- K selection on the earliest quarters only (never sees returns) --- #
    kq = qs[:min(K_SELECT_QUARTERS, len(qs))]
    errs = {k: [] for k in K_GRID}
    for p in kq:
        dec = p + pd.Timedelta(days=LAG)
        snap = pn.snapshot_as_of(p, dec)
        if len(snap) < 1000:
            continue
        di = dates.searchsorted(dec, side="right") - 1
        W, _ = build_W(snap, cmap, mdta.prices_raw.iloc[di])
        for k in K_GRID:
            errs[k].append(heldout_error(W, k))
    mean_err = {k: np.mean(v) for k, v in errs.items() if v}
    best = min(mean_err.values())
    K = min(k for k, e in mean_err.items() if e <= best * 1.02)
    log(f"K selection (held-out, first {len(kq)} quarters): "
        f"{ {k: round(e, 4) for k, e in mean_err.items()} } -> K={K}")

    # ---- quarterly loop ---------------------------------------------------- #
    events, corr_da, narr = [], [], []
    for qi in range(len(qs)):
        p = qs[qi]
        dec = p + pd.Timedelta(days=LAG)
        if dec >= dates[-1] - pd.Timedelta(days=95):
            continue
        snap = pn.snapshot_as_of(p, dec)
        if len(snap) < 1000:
            continue
        di = dates.searchsorted(dec, side="right") - 1
        px, adv_d = mdta.prices_raw.iloc[di], adv.iloc[di]
        mc_d = mcap.iloc[di] if len(mcap) else pd.Series(dtype=float)

        W, aum = build_W(snap, cmap, px)
        if len(W) < 100:
            continue
        A, S = fit_nmf(W, K)
        tickers = W.columns

        # strategy crowding: capital parked in k / one day of basket ADV
        cap_k = (A * aum.values[:, None]).sum(axis=0)          # $ per strategy
        S_norm = S / S.sum(axis=1, keepdims=True)              # basket weights
        basket_adv = S_norm @ adv_d.reindex(tickers).fillna(0.0).values
        crowd_k = cap_k / np.maximum(basket_adv, 1.0)          # days to unwind
        # stock exposure to crowded strategies (weights within the stock)
        expo = S / np.maximum(S.sum(axis=0, keepdims=True), 1e-12)  # K x stocks
        sig_raw = pd.Series(expo.T @ crowd_k, index=tickers)

        # anti-self-deception: is this just days-ADV?
        da_stock = (snap.groupby("instrument_id")["value_usd"].sum()
                    .pipe(lambda s: s.groupby(s.index.to_series().map(cmap)).sum())
                    / adv_d).reindex(tickers)
        rho = sps.spearmanr(sig_raw.rank(), da_stock.rank(),
                            nan_policy="omit")[0]
        corr_da.append({"period": p, "corr_days_adv": float(rho)})

        # theorem residualisation (headline) + raw
        ctrl = pd.DataFrame({"log_mktcap": np.log(mc_d.reindex(tickers)),
                             "log_adv": np.log(adv_d.reindex(tickers))})
        r_raw = np.log1p(sig_raw.clip(lower=0)).rank(pct=True)
        r_res = residualise(r_raw, ctrl).rank(pct=True)

        nxt = qs[qi + 1] + pd.Timedelta(days=LAG) if qi + 1 < len(qs) \
            else dates[-1]
        fwd = forward_return(cum, dates, dec, min(nxt, dates[-1])).reindex(tickers)
        for ver, r in [("raw", r_raw), ("resid", r_res)]:
            df = pd.concat([r.rename("s"), fwd.rename("f")], axis=1).dropna()
            if len(df) < 150:
                continue
            q5 = pd.qcut(df["s"].rank(method="first"), 5, labels=False) + 1
            ew = df.groupby(q5)["f"].mean()
            w = mc_d.reindex(df.index).fillna(0.0)
            vw = df.assign(w=w).groupby(q5).apply(
                lambda g: np.average(g["f"], weights=g["w"])
                if g["w"].sum() > 0 else np.nan)
            events.append({
                "period": p, "version": ver,
                "spread_ew": ew.get(5, np.nan) - ew.get(1, np.nan),
                "spread_vw": vw.get(5, np.nan) - vw.get(1, np.nan),
                "ic": sps.spearmanr(df["s"], df["f"])[0], "n": len(df)})

        # narrative: the most crowded strategy this quarter
        kk = int(np.argmax(crowd_k))
        top = pd.Series(S_norm[kk], index=tickers).nlargest(5)
        narr.append({"period": p, "crowd_days": float(crowd_k[kk]),
                     "top_names": ",".join(top.index)})
        log(f"{p.date()} K={K} crowd_max={crowd_k[kk]:,.0f}d "
            f"corr(daysADV)={rho:+.2f}")

    ev = pd.DataFrame(events)
    ev.to_csv(RESULTS / "nmf_events.csv", index=False)
    pd.DataFrame(corr_da).to_csv(RESULTS / "nmf_corr_daysadv.csv", index=False)
    pd.DataFrame(narr).to_csv(RESULTS / "nmf_top_strategy.csv", index=False)

    L = [f"# M1 NMF strategy crowding - K={K} (held-out nas {len(kq)} "
         "primeiras janelas)", ""]
    for ver, g in ev.groupby("version"):
        head = " (HEADLINE - teorema)" if ver == "resid" else ""
        L += [f"## {ver}{head}",
              f"- spread EW: {g.spread_ew.mean():+.4f}/tri, "
              f"t(NW)={nw_tstat(g.spread_ew):.2f}",
              f"- spread VW: {g.spread_vw.mean():+.4f}/tri, "
              f"t(NW)={nw_tstat(g.spread_vw):.2f}",
              f"- IC medio: {g.ic.mean():+.4f} | eventos: {len(g)}", ""]
    cd = pd.DataFrame(corr_da)["corr_days_adv"]
    verdict = ("**days-ADV com passos extras - reportar como tal**"
               if cd.mean() > 0.8 else "informacao propria alem do days-ADV")
    L += [f"## Anti-autoengano: corr media com days-ADV puro = "
          f"{cd.mean():+.2f} -> {verdict}"]
    (RESULTS / "NMF_REPORT.md").write_text("\n".join(L), encoding="utf-8")
    log("done -> results/")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    main(**vars(ap.parse_args()))
