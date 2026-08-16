"""ML positioning factor: predict the size-residualized forward excess
return from the CHANGE/ACTION variables of the 13F catalogue, and treat
the prediction as a new stock-level factor.

    python run_ml.py                # full walk-forward (uses panel cache)
    python run_ml.py --rebuild      # force panel rebuild

DESIGN, mirroring the user's tabular-ML notebook practices
("tabular ML - refactor - V4_V22"):
  preprocessing  per-quarter cross-sectional winsorize (1-99%) -> z-score
                 -> clip +-8 (their winsorize_and_zscore_by_universe);
                 median imputation (z-space median ~ 0)
  target         forward quarterly return -> cross-sectional excess ->
                 residualized on log(mktcap) (the size adjustment asked
                 for) -> cross-sectional RANK Z-SCORE, clip +-8 (their
                 precomputed_excess_rank_zscore target)
  models         an architecture race with a comparison table (their
                 run_all_models pattern): ridge / knn / hist-gradient
                 boosting (sklearn's LightGBM stand-in; no lightgbm in
                 this venv) / random forest / rank-ensemble of the four
  validation     STRICTLY EXPANDING walk-forward by quarter (train on
                 quarters < t, predict t), 12-quarter warm-up - the
                 project's OOS protocol, which is the panel analogue of
                 their trade_lag/no-leak discipline
  no vol weighting (per instruction) - plain EW quintiles as everywhere
                 else in the project

FEATURES - change/action variables only (the family the research says
carries the information; levels excluded by Law 1):
  new_conviction, dbreadth, dbreadth_common, entry_rate, exit_rate,
  net_entry, dio, dio_2q, d_days_adv, ti, vi, late_minus_early_dio

EVALUATION AS A FACTOR: the OOS prediction is ranked into EW quintiles
each quarter; spread on the RAW forward return (comparable with every
catalogue signal) and on the size-residualized forward return (the
object the model was trained on). NW(4) t, Sharpe, Spearman IC.

PRE-REGISTERED HONESTY CLAUSE: this is a post-hoc exploratory study on
the candidate track (architectures raced, no fresh sample). The gates
that matter, fixed before running: (G1) does any architecture beat the
best single change-signal (champion alone, t~+3.5, Sharpe ~1.05) on the
same quarters? (G2) does the nonlinear family beat ridge (the FM-like
linear baseline) - i.e., is there NONLINEAR information in the change
variables? If G2 fails, the FM/score model already extracts what exists
and the right conclusion is "no nonlinear premium", not a new factor.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sps

HERE = Path(__file__).resolve().parent
for sub in ("general_predictive_signals", "general_plan"):
    sys.path.insert(0, str(HERE.parent / sub))

import market_cap as mc                             # noqa: E402
import panel as pn                                  # noqa: E402
from backtest_gp import forward_return, nw_tstat    # noqa: E402
from run_all import load_market, log                # noqa: E402
from signal_defs import build_all                   # noqa: E402

from sklearn.ensemble import (                      # noqa: E402
    HistGradientBoostingRegressor, RandomForestRegressor)
from sklearn.inspection import permutation_importance  # noqa: E402
from sklearn.linear_model import Ridge              # noqa: E402
from sklearn.neighbors import KNeighborsRegressor   # noqa: E402

RESULTS = HERE / "results"
PANEL_CACHE = RESULTS / "ml_panel.parquet"
LAG = 45
EARLY_CUT = 40
MIN_HIST = 12
FEATURES = ["new_conviction", "dbreadth", "dbreadth_common", "entry_rate",
            "exit_rate", "net_entry", "dio", "dio_2q", "d_days_adv",
            "ti", "vi", "late_minus_early_dio"]


def winsor_z(s: pd.Series, clip: float = 8.0) -> pd.Series:
    """The notebook's winsorize(1-99%) + cross-sectional z + clip."""
    s = s.replace([np.inf, -np.inf], np.nan)
    lo, hi = s.quantile(0.01), s.quantile(0.99)
    s = s.clip(lo, hi)
    sd = s.std(ddof=1)
    if not np.isfinite(sd) or sd == 0:
        return s * 0.0
    return ((s - s.mean()) / sd).clip(-clip, clip)


def rank_z(s: pd.Series, clip: float = 8.0) -> pd.Series:
    """The notebook's cross-sectional rank z-score target."""
    r = s.rank(pct=True)
    z = pd.Series(sps.norm.ppf(r.clip(1e-6, 1 - 1e-6)), index=s.index)
    return z.clip(-clip, clip)


def residualise(y: pd.Series, X: pd.DataFrame) -> pd.Series:
    df = pd.concat([y.rename("y"), X], axis=1).replace(
        [np.inf, -np.inf], np.nan)
    ok = df.notna().all(axis=1)
    if ok.sum() < 30:
        return y - y.mean()
    A = np.column_stack([np.ones(ok.sum()), df.loc[ok, X.columns].values])
    b, *_ = np.linalg.lstsq(A, df.loc[ok, "y"].values, rcond=None)
    r = y.copy()
    r[ok] = df.loc[ok, "y"].values - A @ b
    r[~ok] = np.nan
    return r


def build_panel() -> pd.DataFrame:
    """Quarterly stacked frame: period, ticker, 12 features (winsor-z),
    fwd_raw, fwd_resid (size-residualized), y (rank-z of fwd_resid)."""
    cmap, mdta = load_market()
    dates = mdta.prices.index
    cum = mdta.returns.cumsum()
    adv = mdta.dollar_volume.rolling(63, min_periods=20).median()
    shares = mc.shares_panel(dates, mdta.tickers, mdta.prices,
                             mdta.prices_raw)
    mcap = mc.mktcap_panel(mdta.prices_raw, shares)
    meta = pd.read_parquet(pn.QDIR / "filings_meta.parquet")
    cmap_s = pd.Series(cmap)

    qs = [q for q in pn.quarters()
          if pd.Timestamp("2013-06-30") <= q
          <= dates[-1] - pd.Timedelta(days=120)]
    rows = []
    for qi in range(2, len(qs)):
        p, p1, p2 = qs[qi], qs[qi - 1], qs[qi - 2]
        dec = p + pd.Timedelta(days=LAG)
        if dec >= dates[-1] - pd.Timedelta(days=95):
            continue
        cur = pn.snapshot_as_of(p, dec)
        prev = pn.snapshot_as_of(p1, dec)
        prev2 = pn.snapshot_as_of(p2, dec)
        if min(len(cur), len(prev)) < 1000:
            continue
        di = dates.searchsorted(dec, side="right") - 1
        di_p = dates.searchsorted(p, side="right") - 1
        di_p1 = dates.searchsorted(p1, side="right") - 1
        di_p2 = dates.searchsorted(p2, side="right") - 1
        px, adv_d = mdta.prices_raw.iloc[di], adv.iloc[di]
        mc_d = mcap.iloc[di]

        def so_at(dix):
            row = shares.iloc[dix] if len(shares) else pd.Series(dtype=float)
            return pd.Series(cmap_s.map(row).values, index=cmap_s.index)

        orig = meta[(meta["period_end"] == p) & (~meta["is_amendment"])]
        early = set(orig.loc[orig["filing_date"]
                             <= p + pd.Timedelta(days=EARLY_CUT), "filer_id"])

        pair = cur.merge(prev, on=["filer_id", "instrument_id"],
                         suffixes=("_c", "_p"))
        pair = pair[(pair["shares_p"] > 0) & (pair["shares_c"] > 0)]
        pair["ratio"] = (pair["shares_c"] / pair["shares_p"]).round(3)
        fac_map = {}
        for j, g in pair.groupby("instrument_id"):
            if len(g) < 10:
                continue
            counts = g["ratio"].value_counts()
            mode, k = counts.index[0], counts.iloc[0]
            k2 = counts.iloc[1] if len(counts) > 1 else 0
            if abs(mode - 1) > 0.15 and (k >= 0.10 * len(g)
                                         or (k >= 30 and k >= 2.5 * k2)):
                fac_map[j] = float(mode)

        sig = build_all(cur, prev, prev2, so_at(di_p), so_at(di_p1),
                        so_at(di_p2), early, pd.Index([]),
                        split_fac=pd.Series(fac_map, dtype=float))
        t = sig.index.to_series().map(cmap)
        adv_i = t.map(adv_d)
        sig["days_adv"] = sig.pop("inst_value") / adv_i
        sig["d_days_adv"] = (sig["days_adv"]
                             - sig.pop("inst_value_prev") / adv_i)
        sig["ticker"] = t
        sig = sig.dropna(subset=["ticker"])
        agg = {n: ("mean" if n in ("ti", "vi") else "sum")
               for n in FEATURES}
        byt = sig.groupby("ticker").agg(agg)
        byt = byt.loc[px.reindex(byt.index) >= 1.0]

        nxt = qs[qi + 1] + pd.Timedelta(days=LAG) if qi + 1 < len(qs) \
            else dates[-1]
        fwd = forward_return(cum, dates, dec,
                            min(nxt, dates[-1])).reindex(byt.index)
        fwd = fwd - fwd.mean()                       # cross-sectional excess
        lm = pd.Series(np.log(mc_d.reindex(byt.index)), index=byt.index)
        fwd_res = residualise(fwd, lm.to_frame("lm"))

        out = pd.DataFrame({"period": p, "ticker": byt.index})
        for f in FEATURES:
            out[f] = winsor_z(byt[f]).values
        out["fwd_raw"] = fwd.values
        out["fwd_resid"] = fwd_res.values
        out["y"] = rank_z(fwd_res).values
        rows.append(out.dropna(subset=["fwd_raw"]))
        log(f"{p.date()}: {len(out)} names")
    return pd.concat(rows, ignore_index=True)


def make_models():
    return {
        "ridge": Ridge(alpha=10.0),
        "knn": KNeighborsRegressor(n_neighbors=200, weights="distance",
                                   n_jobs=-1),
        "hgb": HistGradientBoostingRegressor(
            max_iter=300, learning_rate=0.05, max_leaf_nodes=31,
            l2_regularization=1.0, min_samples_leaf=100, random_state=7),
        "rf": RandomForestRegressor(
            n_estimators=300, max_depth=8, min_samples_leaf=50,
            max_features=0.5, random_state=7, n_jobs=-1),
    }


def main(rebuild: bool = False) -> None:
    RESULTS.mkdir(exist_ok=True)
    if PANEL_CACHE.exists() and not rebuild:
        P = pd.read_parquet(PANEL_CACHE)
        log(f"panel cache: {len(P)} rows")
    else:
        P = build_panel()
        P.to_parquet(PANEL_CACHE)
        log(f"panel built: {len(P)} rows -> cache")
    P["period"] = pd.to_datetime(P["period"])
    periods = sorted(P["period"].unique())
    log(f"{len(periods)} quarters, features: {FEATURES}")

    names = list(make_models()) + ["ens"]
    ev: dict[str, list] = {n: [] for n in names}
    imp_acc = []
    for ti in range(MIN_HIST, len(periods)):
        p = periods[ti]
        tr = P[P["period"] < p].dropna(subset=FEATURES + ["y"])
        te = P[P["period"] == p].dropna(subset=FEATURES)
        if len(tr) < 5000 or len(te) < 300:
            continue
        Xtr = tr[FEATURES].fillna(0.0).values
        ytr = tr["y"].values
        Xte = te[FEATURES].fillna(0.0).values
        preds = {}
        for nm, mdl in make_models().items():
            mdl.fit(Xtr, ytr)
            preds[nm] = pd.Series(mdl.predict(Xte), index=te.index)
            if nm == "hgb" and ti == len(periods) - 1:
                pi = permutation_importance(
                    mdl, Xte, te["y"].fillna(0.0).values,
                    n_repeats=5, random_state=7)
                imp_acc.append(pd.Series(pi.importances_mean,
                                         index=FEATURES))
        preds["ens"] = sum(s.rank(pct=True) for s in preds.values()) / 4
        rng = np.random.default_rng(int(pd.Timestamp(p).value) % (2**32))
        jit = rng.uniform(0, 1e-9, len(te))
        for nm, pr in preds.items():
            df = pd.DataFrame({
                "s": pr.values + jit, "fr": te["fwd_raw"].values,
                "fx": te["fwd_resid"].values}).dropna()
            q5 = pd.qcut(df["s"].rank(), 5, labels=False)
            g_r = df.groupby(q5)["fr"].mean()
            g_x = df.groupby(q5)["fx"].mean()
            ev[nm].append({
                "period": p,
                "spread_raw": g_r.get(4, np.nan) - g_r.get(0, np.nan),
                "spread_resid": g_x.get(4, np.nan) - g_x.get(0, np.nan),
                "ic": sps.spearmanr(df["s"], df["fr"])[0]})
        log(f"OOS {pd.Timestamp(p).date()}: "
            + " ".join(f"{nm} {ev[nm][-1]['spread_raw']:+.3f}"
                       for nm in names))

    # ---- report ------------------------------------------------------- #
    L = ["# ml_positioning - predicted size-residualized excess return "
         "from the 12 change variables", "",
         f"- walk-forward expanding, {MIN_HIST}q warm-up; features "
         f"winsor-z per quarter; target rank-z of size-residualized "
         f"forward excess (notebook practices); no vol weighting", "",
         "| model | spread raw/q (t) | Sharpe | spread resid/q (t) | "
         "IC |", "|---|---|---|---|---|"]
    tab = {}
    for nm in names:
        e = pd.DataFrame(ev[nm])
        e.to_csv(RESULTS / f"ml_events_{nm}.csv", index=False)
        sr, sx = e["spread_raw"], e["spread_resid"]
        tab[nm] = dict(t_raw=nw_tstat(sr),
                       sharpe=sr.mean() / sr.std() * 2)
        L.append(f"| {nm} | {sr.mean():+.4f} ({nw_tstat(sr):+.2f}) | "
                 f"{sr.mean() / sr.std() * 2:+.2f} | "
                 f"{sx.mean():+.4f} ({nw_tstat(sx):+.2f}) | "
                 f"{e['ic'].mean():+.4f} |")
    # paired deltas: nonlinear vs ridge, best vs ens
    er = pd.DataFrame(ev["ridge"]).set_index("period")["spread_raw"]
    L += ["", "## Gates", ""]
    for nm in ["hgb", "rf", "knn", "ens"]:
        en = pd.DataFrame(ev[nm]).set_index("period")["spread_raw"]
        d = (en - er).dropna()
        L.append(f"- G2 {nm} vs ridge (nonlinear info?): "
                 f"{d.mean():+.4f}/q (t={nw_tstat(d):+.2f})")
    L += ["- G1 reference: champion alone t~+3.5, Sharpe ~1.05 on this "
          "protocol; FM combiner Sharpe 0.86 (10 predictors incl. "
          "classical)", ""]
    if imp_acc:
        imp = imp_acc[0].sort_values(ascending=False)
        L += ["## HGB permutation importance (last OOS quarter)", ""]
        L += [f"- {k}: {v:+.4f}" for k, v in imp.items()]
    (RESULTS / "ML_REPORT.md").write_text("\n".join(L), encoding="utf-8")
    log("done -> results/")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true")
    main(**vars(ap.parse_args()))
