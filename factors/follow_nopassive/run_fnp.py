"""Follow-the-money (shadow-AUM copycat leaders) with the passive tail
excluded: does removing quasi-passive filers from the leader/follower
universe revive the follow signal?

    python run_fnp.py            # full sample
    python run_fnp.py --smoke

CONTEXT. The original copycat follow test (buy the fresh positions of
copied leaders, weighted by follower capital) came out INVERTED - newly
copied names show a hangover (t=-2.53). The user's hypothesis: the follow
side may have been polluted by quasi-passive leaders whose "fresh buys"
are index adds, not ideas. Note the original already excluded mega index
complexes via the 15-500 position cap; what remained possible is SMALLER
index-like filers (active share < 25%) acting as leaders or followers.

PAIRED DESIGN, one loop, two parallel graph states:
  A = original eligibility (15-500 positions, >= $250M)  [status quo]
  B = A minus filers with active share < 25% vs the VW market
      (applied to leaders AND followers AND the copy-graph edges)
Signal per track, identical to run_copycat: leaders in the top tercile of
trailing shadow AUM; their CURRENT new positions weighted by shadow AUM /
ADV; residualized on size/ADV; metrics = excess vs universe and top-half
spread within flagged names. Verdict = paired delta B-A (NW t) on both
metrics + the count of passive leaders that B removes.
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
for sub in ("", "general_plan", "general_predictive_signals"):
    sys.path.insert(0, str(HERE.parent / sub))

import market_cap as mc                             # noqa: E402
import panel as pn                                  # noqa: E402
from backtest_gp import forward_return, nw_tstat    # noqa: E402
from run_all import load_market, log                # noqa: E402
from run_signals import residualise                 # noqa: E402

RESULTS = HERE / "results"
LAG = 50
N_LEADERS = 300
TRAIL = 4
ACT_CUT = 0.25


def main(smoke: bool = False) -> None:
    RESULTS.mkdir(exist_ok=True)
    cmap, mdta = load_market()
    dates = mdta.prices.index
    cum = mdta.returns.cumsum()
    adv = mdta.dollar_volume.rolling(63, min_periods=20).median()
    shares = mc.shares_panel(dates, mdta.tickers, mdta.prices, mdta.prices_raw)
    mcap = mc.mktcap_panel(mdta.prices_raw, shares)

    qs = [q for q in pn.quarters()
          if pd.Timestamp("2013-06-30") <= q <= dates[-1] - pd.Timedelta(days=125)]
    if smoke:
        qs = qs[-12:]
    log(f"{len(qs)} quarters")

    hist = {"A": defaultdict(list), "B": defaultdict(list)}
    prev_new = {"A": None, "B": None}
    prev_leaders = {"A": [], "B": []}
    ev = []

    for qi in range(1, len(qs)):
        p, p1 = qs[qi], qs[qi - 1]
        dec = p + pd.Timedelta(days=LAG)
        if dec >= dates[-1] - pd.Timedelta(days=95):
            break
        cur = pn.snapshot_as_of(p, dec)
        prev = pn.snapshot_as_of(p1, dec)
        if min(len(cur), len(prev)) < 1000:
            continue
        g = cur.groupby("filer_id")["value_usd"]
        stats = pd.DataFrame({"aum": g.sum(), "n": g.size()})
        cur_sets = cur.groupby("filer_id")["instrument_id"].agg(frozenset)
        prev_sets = prev.groupby("filer_id")["instrument_id"].agg(frozenset)
        new = {f: cur_sets[f] - prev_sets.get(f, frozenset())
               for f in cur_sets.index}
        di = dates.searchsorted(dec, side="right") - 1
        adv_d, px = adv.iloc[di], mdta.prices_raw.iloc[di]
        mc_d = mcap.iloc[di]

        # active share per filer (mapped tickers vs VW market)
        d = cur[["filer_id", "instrument_id", "value_usd"]].copy()
        d["ticker"] = d["instrument_id"].map(cmap)
        dm = d.dropna(subset=["ticker"])
        bw = mc_d / mc_d.sum()
        act = {}
        for m_, gg in dm.groupby("filer_id"):
            w = gg.groupby("ticker")["value_usd"].sum()
            w = w / w.sum()
            act[m_] = 0.5 * float((w - bw.reindex(w.index).fillna(0.0))
                                  .abs().sum())
        act = pd.Series(act)

        elig_A = stats[(stats["n"].between(15, 500))
                       & (stats["aum"] >= 250e6)]
        passive = set(act.index[act < ACT_CUT])
        elig_B = elig_A[~elig_A.index.isin(passive)]

        row = {"period": p,
               "n_passive_elig": int(elig_A.index.isin(passive).sum())}
        for tag, elig in (("A", elig_A), ("B", elig_B)):
            leaders = elig.nlargest(N_LEADERS, "aum").index.tolist()
            if prev_new[tag]:
                followers = [f for f in elig.index
                             if f not in prev_leaders[tag]]
                for Bf in followers:
                    nb = new.get(Bf, frozenset())
                    if len(nb) < 3:
                        continue
                    raw = {A_: len(nb & la) / len(nb)
                           for A_, la in prev_new[tag].items() if la}
                    if not raw:
                        continue
                    base = np.mean(list(raw.values()))
                    for A_, v in raw.items():
                        if v - base > 0:
                            hist[tag][(Bf, A_)].append((qi, v - base))
            saum = defaultdict(float)
            for (Bf, A_), h in hist[tag].items():
                recent = [v for (qq, v) in h if qi - TRAIL <= qq <= qi]
                if recent and Bf in elig.index:
                    saum[A_] += float(elig.loc[Bf, "aum"]) \
                        * float(np.mean(recent))
            saum = pd.Series(saum, dtype=float)
            prev_new[tag] = {A_: new.get(A_, frozenset()) for A_ in leaders}
            prev_leaders[tag] = leaders
            if len(saum) < 30:
                continue
            hi_cut = saum.quantile(2 / 3)
            flow = defaultdict(float)
            n_lead_used = 0
            for A_ in leaders:
                sa = float(saum.get(A_, 0.0))
                if sa >= hi_cut and sa > 0:
                    n_lead_used += 1
                    for j in new.get(A_, frozenset()):
                        flow[j] += sa
            s = pd.Series(flow, dtype=float)
            t_ = s.index.to_series().map(cmap)
            s = s.groupby(t_).sum().dropna()
            advt = adv_d.reindex(s.index)
            sig = (s / advt).replace([np.inf, -np.inf], np.nan).dropna()
            sig = sig[px.reindex(sig.index) >= 1.0]
            if len(sig) < 80:
                continue
            ctrl = pd.DataFrame({
                "log_mktcap": np.log(mc_d.reindex(sig.index)),
                "log_adv": np.log(advt.reindex(sig.index))})
            r = residualise(np.log1p(sig.clip(lower=0)).rank(pct=True),
                            ctrl).rank(pct=True)
            nxt = qs[qi + 1] + pd.Timedelta(days=LAG) \
                if qi + 1 < len(qs) else dates[-1]
            fwd = forward_return(cum, dates, dec, min(nxt, dates[-1]))
            df = pd.concat([r.rename("s"),
                            fwd.reindex(r.index).rename("f")],
                           axis=1).dropna()
            if len(df) < 80:
                continue
            med = df["s"].median()
            uni_mean = float(fwd.reindex(
                px.index[px >= 1.0]).dropna().mean())
            row[f"excess_{tag}"] = float(df["f"].mean() - uni_mean)
            row[f"spread_{tag}"] = float(df["f"][df["s"] > med].mean()
                                         - df["f"][df["s"] <= med].mean())
            row[f"nlead_{tag}"] = n_lead_used
        ev.append(row)
        log(f"{p.date()}: passivos na elig {row['n_passive_elig']}, "
            f"excA {row.get('excess_A')}, excB {row.get('excess_B')}")

    e = pd.DataFrame(ev)
    e.to_csv(RESULTS / "fnp_events.csv", index=False)
    L = ["# follow_nopassive - seguir lideres copiados SEM a cauda passiva",
         "",
         "A = elegibilidade original (15-500 pos, >=250M) | B = A menos "
         "filers com active share < 25% (lideres E seguidores E arestas).",
         ""]
    if len(e):
        for m_, lbl in [("excess", "excesso vs universo"),
                        ("spread", "spread intra-flagged")]:
            a = e[f"{m_}_A"].dropna()
            b = e[f"{m_}_B"].dropna()
            dd_ = (e[f"{m_}_B"] - e[f"{m_}_A"]).dropna()
            L.append(f"- **{lbl}**: A {a.mean():+.4f}/tri "
                     f"(t={nw_tstat(a):+.2f}) | B {b.mean():+.4f}/tri "
                     f"(t={nw_tstat(b):+.2f}) | delta B-A "
                     f"{dd_.mean():+.4f} (t={nw_tstat(dd_):+.2f}, "
                     f"{len(dd_)} tri)")
        L.append(f"- passivos dentro da elegibilidade: "
                 f"{e['n_passive_elig'].mean():.0f} filers/tri; lideres "
                 f"usados A {e['nlead_A'].mean():.0f} vs B "
                 f"{e['nlead_B'].mean():.0f}")
    (RESULTS / "FNP_REPORT.md").write_text("\n".join(L), encoding="utf-8")
    log("done -> results/")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    main(**vars(ap.parse_args()))
