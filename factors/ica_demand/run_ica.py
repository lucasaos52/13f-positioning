"""M4 - blind separation of institutional demand sources (see README.md
for every premise; nothing here is a free choice).

    python run_ica.py [--smoke]
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

import panel as pn                                  # noqa: E402
import market_cap as mc                             # noqa: E402
from backtest_gp import forward_return, nw_tstat    # noqa: E402
from run_all import load_market, log                # noqa: E402

RESULTS = HERE / "results"
LAG = 45
K = 6                     # P4: fixed a priori
MIN_HISTORY = 20          # P3: first expanding window
N_FORCED, N_INFORMED = 2, 2   # P5: fixed ranks
STRESS = ["2015-09-30", "2018-12-31", "2020-03-31", "2022-06-30"]


def modal_split_factor(cur: pd.DataFrame, prev: pd.DataFrame) -> pd.Series:
    """Split factor per instrument via the holders' modal atom (validated
    on NVDA 10:1 etc. - price-implied detection is impossible on Yahoo)."""
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


def build_flow_panel(qs, cmap) -> pd.DataFrame:
    """P1/P2/P3: per-quarter institutional share-growth per ticker, each row
    computed at ITS OWN decision date (p+45d) and never revised."""
    cache = HERE / "results" / "flow_panel.parquet"
    if cache.exists():
        return pd.read_parquet(cache)
    rows = {}
    for qi in range(1, len(qs)):
        p, p1 = qs[qi], qs[qi - 1]
        dec = p + pd.Timedelta(days=LAG)
        cur = pn.snapshot_as_of(p, dec)
        prev = pn.snapshot_as_of(p1, dec)
        if min(len(cur), len(prev)) < 1000:
            continue
        fac = modal_split_factor(cur, prev)
        sh_c = cur.groupby("instrument_id")["shares"].sum()
        sh_p = prev.groupby("instrument_id")["shares"].sum()
        sh_p = sh_p * sh_p.index.to_series().map(fac).fillna(1.0)
        n_c = cur.groupby("instrument_id")["filer_id"].nunique()
        ok = n_c[n_c >= 10].index                       # P8 holder floor
        f = ((sh_c - sh_p) / sh_p).reindex(ok).replace(
            [np.inf, -np.inf], np.nan).dropna()
        f = f.clip(f.quantile(0.01), f.quantile(0.99))  # P1 winsor
        t = f.index.to_series().map(cmap)
        f = f.groupby(t).sum().dropna()
        rows[p] = f - f.mean()                          # P2 de-mean
        log(f"panel {p.date()}: {len(f)} tickers")
    X = pd.DataFrame(rows)                              # tickers x quarters
    X.to_parquet(cache)
    return X


def classify(S_t: np.ndarray) -> tuple[list, list]:
    """P5: within the K sources, top-2 kurtosis = forced; among the rest,
    top-2 |AR(1)| = informed. Uses only the fitting window."""
    kurt = [sps.kurtosis(s) for s in S_t]
    order = np.argsort(kurt)[::-1]
    forced = list(order[:N_FORCED])
    rest = [k for k in range(len(S_t)) if k not in forced]
    ar1 = {k: abs(pd.Series(S_t[k]).autocorr()) for k in rest}
    informed = sorted(rest, key=lambda k: -ar1[k])[:N_INFORMED]
    return forced, informed


def decompose(Xw: pd.DataFrame, method: str, seed: int = 0):
    """Fit ICA (or the PCA rotation-placebo) on the window: tickers are
    samples, quarters are features. Returns sources S (K x T) and per-ticker
    exposures B (tickers x K)."""
    from sklearn.decomposition import PCA, FastICA
    V = Xw.fillna(0.0).values                           # P8: gaps -> 0
    if method == "ica":
        m = FastICA(n_components=K, random_state=seed, max_iter=1000,
                    whiten="unit-variance")
        B = m.fit_transform(V)                          # tickers x K
        S = m.components_                               # K x T (mixing over time)
    else:
        m = PCA(n_components=K, random_state=seed)
        B = m.fit_transform(V)
        S = m.components_
    return S, B


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
    X = build_flow_panel(qs, cmap)
    cols = list(X.columns)
    start = MIN_HISTORY if not smoke else len(cols) - 8

    events, stability, narr = [], [], []
    prev_forced_sig = None
    for ti in range(start, len(cols) - 1):
        t = cols[ti]
        dec = t + pd.Timedelta(days=LAG)
        di = dates.searchsorted(dec, side="right") - 1
        if di >= len(dates) - 60:
            break
        win = X[cols[:ti + 1]]
        # P8: tickers with >=80% coverage in the window and alive at decision
        cover = win.notna().mean(axis=1)
        px = mdta.prices_raw.iloc[di]
        alive = win.index[(cover >= 0.8)
                          & (px.reindex(win.index) >= 1.0)
                          & win[t].notna()]
        win = win.loc[alive]
        if len(win) < 300:
            continue
        mc_d = mcap.iloc[di] if len(mcap) else pd.Series(dtype=float)

        nxt = cols[ti + 1] + pd.Timedelta(days=LAG)
        fwd = forward_return(cum, dates, dec, min(nxt, dates[-1]))

        for method in ("ica", "pca"):
            S, B = decompose(win, method)
            forced, informed = classify(S)
            s_now = S[:, -1]                            # current activity
            rev = -pd.Series(B[:, forced] @ s_now[forced], index=win.index)
            cont = pd.Series(B[:, informed] @ s_now[informed], index=win.index)
            comb = (rev.rank(pct=True) + cont.rank(pct=True)) / 2
            for name, sig in [("rev", rev), ("cont", cont), ("comb", comb)]:
                df = pd.concat([sig.rank(pct=True).rename("s"),
                                fwd.reindex(sig.index).rename("f")],
                               axis=1).dropna()
                if len(df) < 200:
                    continue
                rng = np.random.default_rng(int(t.value) % (2**32))
                jit = pd.Series(rng.uniform(0, 1e-9, len(df)), index=df.index)
                q = pd.qcut((df["s"] + jit).rank(), 5, labels=False) + 1
                ew = df.groupby(q)["f"].mean()
                w = mc_d.reindex(df.index).fillna(0.0)
                vw = df.assign(w=w).groupby(q).apply(
                    lambda g: np.average(g["f"], weights=g["w"])
                    if g["w"].sum() > 0 else np.nan)
                events.append({
                    "period": t, "method": method, "signal": name,
                    "spread_ew": ew.get(5, np.nan) - ew.get(1, np.nan),
                    "spread_vw": vw.get(5, np.nan) - vw.get(1, np.nan),
                    "ic": sps.spearmanr(df["s"], df["f"])[0], "n": len(df)})
            if method == "ica":
                # falsification 2: forced-source spikes vs known stress
                act = np.abs(S[forced]).sum(axis=0)
                top = [str(cols[i].date()) for i in np.argsort(act)[::-1][:5]]
                narr.append({"period": t, "top_forced_quarters": ",".join(top)})
                # falsification 3: classification stability
                sig_f = frozenset(forced)
                if prev_forced_sig is not None:
                    stability.append(len(sig_f & prev_forced_sig) / N_FORCED)
                prev_forced_sig = sig_f
        log(f"{t.date()} done")

    ev = pd.DataFrame(events)
    ev.to_csv(RESULTS / "ica_events.csv", index=False)
    pd.DataFrame(narr).to_csv(RESULTS / "forced_spikes.csv", index=False)

    L = [f"# M4 ICA demand sources - K={K}, janela inicial {MIN_HISTORY} tri", ""]
    for (method, name), g in ev.groupby(["method", "signal"]):
        L += [f"## {method.upper()} / {name}"
              + ("  <- TESE" if method == "ica" else "  <- placebo de rotacao"),
              f"- spread EW {g.spread_ew.mean():+.4f}/tri t={nw_tstat(g.spread_ew):+.2f}"
              f" | VW {g.spread_vw.mean():+.4f} t={nw_tstat(g.spread_vw):+.2f}"
              f" | IC {g.ic.mean():+.3f} | n={len(g)}", ""]
    if stability:
        L += [f"## Estabilidade da classificacao forcada t->t+1: "
              f"{np.mean(stability):.0%}"]
    if narr:
        L += ["## Trimestres de pico das fontes forcadas (ultimo fit): "
              + narr[-1]["top_forced_quarters"],
              f"(stress conhecido: {', '.join(STRESS)})"]
    (RESULTS / "ICA_REPORT.md").write_text("\n".join(L), encoding="utf-8")
    log("done -> results/")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    main(**vars(ap.parse_args()))
