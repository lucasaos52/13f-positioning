"""End-to-end demo: Yahoo data -> factor portfolios -> grouping -> stats.

The `inds_raw` matrices do not exist yet, so three price-derived factors
stand in as templates (momentum 12-2, low-vol, short-term reversal). When
the real indicators arrive, replace `TEMPLATE_FACTORS` with
`Indicator(name, values=inds_raw[name])` — everything downstream is
unchanged.

Run (needs yfinance — the anaconda base env has it):
    python run_demo.py --quick        # 40 tickers, 2018+, smoke test
    python run_demo.py                # S&P 500, 2012+
"""
from __future__ import annotations

import argparse
import os

import pandas as pd

from backtest import Backtest
from filters import Filters
from grouping import group_and_combine
from indicator import Indicator
from market_data import MarketData, log, sp500_tickers
from portfolio import Portfolio

TRADING_FEE = 0.0005  # 5 bps on |trades|


# ── template factors (stand-ins until inds_raw exists) ─────────────────── #
def template_factors(md: MarketData) -> dict[str, pd.DataFrame]:
    """Each entry: dates x tickers, cell (t,i) uses only data through t."""
    return {
        # 12-1 momentum: skip the last month, it reverses
        "mom_12_2": md.prices.shift(21) / md.prices.shift(252) - 1,
        # defensive: negated 252d vol (high score = low vol)
        "low_vol": -md.volatility,
        # short-term reversal: last month's LOSERS score high
        "st_reversal": -(md.prices / md.prices.shift(21) - 1),
    }


def build_indicator_portfolio(name: str, values: pd.DataFrame, filters: Filters,
                              md: MarketData, rb_idxs, side: str = "HML",
                              pct: float = 0.2) -> Portfolio:
    """Raw values -> scored -> quantile portfolio -> rebalanced. The one
    function to call per indicator; `side` gives LS ('HML'/'LMH') or LO."""
    ind = Indicator(name, values=values)
    ind.filter_values(filters.universe).generate_z_scores().clip_scores(-3, 3)
    p = Portfolio.from_indicator(name, ind.scores, filters.universe, side=side, pct=pct)
    if side in ("HML", "LMH"):
        p.equalize()
    p.rebalance(rb_idxs, md.prices)
    return p


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="40 tickers, 2018+")
    ap.add_argument("--start", default=None)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--groups", type=int, default=2)
    ap.add_argument("--intersection", type=float, default=0.0,
                    help="fraction of a cluster's members that must agree on a position's side")
    args = ap.parse_args()

    tickers = sp500_tickers()[:40] if args.quick else sp500_tickers()
    start = args.start or ("2018-01-01" if args.quick else "2012-01-01")

    md = MarketData(tickers, start=start, refresh=args.refresh)
    filters = Filters(md, min_stocks=15 if args.quick else 50)
    rb_idxs = md.dates("1 month").get_idxs()

    log("building indicator portfolios (LS + LO)")
    ls_portfolios, lo_portfolios = [], []
    for name, values in template_factors(md).items():
        ls_portfolios.append(build_indicator_portfolio(name, values, filters, md, rb_idxs, side="HML"))
        lo_portfolios.append(build_indicator_portfolio(f"{name}_LO", values, filters, md, rb_idxs, side="LO"))

    # ── LS: absolute return net of fee+borrow, cash leg = treasury ─────── #
    log("LS backtest (net of fee, borrow, treasury on net exposure)")
    stats_ls = Backtest(ls_portfolios).performance_analysis(
        md, trading_fee=TRADING_FEE, cash_leg=md.treasury_yield, start=start)

    # ── LO: excess vs S&P (production's long-only convention) ──────────── #
    log("LO backtest (excess vs benchmark)")
    stats_lo = Backtest(lo_portfolios).performance_analysis(
        md, trading_fee=TRADING_FEE, cash_leg=md.benchmark_returns,
        benchmark=md.benchmark_returns, start=start)

    # ── grouping: cluster by corr, combine prop. to Sharpe ─────────────── #
    log(f"grouping LS portfolios into {args.groups} clusters "
        f"(intersection={args.intersection})")
    res = group_and_combine(ls_portfolios, md, n_groups=args.groups,
                            rb_idxs=rb_idxs, trading_fee=TRADING_FEE,
                            cash_leg=md.treasury_yield,
                            intersection=args.intersection)
    for k, names in enumerate(res["groups"]):
        log(f"group_{k + 1}: {names}", 1)
    stats_groups = Backtest(res["portfolios"] + [res["combined"]]).performance_analysis(
        md, trading_fee=TRADING_FEE, cash_leg=md.treasury_yield, start=start)

    print("\n== LS (absolute, net) " + "=" * 50)
    print(stats_ls.round(3).to_string())
    print("\n== LO (excess vs S&P) " + "=" * 50)
    print(stats_lo.round(3).to_string())
    print("\n== groups " + "=" * 62)
    print(stats_groups.round(3).to_string())

    os.makedirs("output", exist_ok=True)
    rets = Backtest(ls_portfolios + res["portfolios"] + [res["combined"]]).get_returns(
        md, trading_fee=TRADING_FEE, cash_leg=md.treasury_yield)
    rets["benchmark"] = md.benchmark_returns
    rets.to_csv("output/demo_returns.csv")
    log("daily net returns -> output/demo_returns.csv")


if __name__ == "__main__":
    main()
