"""Shadow AUM / copycat flow - implementation of README.md.

    python run_copycat.py [--smoke]
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
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "general_plan"))
sys.path.insert(0, str(HERE.parent / "general_predictive_signals"))

import panel as pn                                  # noqa: E402
import market_cap as mc                             # noqa: E402
from backtest_gp import forward_return, nw_tstat    # noqa: E402
from run_all import load_market, log                # noqa: E402
from run_signals import residualise                 # noqa: E402

RESULTS = HERE / "results"
LAG = 50               # decision: leaders' quarter-t filings ~all public
N_LEADERS = 300
TRAIL = 4              # quarters of copy-score history for shadow AUM


def books_and_innovations(p, p1, dec):
    """Per-filer stats, current book sets and NEW positions at quarter p,
    both snapshots taken at the same decision date."""
    cur = pn.snapshot_as_of(p, dec)
    prev = pn.snapshot_as_of(p1, dec)
    if min(len(cur), len(prev)) < 1000:
        return None
    g = cur.groupby("filer_id")["value_usd"]
    stats = pd.DataFrame({"aum": g.sum(), "n": g.size()})
    cur_sets = cur.groupby("filer_id")["instrument_id"].agg(frozenset)
    prev_sets = prev.groupby("filer_id")["instrument_id"].agg(frozenset)
    new = {f: cur_sets[f] - prev_sets.get(f, frozenset())
           for f in cur_sets.index}
    return stats, new, cur


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

    # copy scores per (follower, leader) per quarter, filled as we walk
    excess_hist: dict[tuple, list] = defaultdict(list)
    leaders_prev_new = None          # leaders' innovations at q-1
    leaders_prev = []
    ev, stab, prev_saum = [], [], None

    for qi in range(1, len(qs)):
        p, p1 = qs[qi], qs[qi - 1]
        dec = p + pd.Timedelta(days=LAG)
        if dec >= dates[-1] - pd.Timedelta(days=95):
            break
        out = books_and_innovations(p, p1, dec)
        if out is None:
            continue
        stats, new, cur = out
        elig = stats[(stats["n"].between(15, 500)) & (stats["aum"] >= 250e6)]
        leaders = elig.nlargest(N_LEADERS, "aum").index.tolist()

        # ---- copy scores: followers' new(q) vs leaders' new(q-1) --------- #
        if leaders_prev_new:
            followers = [f for f in elig.index if f not in leaders_prev]
            for B in followers:
                nb = new.get(B, frozenset())
                if len(nb) < 3:
                    continue
                raw = {A: len(nb & la) / len(nb)
                       for A, la in leaders_prev_new.items() if la}
                if not raw:
                    continue
                base = np.mean(list(raw.values()))
                for A, v in raw.items():
                    if v - base > 0:
                        excess_hist[(B, A)].append((qi, v - base))

        # ---- shadow AUM per leader (trailing TRAIL quarters, past only) --- #
        saum = defaultdict(float)
        for (B, A), hist in excess_hist.items():
            recent = [v for (qq, v) in hist if qi - TRAIL <= qq <= qi]
            if recent and B in elig.index:
                saum[A] += float(elig.loc[B, "aum"]) * float(np.mean(recent))
        saum = pd.Series(saum, dtype=float)
        if prev_saum is not None and len(saum) > 20:
            common = saum.index.intersection(prev_saum.index)
            if len(common) > 20:
                stab.append(float(saum[common].rank().corr(
                    prev_saum[common].rank())))
        prev_saum = saum

        # ---- signal: expected copycat flow on leaders' CURRENT new buys -- #
        if len(saum) < 30:
            leaders_prev_new = {A: new.get(A, frozenset()) for A in leaders}
            leaders_prev = leaders
            continue
        di = dates.searchsorted(dec, side="right") - 1
        adv_d, px = adv.iloc[di], mdta.prices_raw.iloc[di]
        mc_d = mcap.iloc[di] if len(mcap) else pd.Series(dtype=float)

        hi_cut = saum.quantile(2 / 3)
        lo_cut = saum.quantile(1 / 3)
        flow_hi, flow_lo = defaultdict(float), defaultdict(float)
        for A in leaders:
            sa = float(saum.get(A, 0.0))
            for j in new.get(A, frozenset()):
                if sa >= hi_cut:
                    flow_hi[j] += sa
                elif sa <= lo_cut:
                    flow_lo[j] += 1.0          # placebo: unweighted presence
        nxt = qs[qi + 1] + pd.Timedelta(days=LAG) if qi + 1 < len(qs) \
            else dates[-1]
        fwd = forward_return(cum, dates, dec, min(nxt, dates[-1]))

        for name, fdict in [("shadow_flow", flow_hi), ("placebo_lowsaum", flow_lo)]:
            s = pd.Series(fdict, dtype=float)
            t = s.index.to_series().map(cmap)
            s = s.groupby(t).sum().dropna()
            advt = adv_d.reindex(s.index)
            sig = (s / advt).replace([np.inf, -np.inf], np.nan).dropna()
            sig = sig[px.reindex(sig.index) >= 1.0]
            if len(sig) < 80:
                continue
            ctrl = pd.DataFrame({"log_mktcap": np.log(mc_d.reindex(sig.index)),
                                 "log_adv": np.log(advt.reindex(sig.index))})
            r = residualise(np.log1p(sig.clip(lower=0)).rank(pct=True),
                            ctrl).rank(pct=True)
            df = pd.concat([r.rename("s"), fwd.reindex(r.index).rename("f")],
                           axis=1).dropna()
            if len(df) < 80:
                continue
            # signal names vs the rest of the tradable universe: top-half
            # spread within flagged names + mean excess vs ALL stocks
            med = df["s"].median()
            uni_mean = float(fwd.reindex(
                px.index[px >= 1.0]).dropna().mean())
            ev.append({
                "period": p, "signal": name, "n": len(df),
                "excess_all": float(df["f"].mean() - uni_mean),
                "spread_hilo": float(df["f"][df["s"] > med].mean()
                                     - df["f"][df["s"] <= med].mean())})
        leaders_prev_new = {A: new.get(A, frozenset()) for A in leaders}
        leaders_prev = leaders
        log(f"{p.date()} done (leaders c/ saum: {len(saum)})")

    e = pd.DataFrame(ev)
    e.to_csv(RESULTS / "copycat_events.csv", index=False)
    L = [f"# Shadow AUM / copycat flow - {N_LEADERS} lideres, trailing {TRAIL}q", ""]
    for name, g in e.groupby("signal"):
        tag = " <- TESE" if name == "shadow_flow" else " <- placebo (sem seguidores)"
        L += [f"## {name}{tag}",
              f"- excesso vs universo: {g.excess_all.mean():+.4f}/tri "
              f"t={nw_tstat(g.excess_all):+.2f}",
              f"- spread intra-flagged (alto vs baixo fluxo): "
              f"{g.spread_hilo.mean():+.4f}/tri t={nw_tstat(g.spread_hilo):+.2f}",
              f"- n medio de nomes: {g.n.mean():.0f} | eventos: {len(g)}", ""]
    if stab:
        L.append(f"## estabilidade do shadow AUM (rank corr t vs t-1): "
                 f"{np.mean(stab):.2f}")
    (RESULTS / "COPYCAT_REPORT.md").write_text("\n".join(L), encoding="utf-8")
    log("done -> results/")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    main(**vars(ap.parse_args()))
