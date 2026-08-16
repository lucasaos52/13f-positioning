"""Champion refinement: new_conviction with the two measured drags removed.

    python run_champion.py [--smoke]

Not a new search - a surgical test of two PRE-IDENTIFIED, independently
significant drags on the champion's long leg:

  F1 copycat hangover: names just revealed by high-shadow-AUM leaders revert
     by -0.8%/q (t=-2.53) in our holding window (the post-pop reflux) - and
     the champion's long leg BUYS freshly-built positions, overlapping them.
  F2 stale demand: names with heavy 2-quarter cumulated institutional buying
     revert (dio_2q, t=-2.1) - fresh conviction in a name the crowd has been
     piling into for 6 months is late conviction.

Variants (directions pre-registered: filters should RAISE the long leg):
  V0 champion as-is (baseline, same construction as general_predictive_signals)
  V1 long leg excluding top-tercile copycat-flow names
  V2 long leg excluding top-tercile dio_2q names
  V3 both
Deltas vs V0 with NW t on the per-quarter differences (paired).
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
for sub in ("", "general_plan", "general_predictive_signals", "copycat", "ssi"):
    sys.path.insert(0, str(HERE.parent / sub))

import panel as pn                                  # noqa: E402
import market_cap as mc                             # noqa: E402
from backtest_gp import forward_return, nw_tstat    # noqa: E402
from run_all import load_market, log                # noqa: E402
from run_signals import residualise                 # noqa: E402
from run_ssi import new_conviction_signal           # noqa: E402

RESULTS = HERE / "results"
LAG = 50
N_LEADERS = 300
TRAIL = 4


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

    excess_hist: dict[tuple, list] = defaultdict(list)
    leaders_prev_new, leaders_prev = None, []
    io_hist: dict = {}
    rows = []

    for qi in range(2, len(qs)):
        p, p1, p2 = qs[qi], qs[qi - 1], qs[qi - 2]
        dec = p + pd.Timedelta(days=LAG)
        if dec >= dates[-1] - pd.Timedelta(days=95):
            break
        cur = pn.snapshot_as_of(p, dec)
        prev = pn.snapshot_as_of(p1, dec)
        prev2 = pn.snapshot_as_of(p2, dec)
        if min(len(cur), len(prev)) < 1000:
            continue
        di = dates.searchsorted(dec, side="right") - 1
        px, adv_d = mdta.prices_raw.iloc[di], adv.iloc[di]
        mc_d = mcap.iloc[di] if len(mcap) else pd.Series(dtype=float)

        # ---- copycat flow (same machinery as factors/copycat) ------------ #
        g = cur.groupby("filer_id")["value_usd"]
        stats = pd.DataFrame({"aum": g.sum(), "n": g.size()})
        elig = stats[(stats["n"].between(15, 500)) & (stats["aum"] >= 250e6)]
        leaders = elig.nlargest(N_LEADERS, "aum").index.tolist()
        cur_sets = cur.groupby("filer_id")["instrument_id"].agg(frozenset)
        prev_sets = prev.groupby("filer_id")["instrument_id"].agg(frozenset)
        new = {f: cur_sets[f] - prev_sets.get(f, frozenset())
               for f in cur_sets.index}
        if leaders_prev_new:
            for B in (f for f in elig.index if f not in leaders_prev):
                nb = new.get(B, frozenset())
                if len(nb) < 3:
                    continue
                raw = {A: len(nb & la) / len(nb)
                       for A, la in leaders_prev_new.items() if la}
                if raw:
                    base = np.mean(list(raw.values()))
                    for A, v in raw.items():
                        if v - base > 0:
                            excess_hist[(B, A)].append((qi, v - base))
        saum = defaultdict(float)
        for (B, A), hist in excess_hist.items():
            rec = [v for (qq, v) in hist if qi - TRAIL <= qq <= qi]
            if rec and B in elig.index:
                saum[A] += float(elig.loc[B, "aum"]) * float(np.mean(rec))
        saum = pd.Series(saum, dtype=float)
        flow = defaultdict(float)
        if len(saum) >= 30:
            hi = saum.quantile(2 / 3)
            for A in leaders:
                if float(saum.get(A, 0.0)) >= hi:
                    for j in new.get(A, frozenset()):
                        flow[j] += float(saum[A])
        flow = pd.Series(flow, dtype=float)
        flow_t = (flow.groupby(flow.index.to_series().map(cmap)).sum()
                  if len(flow) else pd.Series(dtype=float))

        # ---- dio_2q (io-ratio based, split-safe) -------------------------- #
        def io_ratio(snap, dix):
            sh = snap.groupby("instrument_id")["shares"].sum()
            so_row = shares.iloc[dix] if len(shares) else pd.Series(dtype=float)
            t = sh.index.to_series().map(cmap)
            io = (sh / t.map(so_row)).replace([np.inf, -np.inf], np.nan)
            io = io[(io > 0) & (io < 1.5)]
            return io.groupby(t.reindex(io.index)).sum()
        i_p = dates.searchsorted(p, side="right") - 1
        i_p2 = dates.searchsorted(p2, side="right") - 1
        dio2 = (io_ratio(cur, i_p) - io_ratio(prev2, i_p2)).dropna()

        # ---- champion: new_conviction resid ------------------------------- #
        nc = new_conviction_signal(cur, prev, cmap)
        u = nc.index[px.reindex(nc.index) >= 1.0]
        nc = nc.loc[nc.index.isin(u)]
        ctrl = pd.DataFrame({"log_mktcap": np.log(mc_d.reindex(nc.index)),
                             "log_adv": np.log(adv_d.reindex(nc.index))})
        r = residualise(nc.rank(pct=True), ctrl).rank(pct=True).dropna()
        if len(r) < 300:
            continue

        nxt = qs[qi + 1] + pd.Timedelta(days=LAG) if qi + 1 < len(qs) else dates[-1]
        fwd = forward_return(cum, dates, dec, min(nxt, dates[-1])).reindex(r.index)

        long_names = r.index[r >= r.quantile(0.8)]
        short_names = r.index[r <= r.quantile(0.2)]
        cc_hi = set(flow_t.nlargest(max(int(len(flow_t) / 3), 1)).index) \
            if len(flow_t) > 10 else set()
        d2 = dio2.reindex(r.index)
        d2_hi = set(d2.dropna().nlargest(int(d2.notna().sum() / 3)).index)

        def leg(names):
            f = fwd.reindex(list(names)).dropna()
            return float(f.mean()) if len(f) >= 20 else np.nan

        base_long = leg(long_names)
        rec = {"period": p, "n_long": len(long_names),
               "short": leg(short_names), "v0_long": base_long,
               "v1_long": leg([n for n in long_names if n not in cc_hi]),
               "v2_long": leg([n for n in long_names if n not in d2_hi]),
               "v3_long": leg([n for n in long_names
                               if n not in cc_hi and n not in d2_hi]),
               "n_cc_removed": len([n for n in long_names if n in cc_hi]),
               "n_d2_removed": len([n for n in long_names if n in d2_hi])}
        rows.append(rec)
        leaders_prev_new = {A: new.get(A, frozenset()) for A in leaders}
        leaders_prev = leaders
        log(f"{p.date()} done (cc removed {rec['n_cc_removed']}, "
            f"d2 removed {rec['n_d2_removed']})")

    e = pd.DataFrame(rows)
    e.to_csv(RESULTS / "champion_events.csv", index=False)
    L = ["# Champion refinement - new_conviction long leg, filtros medidos", ""]
    for v, lbl in [("v0", "baseline"), ("v1", "sem copycat-hangover"),
                   ("v2", "sem demanda velha (dio_2q)"), ("v3", "ambos")]:
        spread = e[f"{v}_long"] - e["short"]
        L += [f"## {v} ({lbl})",
              f"- long leg: {e[f'{v}_long'].mean():+.4f}/tri "
              f"t={nw_tstat(e[f'{v}_long']):+.2f}",
              f"- spread vs short comum: {spread.mean():+.4f}/tri "
              f"t={nw_tstat(spread):+.2f} | Sharpe "
              f"{spread.mean() / spread.std() * 2:.2f}", ""]
        if v != "v0":
            d = e[f"{v}_long"] - e["v0_long"]
            L.append(f"- DELTA vs baseline: {d.mean():+.4f}/tri "
                     f"t(NW, pareado)={nw_tstat(d):+.2f} | "
                     f"removidos/tri: cc {e.n_cc_removed.mean():.0f}, "
                     f"d2 {e.n_d2_removed.mean():.0f}")
            L.append("")
    (RESULTS / "CHAMPION_REPORT.md").write_text("\n".join(L), encoding="utf-8")
    log("done -> results/")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    main(**vars(ap.parse_args()))
