"""Champion through the REAL backtester (the factors/ mini-multifactor):
monthly rebalance with drift, 5bps fee, daily borrow accrual, treasury leg,
LS (net) and LO (excess vs S&P) - the production conventions.

    python run_champion_bt.py

Pipeline: rebuild the champion cross-sections quarterly (new_conviction
residualised + copycat-hangover filter, decision at p+50d by filed_date),
forward-fill each cross-section from ITS decision date (step function - the
signal is quarterly, the book rebalances monthly on the latest known
signal), then hand the indicator matrix to the standard machinery:
filters.universe -> from_indicator (HML / long_only) -> adjust_by_volatility
(the multifactor's vol weighting) -> rebalance/period_return with costs.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
for sub in ("", "general_plan", "general_predictive_signals", "ssi"):
    sys.path.insert(0, str(HERE.parent / sub))

import panel as pn                                  # noqa: E402
import market_cap as mc                             # noqa: E402
from run_all import load_market, log                # noqa: E402
from run_signals import residualise                 # noqa: E402
from run_ssi import new_conviction_signal           # noqa: E402

RESULTS = HERE / "results"
LAG = 50
N_LEADERS = 300
TRAIL = 4


def build_signal_panel(cmap, mdta):
    """Quarterly champion cross-sections -> daily ffilled indicator matrix."""
    cache = RESULTS / "champion_signal_panel.parquet"
    if cache.exists():
        return pd.read_parquet(cache)
    dates = mdta.prices.index
    adv = mdta.dollar_volume.rolling(63, min_periods=20).median()
    shares = mc.shares_panel(dates, mdta.tickers, mdta.prices, mdta.prices_raw)
    mcap = mc.mktcap_panel(mdta.prices_raw, shares)
    qs = [q for q in pn.quarters()
          if pd.Timestamp("2013-06-30") <= q <= dates[-1] - pd.Timedelta(days=60)]

    excess_hist: dict[tuple, list] = defaultdict(list)
    leaders_prev_new, leaders_prev = None, []
    cross: dict[pd.Timestamp, pd.Series] = {}
    for qi in range(1, len(qs)):
        p, p1 = qs[qi], qs[qi - 1]
        dec = p + pd.Timedelta(days=LAG)
        if dec >= dates[-1]:
            break
        cur = pn.snapshot_as_of(p, dec)
        prev = pn.snapshot_as_of(p1, dec)
        if min(len(cur), len(prev)) < 1000:
            continue
        di = dates.searchsorted(dec, side="right") - 1
        px, adv_d = mdta.prices_raw.iloc[di], adv.iloc[di]
        mc_d = mcap.iloc[di] if len(mcap) else pd.Series(dtype=float)

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
        for (B, A), h in excess_hist.items():
            rec = [v for (qq, v) in h if qi - TRAIL <= qq <= qi]
            if rec and B in elig.index:
                saum[A] += float(elig.loc[B, "aum"]) * float(np.mean(rec))
        saum = pd.Series(saum, dtype=float)
        cc_hi_t = set()
        if len(saum) >= 30:
            hi = saum.quantile(2 / 3)
            flow = defaultdict(float)
            for A in leaders:
                if float(saum.get(A, 0.0)) >= hi:
                    for j in new.get(A, frozenset()):
                        flow[j] += float(saum[A])
            fs = pd.Series(flow, dtype=float)
            ft = fs.groupby(fs.index.to_series().map(cmap)).sum()
            if len(ft) > 10:
                cc_hi_t = set(ft.nlargest(max(int(len(ft) / 3), 1)).index)

        nc = new_conviction_signal(cur, prev, cmap)
        nc = nc[px.reindex(nc.index) >= 1.0]
        ctrl = pd.DataFrame({"log_mktcap": np.log(mc_d.reindex(nc.index)),
                             "log_adv": np.log(adv_d.reindex(nc.index))})
        r = residualise(nc.rank(pct=True), ctrl).rank(pct=True).dropna()
        r[r.index.isin(cc_hi_t)] = np.nan       # the V1 filter: drop hangover
        cross[dates[min(di + 1, len(dates) - 1)]] = r
        leaders_prev_new = {A: new.get(A, frozenset()) for A in leaders}
        leaders_prev = leaders
        log(f"signal {p.date()}: {r.notna().sum()} names "
            f"({len(cc_hi_t)} filtered)")

    panel = pd.DataFrame(cross).T.sort_index()
    panel = panel.reindex(dates).ffill(limit=75)    # step function, PIT
    panel.to_parquet(cache)
    return panel


def main() -> None:
    RESULTS.mkdir(exist_ok=True)
    import os
    os.chdir(HERE.parent)
    from backtest import Backtest                    # noqa: E402
    from filters import Filters                      # noqa: E402
    from portfolio import Portfolio                  # noqa: E402
    cmap, mdta = load_market()
    flt = Filters(mdta)
    os.chdir(HERE)

    inds = build_signal_panel(cmap, mdta)
    inds = inds[[c for c in inds.columns if c in mdta.prices.columns]] \
        .reindex(index=mdta.prices.index)

    first = str(inds.dropna(how="all").index[0].date())
    rb_idxs = mdta.dates("1 month").get_idxs(first_date=first)

    rows = {}
    for side in ("HML", "LO"):
        p = Portfolio.from_indicator(f"champ_{side}", inds, flt.universe,
                                     side=side, pct=0.2, min_stocks=40)
        p = p.adjust_by_volatility(mdta.volatility)
        p = p.normalize(type="split" if side == "HML" else "long")
        p.rebalance(rb_idxs, mdta.prices)
        rets = Backtest([p]).get_returns(mdta, trading_fee=0.0005)
        rr = rets.iloc[:, 0].dropna()
        rr = rr[rr.index >= pd.Timestamp(first)]
        if side == "LO":
            rr = rr - mdta.benchmark_returns.reindex(rr.index).fillna(0)
        ann = rr.mean() * 252
        vol = rr.std() * np.sqrt(252)
        eq = rr.cumsum()
        mode = "ls" if side == "HML" else "lo"
        rows[mode] = {"ann_return": ann, "ann_vol": vol,
                      "sharpe": ann / vol if vol > 0 else np.nan,
                      "max_dd": float((eq - eq.cummax()).min()),
                      "hit": float((rr > 0).mean()),
                      "equity": eq}

    # ---- chart + report --------------------------------------------------- #
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(11, 5.5))
    ax.plot(rows["ls"]["equity"].index, 100 * rows["ls"]["equity"],
            label=f"LS net (Sharpe {rows['ls']['sharpe']:.2f})", lw=1.8)
    ax.plot(rows["lo"]["equity"].index, 100 * rows["lo"]["equity"],
            label=f"LO excesso vs S&P (Sharpe {rows['lo']['sharpe']:.2f})",
            lw=1.8)
    ax.set_ylabel("PnL acumulado (%)")
    ax.set_title("Champion (new_conviction + filtro copycat) no backtester "
                 "factors/: rebal mensal, 5bps, borrow, vol-weighted")
    ax.legend(); ax.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(RESULTS / "champion_bt.png", dpi=130)

    L = ["# Champion no backtester de producao (factors/)", "",
         "| modo | ret a.a. | vol | Sharpe | maxDD | hit |",
         "|---|---|---|---|---|---|"]
    for mode in ("ls", "lo"):
        r = rows[mode]
        L.append(f"| {mode.upper()} | {r['ann_return']:+.2%} | "
                 f"{r['ann_vol']:.2%} | **{r['sharpe']:.2f}** | "
                 f"{r['max_dd']:+.2%} | {r['hit']:.1%} |")
    L += ["", "Convencoes: rebal mensal com drift, fee 5bps por lado, borrow "
          "50bps a.a. acruado diario no short, cash leg em T-bill (LS), "
          "excesso vs S&P (LO), vol-weighted como o multifactor. Sinal "
          "trimestral em step function a partir da data de decisao (PIT)."]
    (RESULTS / "CHAMPION_BT_REPORT.md").write_text("\n".join(L),
                                                   encoding="utf-8")
    print("\n".join(L[2:]))
    log("done -> results/")


if __name__ == "__main__":
    main()
