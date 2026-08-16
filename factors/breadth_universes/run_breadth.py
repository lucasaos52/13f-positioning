"""Breadth family x manager universe: number of DISTINCT HOLDERS per
asset (level) and its quarter-over-quarter CHANGE, each computed on two
voter universes - the full census vs active-share >= 25% filers only.

    python run_breadth.py            # full sample
    python run_breadth.py --smoke

WHAT IS NEW vs the 17-signal catalogue: breadth_level and dbreadth were
evaluated there on the FULL census only. Here each is recomputed on the
ACTIVE universe (act >= 25% vs the VW market, the user's cut) and the
paired delta answers: does restricting the ballot to active managers
sharpen the holder-count information?

SIGNALS (headline conventions inherited from signal_defs):
  breadth_level = n_holders / n_filers          THEOREM -> residual
      (dart-throwing VW books hold big stocks more often by construction)
  dbreadth      = n_c/nf_c - n_p/nf_p           raw headline
      (monkey books give ~0 everywhere; CHS 2002 replicated at +1.65%/q)
For the ACTIVE variant, both quarters' counts are restricted to filers
classified active at the CURRENT decision date (classification needs the
current book; a filer present only in the prior quarter keeps his prior-
quarter vote only in the census version - noted, second-order).

Evaluation: standard protocol (D+45 PIT, price >= $1, holders floor >= 5,
EW quintiles, NW(4), IC). Verdict = paired deltas ACTIVE - CENSUS.
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

    events: dict[tuple, list] = {}
    paired: dict[str, list] = {"breadth_level": [], "dbreadth": []}
    diag = []

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

        def to_pairs(df):
            d = df[["filer_id", "instrument_id", "value_usd"]].copy()
            d["ticker"] = d["instrument_id"].map(cmap)
            return d.dropna(subset=["ticker"])

        pc, pp = to_pairs(cur), to_pairs(prev)

        # active-share classification at the current decision date
        bw = mc_d / mc_d.sum()
        act = {}
        for m_, g in pc.groupby("filer_id"):
            w = g.groupby("ticker")["value_usd"].sum()
            w = w / w.sum()
            act[m_] = 0.5 * float((w - bw.reindex(w.index).fillna(0.0))
                                  .abs().sum())
        act = pd.Series(act)
        active = set(act.index[act >= ACT_CUT])
        diag.append({"period": p, "n_all": int(act.size),
                     "n_active": len(active)})

        sigs = {}
        for tag, keep in (("census", None), ("active", active)):
            c_ = pc if keep is None else pc[pc["filer_id"].isin(keep)]
            p_ = pp if keep is None else pp[pp["filer_id"].isin(keep)]
            nf_c = float(c_["filer_id"].nunique())
            nf_p = float(p_["filer_id"].nunique())
            n_c = c_.groupby("ticker")["filer_id"].nunique()
            n_p = p_.groupby("ticker")["filer_id"].nunique()
            idx = n_c.index.union(n_p.index)
            sigs[(tag, "breadth_level")] = (n_c / nf_c).reindex(idx)
            sigs[(tag, "dbreadth")] = (n_c.reindex(idx).fillna(0) / nf_c
                                       - n_p.reindex(idx).fillna(0) / nf_p)
            sigs[(tag, "_nmax")] = pd.concat(
                [n_c.reindex(idx), n_p.reindex(idx)], axis=1) \
                .max(axis=1).fillna(0)

        idx = sigs[("census", "breadth_level")].index
        uni = idx[(pd.Series(idx.map(px), index=idx) >= 1.0)
                  & (sigs[("census", "_nmax")] >= 5)]
        ctrl = pd.DataFrame({
            "lm": np.log(pd.Series(uni.map(mc_d), index=uni)),
            "la": np.log(pd.Series(uni.map(adv_d), index=uni))})
        nxt = qs[qi + 1] + pd.Timedelta(days=LAG) if qi + 1 < len(qs) \
            else dates[-1]
        fwd = forward_return(cum, dates, dec, min(nxt, dates[-1])).reindex(uni)
        rng = np.random.default_rng(int(p.value) % (2**32))

        qmetrics = {}
        for (tag, name), s in sigs.items():
            if name.startswith("_"):
                continue
            s = s.reindex(uni).replace([np.inf, -np.inf], np.nan)
            s = s.clip(s.quantile(0.01), s.quantile(0.99))
            r = s.rank(pct=True)
            if name == "breadth_level":                  # theorem
                r = residualise(r, ctrl).rank(pct=True)
            df = pd.concat([r.rename("s"), fwd.rename("f")], axis=1).dropna()
            if len(df) < 300:
                continue
            jit = pd.Series(rng.uniform(0, 1e-9, len(df)), index=df.index)
            q5 = pd.qcut((df["s"] + jit).rank(), 5, labels=False)
            gq = df.groupby(q5)["f"].mean()
            sp = float(gq.get(4, np.nan) - gq.get(0, np.nan))
            ic = float(sps.spearmanr(df["s"], df["f"])[0])
            events.setdefault((tag, name), []).append(
                {"period": p, "spread": sp, "ic": ic})
            qmetrics[(tag, name)] = (sp, ic)
        for name in ("breadth_level", "dbreadth"):
            a = qmetrics.get(("census", name))
            b = qmetrics.get(("active", name))
            if a and b:
                paired[name].append({"period": p,
                                     "d_spread": b[0] - a[0],
                                     "d_ic": b[1] - a[1]})
        log(f"{p.date()}: {len(active)}/{act.size} ativos")

    dg = pd.DataFrame(diag)
    L = ["# breadth_universes - holders distintos (nivel e variacao) x "
         "universo de eleitores", "",
         f"active = act share >= {ACT_CUT:.0%}; media "
         f"{dg['n_active'].mean():.0f} de {dg['n_all'].mean():.0f} "
         f"filers/tri classificados ativos.", "",
         "## Sinais por universo (spread EW Q5-Q1, NW t, IC)", ""]
    for (tag, name), evs in sorted(events.items()):
        e = pd.DataFrame(evs)
        L.append(f"- **{name} [{tag}]**: {e['spread'].mean():+.4f}/tri "
                 f"(t={nw_tstat(e['spread']):+.2f}), IC "
                 f"{e['ic'].mean():+.4f}, {len(e)} tri")
    L += ["", "## Deltas pareados (active - census)", ""]
    for name, rows_ in paired.items():
        if not rows_:
            continue
        pr = pd.DataFrame(rows_)
        L.append(f"- **{name}**: dSpread {pr['d_spread'].mean():+.4f}/tri "
                 f"(t={nw_tstat(pr['d_spread']):+.2f}), dIC "
                 f"{pr['d_ic'].mean():+.4f} "
                 f"(t={nw_tstat(pr['d_ic']):+.2f}), {len(pr)} tri")
        pr.to_csv(RESULTS / f"paired_{name}.csv", index=False)
    (RESULTS / "BREADTH_UNIV_REPORT.md").write_text("\n".join(L),
                                                    encoding="utf-8")
    log("done -> results/")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    main(**vars(ap.parse_args()))
