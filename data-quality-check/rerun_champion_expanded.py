"""Headline re-run on the EXPANDED universe + the halving stability test.

    python rerun_champion_expanded.py

(1) new_conviction (residualized, champion core) re-evaluated on the
    post-fix universe (map 3,928->4,154 entries incl. LLY/GOOG/JPM/BRK/
    UNH/XOM...). Reference values on the old universe, same protocol:
    t=+3.67 (np run) / +3.83 (inter run) / +3.27 (17-signal run).
(2) HALVING STABILITY: the same signal evaluated on two random halves of
    the expanded universe (seeded). If the champion holds under a random
    50% coverage cut, quasi-random coverage (which is what the name-match
    hole was) cannot flip verdicts - the generic answer to "does the
    coverage hole change everything?".
Missing-mktcap fallback (new tickers lack the shares panel): mktcap :=
aggregate 13F value held (the documented run_all fallback), used only
where the shares-based mktcap is NaN.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sps

ROOT = Path(__file__).resolve().parents[1]
for sub in ("factors", "factors/general_plan"):
    sys.path.insert(0, str(ROOT / sub))

import market_cap as mc                             # noqa: E402
import panel as pn                                  # noqa: E402
from backtest_gp import forward_return, nw_tstat    # noqa: E402
from run_all import load_market, log                # noqa: E402

OUT = ROOT / "data-quality-check" / "results"
LAG = 45


def residualise(y, X):
    df = pd.concat([y.rename("y"), X], axis=1).replace(
        [np.inf, -np.inf], np.nan)
    ok = df.notna().all(axis=1)
    if ok.sum() < 30:
        return y - y.mean()
    A = np.column_stack([np.ones(ok.sum()), df.loc[ok, X.columns].values])
    try:
        b, *_ = np.linalg.lstsq(A, df.loc[ok, "y"].values, rcond=None)
    except np.linalg.LinAlgError:
        return y - y.mean()
    r = y.copy()
    r[ok] = df.loc[ok, "y"].values - A @ b
    r[~ok] = np.nan
    return r


def split_factor(cur, prev):
    pair = cur.merge(prev, on=["filer_id", "instrument_id"],
                     suffixes=("_c", "_p"))
    pair = pair[(pair["shares_p"] > 0) & (pair["shares_c"] > 0)]
    pair["ratio"] = (pair["shares_c"] / pair["shares_p"]).round(3)
    fac = {}
    for j, g in pair.groupby("instrument_id"):
        if len(g) < 10:
            continue
        counts = g["ratio"].value_counts()
        mode, k = counts.index[0], counts.iloc[0]
        k2 = counts.iloc[1] if len(counts) > 1 else 0
        if abs(mode - 1) > 0.15 and (k >= 0.10 * len(g)
                                     or (k >= 30 and k >= 2.5 * k2)):
            fac[j] = float(mode)
    return pd.Series(fac, dtype=float)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    cmap, mdta = load_market()
    dates = mdta.prices.index
    cum = mdta.returns.cumsum()
    adv = mdta.dollar_volume.rolling(63, min_periods=20).median()
    shares = mc.shares_panel(dates, mdta.tickers, mdta.prices, mdta.prices_raw)
    mcap = mc.mktcap_panel(mdta.prices_raw, shares)
    log(f"universe: {len(mdta.prices.columns)} tickers, map {len(cmap)}")

    qs = [q for q in pn.quarters()
          if pd.Timestamp("2013-06-30") <= q <= dates[-1] - pd.Timedelta(days=120)]
    rows = []
    rng_split = np.random.default_rng(20260816)
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
        fac_i = split_factor(cur, prev)
        prev_sh = prev.groupby(["filer_id", "instrument_id"])["shares"].sum()

        b = cur.copy()
        tot = b.groupby("filer_id")["value_usd"].transform("sum")
        b["w"] = b["value_usd"] / tot.replace(0, np.nan)
        b["thr"] = b.groupby("filer_id")["w"].transform(
            lambda s: s.quantile(0.9))
        key = pd.MultiIndex.from_frame(b[["filer_id", "instrument_id"]])
        shp = pd.Series(prev_sh.reindex(key).values, index=b.index)
        fac = b["instrument_id"].map(fac_i).fillna(1.0)
        grew = shp.isna() | (b["shares"] >= 1.25 * shp * fac)
        v = b[(b["w"] >= b["thr"]) & grew].copy()
        v["ticker"] = v["instrument_id"].map(cmap)
        v = v.dropna(subset=["ticker"])
        n_filers = float(cur["filer_id"].nunique())
        nc = v.groupby("ticker")["filer_id"].nunique() / n_filers
        # aggregate 13F dollar value per ticker (mktcap fallback)
        b["ticker"] = b["instrument_id"].map(cmap)
        agg13f = b.dropna(subset=["ticker"]).groupby("ticker")["value_usd"] \
            .sum()

        # FULL universe (>=5 holders), zeros for names without votes -
        # the original protocol; evaluating voted names only was a bug
        n_c = b.dropna(subset=["ticker"]).groupby("ticker")["filer_id"] \
            .nunique()
        idx_all = n_c.index[n_c >= 5]
        nc = nc.reindex(idx_all).fillna(0.0)
        uni = idx_all[pd.Series(idx_all.map(px), index=idx_all) >= 1.0]
        mcv = pd.Series(uni.map(mc_d), index=uni)
        mcv = mcv.fillna(agg13f.reindex(uni))          # documented fallback
        ctrl = pd.DataFrame({
            "lm": np.log(mcv),
            "la": np.log(pd.Series(uni.map(adv_d), index=uni))})
        nxt = qs[qi + 1] + pd.Timedelta(days=LAG) if qi + 1 < len(qs) \
            else dates[-1]
        fwd = forward_return(cum, dates, dec, min(nxt, dates[-1])).reindex(uni)
        rngq = np.random.default_rng(int(p.value) % (2**32))

        halves = rng_split.permutation(len(uni))
        h1 = set(np.array(uni)[halves[:len(uni) // 2]])

        def spread(names):
            s = nc.reindex(list(names)).fillna(0.0)
            c = ctrl.reindex(list(names))
            r = residualise(s.rank(pct=True), c).rank(pct=True)
            f = fwd.reindex(list(names))
            df = pd.concat([r.rename("s"), f.rename("f")], axis=1).dropna()
            if len(df) < 150:
                return np.nan, np.nan
            jit = pd.Series(rngq.uniform(0, 1e-9, len(df)), index=df.index)
            q5 = pd.qcut((df["s"] + jit).rank(), 5, labels=False)
            g = df.groupby(q5)["f"].mean()
            return (float(g.get(4, np.nan) - g.get(0, np.nan)),
                    float(sps.spearmanr(df["s"], df["f"])[0]))

        spF, icF = spread(uni)
        spA, _ = spread(h1)
        spB, _ = spread(set(uni) - h1)
        rows.append({"period": p, "n_uni": len(uni),
                     "spread_full": spF, "ic_full": icF,
                     "spread_half1": spA, "spread_half2": spB})
        log(f"{p.date()}: uni {len(uni)}, spread {spF:+.4f}")

    e = pd.DataFrame(rows)
    e.to_csv(OUT / "champion_expanded_events.csv", index=False)
    L = ["# Champion core on the EXPANDED universe + halving stability", "",
         f"- universe now {len(mdta.prices.columns)} tickers (was 3,927); "
         f"avg evaluated names/quarter: {e['n_uni'].mean():.0f}", "",
         f"## new_conviction (resid) - EXPANDED universe",
         f"- spread {e['spread_full'].mean():+.4f}/tri "
         f"(t={nw_tstat(e['spread_full']):+.2f}), Sharpe "
         f"{e['spread_full'].mean() / e['spread_full'].std() * 2:+.2f}, "
         f"IC {e['ic_full'].mean():+.4f}",
         f"- reference OLD universe, same protocol: t=+3.67 / +3.83 / "
         f"+3.27 across three prior implementations", "",
         "## Halving stability (random 50% coverage cuts, seeded)",
         f"- half 1: {e['spread_half1'].mean():+.4f}/tri "
         f"(t={nw_tstat(e['spread_half1']):+.2f})",
         f"- half 2: {e['spread_half2'].mean():+.4f}/tri "
         f"(t={nw_tstat(e['spread_half2']):+.2f})",
         "- reading: if the signal survives a random 50% coverage cut, "
         "quasi-random coverage (the name-match hole) cannot flip "
         "verdicts."]
    (OUT / "CHAMPION_EXPANDED.md").write_text("\n".join(L),
                                              encoding="utf-8")
    log("done")


if __name__ == "__main__":
    main()
