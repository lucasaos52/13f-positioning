"""Confounder ladder for dBreadth: is the spread just another factor in drag?

The plan §5.3 ladder, run with real Ken French factors (all free):

    raw -> CAPM -> FF3 -> FF5 -> FF6 (+momentum) -> FF6 + short-term reversal

Why each rung targets a specific confounder:
  - SMB: breadth changes concentrate in smaller names (more room for new
    holders); a naive Angelini-style replication carries SMB ~0.63.
  - UMD (momentum): dBreadth follows returns - feedback trading
    (Nofsinger-Sias) - so a raw sort may be momentum in drag. Chen-Hong-
    Stein's own adjusted spread drops from 6.38% to 4.95%/12mo.
  - ST_Rev: the sharpest version of the same worry at one-month horizon.
  - RMW/CMA: quality tilts of institutional buying (Edelen-Ince-Kadlec:
    institutions buy the WRONG side of anomalies - sign could go either way).

Betas are reported alongside alphas: "um fator de posicionamento com beta
0,4 em SMB nao e um fator de posicionamento" (plan §5.3).

A naive approach neutralises ex ante and quotes literature alphas, but never
ran his own attribution - his stated next step. This closes that gap on our
side with ~40 quarters of monthly series.
"""
from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import requests

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import panel as pn                    # noqa: E402
from backtest_gp import nw_tstat      # noqa: E402
from run_all import load_market, log  # noqa: E402

RESULTS = HERE / "results"
KF = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
FILES = {
    "ff5": ("F-F_Research_Data_5_Factors_2x3_CSV.zip",
            ["mkt_rf", "smb", "hml", "rmw", "cma", "rf"]),
    "mom": ("F-F_Momentum_Factor_CSV.zip", ["umd"]),
    "strev": ("F-F_ST_Reversal_Factor_CSV.zip", ["strev"]),
}


def kf_monthly(name: str) -> pd.DataFrame:
    fname, cols = FILES[name]
    cache = HERE / "data" / f"kf_{name}.csv"
    if cache.exists():
        return pd.read_csv(cache, index_col=0, parse_dates=True)
    raw = requests.get(KF + fname, timeout=60).content
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        txt = z.read(z.namelist()[0]).decode("latin-1")
    lines = txt.splitlines()
    start = next(i for i, l in enumerate(lines)
                 if l.strip()[:6].isdigit() and len(l.strip()[:6]) == 6)
    end = next((i for i in range(start, len(lines))
                if not lines[i].strip()[:6].isdigit()), len(lines))
    df = pd.read_csv(io.StringIO("\n".join(lines[start:end])), header=None)
    df.columns = ["ym"] + cols
    df["date"] = pd.to_datetime(df["ym"].astype(int).astype(str),
                                format="%Y%m") + pd.offsets.MonthEnd(0)
    out = df.set_index("date")[cols] / 100.0
    out.to_csv(cache)
    return out


def ladder(y: pd.Series, F: pd.DataFrame) -> list[dict]:
    """y = monthly LONG-SHORT return (already excess by construction)."""
    rungs = [("raw", []),
             ("CAPM", ["mkt_rf"]),
             ("FF3", ["mkt_rf", "smb", "hml"]),
             ("FF5", ["mkt_rf", "smb", "hml", "rmw", "cma"]),
             ("FF6", ["mkt_rf", "smb", "hml", "rmw", "cma", "umd"]),
             ("FF6+STRev", ["mkt_rf", "smb", "hml", "rmw", "cma", "umd", "strev"])]
    rows = []
    for name, cols in rungs:
        df = pd.concat([y.rename("y"), F[cols]], axis=1).dropna() if cols \
            else y.dropna().to_frame("y")
        if len(df) < 24:
            continue
        if not cols:
            a = df["y"].mean()
            rows.append({"model": name, "alpha_mo": float(a),
                         "t_nw": nw_tstat(df["y"], lags=3), "n_mo": len(df)})
            continue
        X = np.column_stack([np.ones(len(df)), df[cols].values])
        beta, *_ = np.linalg.lstsq(X, df["y"].values, rcond=None)
        resid = df["y"].values - X @ beta
        rec = {"model": name, "alpha_mo": float(beta[0]),
               "t_nw": nw_tstat(pd.Series(resid + beta[0]), lags=3),
               "n_mo": len(df)}
        for c, b in zip(cols, beta[1:]):
            rec[f"b_{c}"] = float(b)
        rows.append(rec)
    return rows


def main() -> None:
    cmap, mdta = load_market()
    dates = mdta.prices.index
    ret = mdta.returns
    adv = mdta.dollar_volume.rolling(63, min_periods=20).median()

    qs = [q for q in pn.quarters()
          if pd.Timestamp("2013-06-30") <= q <= dates[-1] - pd.Timedelta(days=120)]
    memb = []
    for qi in range(1, len(qs)):
        p, p_prev = qs[qi], qs[qi - 1]
        dec = p + pd.Timedelta(days=45)
        nxt = (qs[qi + 1] + pd.Timedelta(days=45)) if qi + 1 < len(qs) else dates[-1]
        if dec >= dates[-1] - pd.Timedelta(days=30):
            continue
        cur = pn.snapshot_as_of(p, dec)
        prev = pn.snapshot_as_of(p_prev, dec)
        if min(len(cur), len(prev)) < 1000:
            continue
        di = dates.searchsorted(dec, side="right") - 1
        px = mdta.prices_raw.iloc[di]
        n_c = cur.groupby("instrument_id")["filer_id"].nunique()
        n_p = prev.groupby("instrument_id")["filer_id"].nunique()
        dbr = (n_c - n_p.reindex(n_c.index).fillna(0.0)) / float(
            cur["filer_id"].nunique())
        tick = dbr.index.to_series().map(cmap)
        s = dbr.groupby(tick).sum()
        s = s[px.reindex(s.index) >= 1.0].dropna()
        if len(s) < 300:
            continue
        q = pd.qcut(s.rank(method="first"), 5, labels=False) + 1
        memb.append((dec, min(nxt, dates[-1]),
                     q.index[q == 5], q.index[q == 1]))
        log(f"{p.date()} formed")

    rows, idx = [], []
    for dec, nxt, long_names, short_names in memb:
        i0 = dates.searchsorted(dec, side="right")
        i1 = dates.searchsorted(nxt, side="right") - 1
        w = ret.iloc[i0:i1 + 1]
        for mkey, wret in w.groupby(w.index.to_period("M")):
            idx.append(mkey.to_timestamp("M"))
            rows.append(float(wret[[c for c in long_names if c in wret]].sum().mean()
                              - wret[[c for c in short_names if c in wret]].sum().mean()))
    spread = pd.Series(rows, index=pd.DatetimeIndex(idx))
    spread = spread[~spread.index.duplicated(keep="first")].sort_index()

    F = pd.concat([kf_monthly("ff5"), kf_monthly("mom"), kf_monthly("strev")],
                  axis=1)
    res = pd.DataFrame(ladder(spread, F))
    res.to_csv(RESULTS / "confounder_ladder_dbreadth.csv", index=False)
    print("=== dBreadth Q5-Q1 EW mensal: escada de confounders ===")
    print(res.round(4).to_string(index=False))


if __name__ == "__main__":
    main()
