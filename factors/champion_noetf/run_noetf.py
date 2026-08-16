"""Champion core with ETF-purged books: does removing ETF lines from the
13F books change new_conviction?

    python run_noetf.py            # full sample
    python run_noetf.py --smoke

WHAT THE DIAGNOSTIC SHOWED (and why this test is about BOOKS, not the
tradable universe): of 7,886 audited ETF instruments, only 1 maps to a
ticker in our crosswalk and 0 are in the price panel - the champion has
NEVER bought an ETF. But ETF lines are 14.6% of total book VALUE
(~$3.8T in 2025Q3), and the original champion construction computes book
weights and the top-decile conviction threshold on the FULL instrument-
level book - so a manager whose top decile is stuffed with SPY has his
threshold inflated and his stock votes suppressed. Purging ETFs promotes
stock positions into the top decile and changes WHO votes.

PAIRED TEST, same quarters, same protocol (D+45, resid, EW quintiles):
  A = status quo: weights/threshold on the full book (ETFs included in
      the denominator and eligible for the top decile), votes only from
      mapped tickers - replicates signal_defs.build_all behaviour;
  B = ETF-purged: ETF instruments dropped from the book BEFORE weights
      and threshold; everything else identical.
Verdict = paired delta of the quintile spread (NW t) + diagnostics
(AUM share purged, fraction of vote-sets changed).
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

import market_cap as mc                             # noqa: E402
import panel as pn                                  # noqa: E402
from backtest_gp import forward_return, nw_tstat    # noqa: E402
from run_all import load_market, log                # noqa: E402

RESULTS = HERE / "results"
ETF_FLAGS = HERE.parent / "ETF_strat" / "data" / "etf_universe_flags.csv"
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


def main(smoke: bool = False) -> None:
    RESULTS.mkdir(exist_ok=True)
    cmap, mdta = load_market()
    dates = mdta.prices.index
    cum = mdta.returns.cumsum()
    adv = mdta.dollar_volume.rolling(63, min_periods=20).median()
    shares = mc.shares_panel(dates, mdta.tickers, mdta.prices, mdta.prices_raw)
    mcap = mc.mktcap_panel(mdta.prices_raw, shares)
    etf = pd.read_csv(ETF_FLAGS, usecols=["instrument_id", "is_etf"])
    etf_set = set(etf.loc[etf["is_etf"] == True, "instrument_id"])  # noqa: E712

    qs = [q for q in pn.quarters()
          if pd.Timestamp("2013-06-30") <= q <= dates[-1] - pd.Timedelta(days=120)]
    if smoke:
        qs = qs[-12:]
    log(f"{len(qs)} quarters | {len(etf_set)} ETF instruments flagged")

    rows = []
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
        mc_d = mcap.iloc[di]
        fac_i = split_factor(cur, prev)

        is_etf_row = cur["instrument_id"].isin(etf_set)
        aum_share_etf = float(cur.loc[is_etf_row, "value_usd"].sum()
                              / cur["value_usd"].sum())
        n_filers = float(cur["filer_id"].nunique())
        prev_sh = prev.groupby(["filer_id", "instrument_id"])["shares"] \
            .sum()

        def build_nc(book: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
            """new_conviction per ticker from an instrument-level book;
            returns (nc, vote_key) where vote_key identifies the vote set."""
            b = book.copy()
            tot = b.groupby("filer_id")["value_usd"].transform("sum")
            b["w"] = b["value_usd"] / tot.replace(0, np.nan)
            thr = b.groupby("filer_id")["w"].transform(
                lambda s: s.quantile(0.9))
            b["thr"] = thr
            key = pd.MultiIndex.from_frame(
                b[["filer_id", "instrument_id"]])
            sh_p = pd.Series(prev_sh.reindex(key).values,
                             index=b.index)
            fac = b["instrument_id"].map(fac_i).fillna(1.0)
            grew = sh_p.isna() | (b["shares"] >= 1.25 * sh_p * fac)
            v = b[(b["w"] >= b["thr"]) & grew].copy()
            v["ticker"] = v["instrument_id"].map(cmap)
            v = v.dropna(subset=["ticker"])
            nc = (v.groupby("ticker")["filer_id"].nunique() / n_filers)
            vk = v.groupby("filer_id")["instrument_id"] \
                .agg(frozenset)
            return nc, vk

        nc_A, vk_A = build_nc(cur)
        nc_B, vk_B = build_nc(cur[~is_etf_row])
        common_f = vk_A.index.intersection(vk_B.index)
        changed = float((vk_A.loc[common_f] != vk_B.loc[common_f]).mean()) \
            if len(common_f) else np.nan

        idx = nc_A.index.union(nc_B.index)
        uni = idx[(pd.Series(idx.map(px), index=idx) >= 1.0)]
        ctrl = pd.DataFrame({
            "lm": np.log(pd.Series(uni.map(mc_d), index=uni)),
            "la": np.log(pd.Series(uni.map(adv_d), index=uni))})
        nxt = qs[qi + 1] + pd.Timedelta(days=LAG) if qi + 1 < len(qs) \
            else dates[-1]
        fwd = forward_return(cum, dates, dec, min(nxt, dates[-1])).reindex(uni)
        rng = np.random.default_rng(int(p.value) % (2**32))

        def spread(nc):
            s = nc.reindex(uni).fillna(0.0)
            r = residualise(s.rank(pct=True), ctrl).rank(pct=True)
            df = pd.concat([r.rename("s"), fwd.rename("f")], axis=1).dropna()
            if len(df) < 300:
                return np.nan, np.nan
            jit = pd.Series(rng.uniform(0, 1e-9, len(df)), index=df.index)
            q5 = pd.qcut((df["s"] + jit).rank(), 5, labels=False)
            g = df.groupby(q5)["f"].mean()
            return (float(g.get(4, np.nan) - g.get(0, np.nan)),
                    float(sps.spearmanr(df["s"], df["f"])[0]))

        spA, icA = spread(nc_A)
        spB, icB = spread(nc_B)
        rows.append({"period": p, "spread_A": spA, "spread_B": spB,
                     "ic_A": icA, "ic_B": icB,
                     "aum_share_etf": aum_share_etf,
                     "votes_changed": changed})
        log(f"{p.date()}: ETF {aum_share_etf:.1%} do book, votos "
            f"alterados {changed:.1%}, dSpread "
            f"{(spB - spA) if np.isfinite(spB) else float('nan'):+.4f}")

    ev = pd.DataFrame(rows)
    ev.to_csv(RESULTS / "noetf_events.csv", index=False)
    L = ["# champion_noetf - new_conviction com books purgados de ETF", "",
         "A = status quo (ETFs no denominador/threshold do book) | "
         "B = ETFs removidos ANTES dos pesos. Universo tradavel identico "
         "(ETF nunca foi compravel - 0 no painel de precos).", ""]
    if len(ev):
        d_sp = (ev["spread_B"] - ev["spread_A"]).dropna()
        d_ic = (ev["ic_B"] - ev["ic_A"]).dropna()
        L += [f"- ETFs = {ev['aum_share_etf'].mean():.1%} do valor dos "
              f"books (media); vote-sets alterados em "
              f"{ev['votes_changed'].mean():.1%} dos gestores/tri",
              f"- **A (status quo)**: spread {ev['spread_A'].mean():+.4f}"
              f"/tri (t={nw_tstat(ev['spread_A']):+.2f}), IC "
              f"{ev['ic_A'].mean():+.4f}",
              f"- **B (sem ETF)**: spread {ev['spread_B'].mean():+.4f}"
              f"/tri (t={nw_tstat(ev['spread_B']):+.2f}), IC "
              f"{ev['ic_B'].mean():+.4f}",
              f"- **delta pareado B-A**: spread {d_sp.mean():+.4f}/tri "
              f"(t={nw_tstat(d_sp):+.2f}), IC {d_ic.mean():+.4f} "
              f"(t={nw_tstat(d_ic):+.2f}), {len(d_sp)} tri"]
    (RESULTS / "NOETF_REPORT.md").write_text("\n".join(L), encoding="utf-8")
    log("done -> results/")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    main(**vars(ap.parse_args()))
