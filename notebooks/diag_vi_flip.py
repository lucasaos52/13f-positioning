"""Diagnose the VI sign flip vs the paper: restricted vs all-filers deltas.

Hypotheses under test, run under the PAPER timing (their lookahead):
  H1 delta definition — the paper's D seems to include filers entering and
     leaving the sample (whole books counted as buys/sells); our main panel
     restricts to filers present in both quarters. Entries/exits are whole
     positions, so VI diverges far more than TI.
  H2 composition/survivorship — contrarian VI shorts the names with the
     biggest surviving-institution buying: in a survivors-only price panel
     those are the winners, so the short leg bleeds.

Outputs the same headline cells as the replica for both panel variants,
plus the liquidity composition of what each variant selects.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sps

warnings.filterwarnings("ignore")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[0] / "factors"))
import os

os.chdir(HERE.parents[0] / "factors")
from market_data import MarketData  # noqa: E402

cmap = (pd.read_csv(HERE / "data" / "cm_map_wide.csv", dtype=str)
        .dropna().set_index("instrument_id")["ticker"])
tickers = sorted(cmap.unique())
mdta = MarketData(tickers, start="2012-06-01", benchmark="SPY")
os.chdir(HERE)

RET, SPY = mdta.returns, mdta.benchmark_returns
CUM, CUM_SPY = RET.cumsum(), SPY.cumsum()
DV = mdta.dollar_volume.rolling(63, min_periods=20).median()

PAPER_END = pd.Timestamp("2021-09-30")
AVAIL = 71


def load_panel(name):
    p = pd.read_csv(HERE / "data" / name, parse_dates=["period_end"])
    p["ticker"] = p["instrument_id"].map(cmap)
    p = p.dropna(subset=["ticker"])
    return p[p.ticker.isin(RET.columns) & (p.period_end <= PAPER_END)]


def grid(panel, signal_col, N=50):
    rows, comp = [], []
    for p, grp in panel.groupby("period_end"):
        pos = RET.index.searchsorted(p, side="right")
        if pos >= len(RET.index) - 63:
            continue
        g = grp.set_index("ticker")[[signal_col, "n_active"]].dropna()
        g = g[(g[signal_col] != 0) & (g.n_active >= N)]
        if len(g) < 20:
            continue
        absI = g[signal_col].abs()
        for qr, frac in [("qr4", 0.25), ("qr5", 0.20)]:
            sel = g[absI >= absI.quantile(1 - frac)]
            dv = DV.iloc[pos - 1].reindex(sel.index)
            comp.append({"qr": qr, "median_dv_musd": float(dv.median() / 1e6),
                         "n": len(sel)})
            for m in (21, 42):
                end = pos + m - 1
                fa = CUM.iloc[end] - CUM.iloc[pos - 1]
                fs = float(CUM_SPY.iloc[end] - CUM_SPY.iloc[pos - 1])
                mer = fa.reindex(sel.index) - fs
                ok = mer.notna()
                side = -np.sign(sel[signal_col][ok])
                rows.append({"period": p, "qr": qr, "m": m,
                             "pnl": float((side * mer[ok]).sum())})
    ev = pd.DataFrame(rows)
    out = ev.groupby(["qr", "m"])["pnl"].agg(["mean", "std", "size"]).reset_index()
    out["sharpe"] = out["mean"] / out["std"] * np.sqrt(4)
    sr = out["mean"] / out["std"]
    out["t"] = sr * np.sqrt(out["size"])
    return out, pd.DataFrame(comp).groupby("qr").median()


# cusip6 -> ticker: per issuer, keep the most liquid mapped share class
cmap6_df = cmap.reset_index()
cmap6_df["c6"] = cmap6_df["instrument_id"].str.slice(0, 6)
liq = mdta.dollar_volume.mean()
cmap6_df["liq"] = cmap6_df["ticker"].map(liq)
cmap6 = (cmap6_df.sort_values("liq", ascending=False)
         .drop_duplicates("c6").set_index("c6")["ticker"])


def load_panel6(name):
    p = pd.read_csv(HERE / "data" / name, parse_dates=["period_end"])
    p["ticker"] = p["instrument_id"].map(cmap6)
    p = p.dropna(subset=["ticker"])
    return p[p.ticker.isin(RET.columns) & (p.period_end <= PAPER_END)]


VARIANTS = [
    ("RESTRITO cusip9 (filers em ambos os tri)", "imbalance_panel.csv.gz", load_panel),
    ("ALL-FILERS cusip9", "imbalance_panel_allfilers.csv.gz", load_panel),
    ("RECEITA DO PAPER (all-filers + CUSIP6)", "imbalance_panel_cusip6.csv.gz", load_panel6),
]
for variant, fname, loader in VARIANTS:
    panel = loader(fname)
    print(f"\n{'=' * 74}\n{variant}: {len(panel):,} stock-quarters mapeados")
    for col in ("vi", "ti"):
        out, comp = grid(panel, col)
        print(f"-- {col.upper()} contrario, N=50, timing paper --")
        print(out.round(3).to_string(index=False))
        print(f"   composicao mediana dos selecionados (US$M volume/dia): "
              f"{comp['median_dv_musd'].round(1).to_dict()}")
