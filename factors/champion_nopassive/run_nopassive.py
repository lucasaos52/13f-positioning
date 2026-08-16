"""Champion core excluding INDEX-COMPLEX filers (Vanguard-like): does
removing the extreme passive tail of MANAGERS change new_conviction?

    python run_nopassive.py            # full sample
    python run_nopassive.py --smoke

WHY THIS IS NOT U2 AGAIN: U2 kept ONLY high-active-share managers (an
aggressive cut that failed, like every universe filter). This is the
mirror minimal cut: drop ONLY the extreme passive tail and keep the whole
rest of the census. Different question: "does the index complex pollute
the ballot?" rather than "are active managers better voters?".

IDENTIFICATION (structural, no name lists - Vanguard's 13F contains the
index STOCKS, not ETFs, so passivity is detected by signature):
    passive-tail filer at the decision date =
        active share vs the VW market < 0.25
        OR (positions > 1,000 AND quarter persistence > 95%)

PAIRED TEST, same protocol as champion_noetf:
  A = full census (status quo);
  B = census minus passive-tail filers (their books removed entirely -
      they neither vote nor count in the filer denominator).
Verdict = paired delta of the residualized quintile spread, NW t, plus
diagnostics (how many filers dropped, their AUM share, their vote share).
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
LAG = 45
ACT_CUT = 0.25
NPOS_CUT = 1000
PERS_CUT = 0.95


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

    qs = [q for q in pn.quarters()
          if pd.Timestamp("2013-06-30") <= q <= dates[-1] - pd.Timedelta(days=120)]
    if smoke:
        qs = qs[-12:]
    log(f"{len(qs)} quarters")

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
        prev_sh = prev.groupby(["filer_id", "instrument_id"])["shares"].sum()

        # ---- passive-tail identification --------------------------------- #
        d = cur[["filer_id", "instrument_id", "value_usd"]].copy()
        d["ticker"] = d["instrument_id"].map(cmap)
        dm = d.dropna(subset=["ticker"])
        bw = mc_d / mc_d.sum()
        act = {}
        for m_, g in dm.groupby("filer_id"):
            w = g.groupby("ticker")["value_usd"].sum()
            w = w / w.sum()
            act[m_] = 0.5 * float((w - bw.reindex(w.index).fillna(0.0))
                                  .abs().sum())
        act = pd.Series(act)
        npos = cur.groupby("filer_id")["instrument_id"].nunique()
        prev_sets = prev.groupby("filer_id")["instrument_id"].agg(set)
        cur_sets = cur.groupby("filer_id")["instrument_id"].agg(set)
        pers = {m_: len(cur_sets[m_] & prev_sets.get(m_, set()))
                / max(len(prev_sets.get(m_, set())), 1)
                for m_ in cur_sets.index if m_ in prev_sets.index}
        pers = pd.Series(pers)
        passive = set(act.index[(act < ACT_CUT)]) | set(
            npos.index[(npos > NPOS_CUT)
                       & (pers.reindex(npos.index).fillna(0) > PERS_CUT)])
        aum_all = cur.groupby("filer_id")["value_usd"].sum()
        aum_share = float(aum_all.reindex(list(passive)).sum()
                          / aum_all.sum()) if passive else 0.0

        def build_nc(book):
            b = book.copy()
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
            nf = float(book["filer_id"].nunique())
            return (v.groupby("ticker")["filer_id"].nunique() / nf,
                    int(len(v)))

        nc_A, votes_A = build_nc(cur)
        cur_B = cur[~cur["filer_id"].isin(passive)]
        nc_B, votes_B = build_nc(cur_B)
        # user ask: the PURE active-share cut (drop act < 0.25 only)
        act_only = set(act.index[act < ACT_CUT])
        nc_C, votes_C = build_nc(cur[~cur["filer_id"].isin(act_only)])

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
        spC, icC = spread(nc_C)
        rows.append({"period": p, "spread_A": spA, "spread_B": spB,
                     "spread_C": spC, "ic_A": icA, "ic_B": icB,
                     "ic_C": icC, "n_passive": len(passive),
                     "n_act_only": len(act_only),
                     "aum_share_passive": aum_share,
                     "votes_A": votes_A, "votes_B": votes_B,
                     "votes_C": votes_C})
        log(f"{p.date()}: {len(passive)} passivos ({aum_share:.1%} do AUM), "
            f"dSpread {(spB - spA) if np.isfinite(spB) else float('nan'):+.4f}")

    ev = pd.DataFrame(rows)
    ev.to_csv(RESULTS / "nopassive_events.csv", index=False)
    L = ["# champion_nopassive - censo sem a cauda passiva "
         "(complexos de indice)", "",
         "Passivo = active share < 0.25 OU (>1000 posicoes E persistencia "
         "> 95%). B remove esses filers INTEIROS (nao votam, nao contam "
         "no denominador). A = censo cheio.", ""]
    if len(ev):
        d_sp = (ev["spread_B"] - ev["spread_A"]).dropna()
        d_ic = (ev["ic_B"] - ev["ic_A"]).dropna()
        d_spC = (ev["spread_C"] - ev["spread_A"]).dropna()
        d_icC = (ev["ic_C"] - ev["ic_A"]).dropna()
        L += [f"- passivos excluidos (B): {ev['n_passive'].mean():.0f} "
              f"filers/tri = {ev['aum_share_passive'].mean():.1%} do AUM; "
              f"corte so-active-share (C): {ev['n_act_only'].mean():.0f} "
              f"filers/tri; votos {ev['votes_A'].mean():.0f} -> B "
              f"{ev['votes_B'].mean():.0f} / C {ev['votes_C'].mean():.0f}",
              f"- **A (censo cheio)**: spread {ev['spread_A'].mean():+.4f}"
              f"/tri (t={nw_tstat(ev['spread_A']):+.2f}), IC "
              f"{ev['ic_A'].mean():+.4f}",
              f"- **B (act<25% OU indice estrutural)**: spread "
              f"{ev['spread_B'].mean():+.4f}/tri "
              f"(t={nw_tstat(ev['spread_B']):+.2f}), IC "
              f"{ev['ic_B'].mean():+.4f}",
              f"- **C (so act>=25%, o pedido)**: spread "
              f"{ev['spread_C'].mean():+.4f}/tri "
              f"(t={nw_tstat(ev['spread_C']):+.2f}), IC "
              f"{ev['ic_C'].mean():+.4f}",
              f"- **delta pareado B-A**: {d_sp.mean():+.4f}/tri "
              f"(t={nw_tstat(d_sp):+.2f}), IC {d_ic.mean():+.4f} "
              f"(t={nw_tstat(d_ic):+.2f})",
              f"- **delta pareado C-A**: {d_spC.mean():+.4f}/tri "
              f"(t={nw_tstat(d_spC):+.2f}), IC {d_icC.mean():+.4f} "
              f"(t={nw_tstat(d_icC):+.2f}), {len(d_spC)} tri"]
    (RESULTS / "NOPASSIVE_REPORT.md").write_text("\n".join(L),
                                                 encoding="utf-8")
    log("done -> results/")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    main(**vars(ap.parse_args()))
