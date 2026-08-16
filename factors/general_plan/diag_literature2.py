"""Days-ADV quintiles scored the way the literature scores them: FF3 ALPHAS.

The published Days-ADV numbers (+0.54%/mo crowded, -0.90%/mo uncrowded,
spread 1.44%/mo t=9.67) are FACTOR ALPHAS of value-weighted quintiles, not
raw returns. Comparing raw quarterly spreads against them (diag_literature)
mixes the premium with the size/market loadings - and the loadings are the
story: Q1 is small-illiquid (huge SMB beta), Q5 is concentrated institutional
money. This script closes the gap:

  1. monthly EW and VW return series per raw-sort quintile (signal refreshed
     quarterly at D+45, held; monthly resolution for the regression);
  2. Fama-French factors downloaded from Ken French's library (free);
  3. alpha_FF3 per quintile and for the Q5-Q1 spread, with NW t-stats;
  4. quintile composition (median mktcap, median dollar ADV) so Q1/Q5 stop
     being abstractions.
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

import market_cap as mc               # noqa: E402
import panel as pn                    # noqa: E402
from backtest_gp import nw_tstat      # noqa: E402
from run_all import load_market, log  # noqa: E402

RESULTS = HERE / "results"
FF_URL = ("https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
          "F-F_Research_Data_Factors_CSV.zip")


def ff3_monthly() -> pd.DataFrame:
    cache = HERE / "data" / "ff3_monthly.csv"
    if cache.exists():
        return pd.read_csv(cache, index_col=0, parse_dates=True)
    raw = requests.get(FF_URL, timeout=60).content
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        txt = z.read(z.namelist()[0]).decode("latin-1")
    lines = txt.splitlines()
    start = next(i for i, l in enumerate(lines) if l.strip().startswith("19"))
    end = next(i for i in range(start, len(lines))
               if not lines[i].strip()[:6].isdigit())
    df = pd.read_csv(io.StringIO("\n".join(lines[start - 1:end])))
    df.columns = ["ym", "mkt_rf", "smb", "hml", "rf"]
    df["date"] = pd.to_datetime(df["ym"].astype(str), format="%Y%m") + pd.offsets.MonthEnd(0)
    df = df.set_index("date")[["mkt_rf", "smb", "hml", "rf"]] / 100.0
    df.to_csv(cache)
    return df


def alpha_ff3(monthly_ret: pd.Series, ff: pd.DataFrame) -> tuple[float, float]:
    df = pd.concat([monthly_ret.rename("r"), ff], axis=1).dropna()
    if len(df) < 24:
        return np.nan, np.nan
    y = df["r"] - df["rf"]
    X = np.column_stack([np.ones(len(df)), df[["mkt_rf", "smb", "hml"]].values])
    beta, *_ = np.linalg.lstsq(X, y.values, rcond=None)
    resid = y.values - X @ beta
    # NW(3) on the alpha
    e = resid + beta[0]                     # alpha + residual series
    return float(beta[0]), nw_tstat(pd.Series(e), lags=3)


def main() -> None:
    cmap, mdta = load_market()
    dates = mdta.prices.index
    ret = mdta.returns
    adv = mdta.dollar_volume.rolling(63, min_periods=20).median()
    shares = mc.shares_panel(dates, mdta.tickers, mdta.prices, mdta.prices_raw)
    mcap = mc.mktcap_panel(mdta.prices_raw, shares)

    qs = [q for q in pn.quarters()
          if pd.Timestamp("2013-06-30") <= q <= dates[-1] - pd.Timedelta(days=120)]

    # quintile membership per formation, then monthly returns
    memb: list[tuple[pd.Timestamp, pd.Timestamp, dict]] = []
    comp_rows = []
    for qi in range(len(qs)):
        p = qs[qi]
        dec = p + pd.Timedelta(days=45)
        nxt = (qs[qi + 1] + pd.Timedelta(days=45)) if qi + 1 < len(qs) else dates[-1]
        if dec >= dates[-1] - pd.Timedelta(days=30):
            continue
        cur = pn.snapshot_as_of(p, dec)
        if len(cur) < 1000:
            continue
        di = dates.searchsorted(dec, side="right") - 1
        adv_d, px = adv.iloc[di], mdta.prices_raw.iloc[di]
        mc_d = mcap.iloc[di] if len(mcap) else pd.Series(dtype=float)

        inst = cur.groupby("instrument_id")["value_usd"].sum()
        tick = inst.index.to_series().map(cmap)
        da = (inst / tick.map(adv_d)).groupby(tick).sum()
        da = da[(px.reindex(da.index) >= 1.0) & (da > 0)].replace(
            [np.inf, -np.inf], np.nan).dropna()
        if len(da) < 300:
            continue
        q = pd.qcut(da.rank(method="first"), 5, labels=False) + 1
        memb.append((dec, min(nxt, dates[-1]),
                     {k: q.index[q == k] for k in range(1, 6)}))
        for k in (1, 5):
            names = q.index[q == k]
            comp_rows.append({
                "period": p, "q": k, "n": len(names),
                "med_mktcap_musd": float(mc_d.reindex(names).median() / 1e6),
                "med_adv_musd": float(adv_d.reindex(names).median() / 1e6),
                "med_days_adv": float(da.reindex(names).median())})
        log(f"{p.date()} formed")

    # monthly series per quintile, EW and VW
    mret: dict[str, list] = {f"{w}_q{k}": [] for w in ("ew", "vw") for k in range(1, 6)}
    midx = []
    for dec, nxt, groups in memb:
        i0 = dates.searchsorted(dec, side="right")
        i1 = dates.searchsorted(nxt, side="right") - 1
        window = ret.iloc[i0:i1 + 1]
        if not len(window):
            continue
        months = window.groupby(window.index.to_period("M"))
        di = max(i0 - 1, 0)
        mc_d = mcap.iloc[di] if len(mcap) else pd.Series(dtype=float)
        for mkey, wret in months:
            midx.append(mkey.to_timestamp("M"))
            for k in range(1, 6):
                names = [n for n in groups[k] if n in wret.columns]
                r = wret[names].sum()                     # monthly sum of daily
                mret[f"ew_q{k}"].append(float(r.mean()))
                w = mc_d.reindex(names).fillna(0.0)
                mret[f"vw_q{k}"].append(
                    float(np.average(r, weights=w)) if w.sum() > 0 else np.nan)

    panel_m = pd.DataFrame(mret, index=pd.DatetimeIndex(midx))
    panel_m = panel_m[~panel_m.index.duplicated(keep="first")].sort_index()
    ff = ff3_monthly()

    rows = []
    for w in ("ew", "vw"):
        for k in range(1, 6):
            a, t = alpha_ff3(panel_m[f"{w}_q{k}"], ff)
            rows.append({"weight": w, "leg": f"q{k}",
                         "alpha_ff3_mo": a, "t": t,
                         "raw_mo": float(panel_m[f"{w}_q{k}"].mean())})
        spread = panel_m[f"{w}_q5"] - panel_m[f"{w}_q1"]
        a, t = alpha_ff3(spread + ff["rf"].reindex(panel_m.index).fillna(0.0), ff)
        rows.append({"weight": w, "leg": "q5-q1",
                     "alpha_ff3_mo": a, "t": t, "raw_mo": float(spread.mean())})
    res = pd.DataFrame(rows)
    res.to_csv(RESULTS / "literature_ff3_alphas.csv", index=False)
    comp = pd.DataFrame(comp_rows).groupby("q")[
        ["n", "med_mktcap_musd", "med_adv_musd", "med_days_adv"]].median()
    comp.to_csv(RESULTS / "literature_composition.csv")
    print("=== composicao mediana dos quintis (Q1 vs Q5) ===")
    print(comp.round(1).to_string())
    print("\n=== alfas FF3 mensais (publicado: q1 -0.90%, q5 +0.54%, spread 1.44% t=9.67) ===")
    print(res.round(4).to_string(index=False))


if __name__ == "__main__":
    main()
