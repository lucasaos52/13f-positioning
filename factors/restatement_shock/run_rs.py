"""Restatement Shock (doc idea #1): does the market react when an amendment
publicly CHANGES the demand information of a prior 13F?

    python run_rs.py            # full sample
    python run_rs.py --smoke    # last ~12 quarters

CAUSAL CHAIN:
    original filing creates a public information state
      -> amendment (RESTATEMENT replaces the table; NEW HOLDINGS adds
         previously-confidential rows) changes that state at an exact,
         known timestamp
      -> copycats / believers update -> price reaction in the days after,
         IN THE DIRECTION of the correction, scaled by its size vs ADV.

This is the single best use of the project's structural advantage: the
curated base preserves filing VERSIONS, amendment semantics (crowdflow
invariants #2/#4) and real dates - the exact ingredients a calendar-grid
replication cannot have. Literature anchor: Cao-Da-Jiang-Yang (2026,
Management Science) documents 13F restatements as economically meaningful.

CONSTRUCTION. For each amendment accession of filer m, period p, filed at
date f: delta = new version table minus the immediately-prior version of
the same (filer, period) - full-table diff for RESTATEMENT (replacement
semantics), added-rows-only for NEW HOLDINGS (additive semantics). Every
changed ticker becomes an event-row with:
    dir      = sign of the share change
    mag      = |delta dollars| / ADV      (days-of-ADV of the correction)
    mat      = |delta dollars| / book     (materiality of the amendment)
    dirret_h = dir * (excess return over +h trading days from the close of
               the first trading day AFTER f)   - positive means the market
               moved in the direction of the correction.

PRE-REGISTERED:
    R1 dirret > 0 at +1/+3/+5 (market updates toward the correction);
    R2 monotone in mag terciles (price-pressure/attention channel);
    R3 immaterial amendments (mat < 0.5% of book) ~ 0 - the doc's
       administrative-amendment falsification;
    R4 placebo: same windows 5 trading days BEFORE f ~ 0 (the correction
       is not public yet);
    R5 NEW HOLDINGS reveals reported separately (Agarwal-type confidential
       reveals at the honest daily clock - our quarterly conf_reveal was
       too coarse).
Inference: quarter-clustered means, NW(4) - amendments cluster in time.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
for sub in ("", "general_plan"):
    sys.path.insert(0, str(HERE.parent / sub))

import panel as pn                                  # noqa: E402
from backtest_gp import nw_tstat                    # noqa: E402
from run_all import load_market, log                # noqa: E402

RESULTS = HERE / "results"
HORIZONS = [1, 3, 5, 10]
MAT_MIN = 0.005        # below this fraction of book = administrative
MIN_DOLLAR = 1e5       # ignore sub-$100k line noise


def main(smoke: bool = False) -> None:
    RESULTS.mkdir(exist_ok=True)
    cmap, mdta = load_market()
    dates = mdta.prices.index
    cum = mdta.returns.cumsum()
    adv = mdta.dollar_volume.rolling(63, min_periods=20).median()
    px_all = mdta.prices_raw
    meta = pd.read_parquet(pn.QDIR / "filings_meta.parquet")
    meta["filing_date"] = pd.to_datetime(meta["filing_date"])

    qs = [q for q in pn.quarters()
          if pd.Timestamp("2013-06-30") <= q <= dates[-1] - pd.Timedelta(days=40)]
    if smoke:
        qs = qs[-12:]
    log(f"{len(qs)} quarters")

    umed_cache: dict[tuple, float] = {}
    rows: list[dict] = []

    for q in qs:
        mq = meta[meta["period_end"] == q].copy()
        amds = mq[mq["is_amendment"]]
        if not len(amds):
            continue
        try:
            tab = pn._load_quarter(str(q)[:10])
        except Exception:
            continue
        tab = tab[tab["filer_id"].isin(amds["filer_id"].unique())]
        fdate = mq.set_index("accession")["filing_date"]
        atype = mq.set_index("accession")["amendment_type"] \
            if "amendment_type" in mq.columns else pd.Series(dtype=object)

        n_ev = 0
        for filer, g in tab.groupby("filer_id"):
            accs = (mq[mq["filer_id"] == filer]
                    .sort_values("filing_date")["accession"].tolist())
            if len(accs) < 2:
                continue
            versions = {a: g[g["accession"] == a] for a in accs
                        if len(g[g["accession"] == a])}
            for vi in range(1, len(accs)):
                a_new, a_old = accs[vi], accs[vi - 1]
                if a_new not in versions:
                    continue
                is_amd = bool(mq.set_index("accession")
                              .loc[a_new, "is_amendment"]) \
                    if a_new in mq["accession"].values else False
                if not is_amd:
                    continue
                f = fdate.get(a_new)
                if pd.isna(f):
                    continue
                ti0 = dates.searchsorted(f, side="right")
                if ti0 + 12 >= len(dates) or ti0 < 8:
                    continue
                new_t = versions[a_new].groupby("instrument_id")["shares"] \
                    .sum()
                kind = str(atype.get(a_new, "")).upper() \
                    if len(atype) else ""
                old_t = versions.get(a_old)
                if old_t is None or not len(old_t):
                    continue
                old_s = old_t.groupby("instrument_id")["shares"].sum()
                if "NEW HOLDINGS" in kind:
                    # additive: only rows absent from the prior version
                    add = new_t[~new_t.index.isin(old_s.index)]
                    delta = add
                else:
                    # replacement semantics: full-table diff
                    delta = new_t.sub(old_s, fill_value=0.0)
                    delta = delta[delta != 0]
                if not len(delta):
                    continue
                book = float(versions[a_new]["value_usd"].sum())
                if book <= 0:
                    continue
                di = min(ti0, len(dates) - 1)
                px_d = px_all.iloc[di]
                adv_d = adv.iloc[di]
                uni_ok = px_d >= 1.0
                for j, dsh in delta.items():
                    t = cmap.get(j)
                    if t is None or t not in cum.columns:
                        continue
                    p_t = px_d.get(t, np.nan)
                    a_t = adv_d.get(t, np.nan)
                    if not (np.isfinite(p_t) and p_t >= 1.0
                            and np.isfinite(a_t) and a_t > 0):
                        continue
                    dollar = dsh * p_t
                    if abs(dollar) < MIN_DOLLAR:
                        continue

                    def wret(i0, h):
                        return float(np.clip(
                            cum[t].iloc[i0 + h] - cum[t].iloc[i0],
                            -0.5, 0.5))

                    r = {"period": q, "filer": filer,
                         "ticker": t, "kind": ("NH" if "NEW HOLDINGS"
                                               in kind else "RS"),
                         "dir": float(np.sign(dsh)),
                         "mag": abs(dollar) / a_t,
                         "mat": abs(dollar) / book}
                    for h in HORIZONS:
                        key = (ti0, h)
                        if key not in umed_cache:
                            w = cum.iloc[ti0 + h] - cum.iloc[ti0]
                            umed_cache[key] = float(
                                w[uni_ok.reindex(w.index).fillna(False)]
                                .median())
                        r[f"dirret{h}"] = r["dir"] * (
                            wret(ti0, h) - umed_cache[key])
                        kb = (ti0 - 5, h)
                        if kb not in umed_cache:
                            w = cum.iloc[ti0 - 5 + h] - cum.iloc[ti0 - 5]
                            umed_cache[kb] = float(
                                w[uni_ok.reindex(w.index).fillna(False)]
                                .median())
                        r[f"pre{h}"] = r["dir"] * (
                            wret(ti0 - 5, h) - umed_cache[kb])
                    rows.append(r)
                    n_ev += 1
        log(f"{q.date()}: {n_ev} event-rows")

    ev = pd.DataFrame(rows)
    ev.to_csv(RESULTS / "rs_events.csv", index=False)

    L = ["# restatement_shock - o mercado reage a correcao publica?", "",
         "dirret = sinal da correcao x excesso vs mediana do universo, "
         "a partir do close do 1o pregao apos o amendment. Cluster por "
         "trimestre, NW(4).", ""]
    if len(ev):
        L.append(f"- {len(ev)} eventos-ticker | "
                 f"{ev['period'].nunique()} tri | RS: "
                 f"{(ev['kind'] == 'RS').sum()}, NH: "
                 f"{(ev['kind'] == 'NH').sum()}\n")
        mat_ok = ev["mat"] >= MAT_MIN
        for lbl, g in [("R1 RESTATEMENTS materiais (mat>=0.5% book)",
                        ev[(ev["kind"] == "RS") & mat_ok]),
                       ("R3 administrativos (mat<0.5%) - deve ser ~0",
                        ev[(ev["kind"] == "RS") & ~mat_ok]),
                       ("R5 NEW HOLDINGS reveals (confidenciais)",
                        ev[ev["kind"] == "NH"])]:
            if not len(g):
                continue
            L.append(f"## {lbl} ({len(g)} eventos)")
            qg = g.groupby("period")
            for h in HORIZONS:
                m = qg[f"dirret{h}"].mean()
                L.append(f"- dirret +{h}d: {g[f'dirret{h}'].mean():+.4f} "
                         f"(t={nw_tstat(m):+.2f})")
            for h in (3, 5):
                m = qg[f"pre{h}"].mean()
                L.append(f"- R4 placebo -5d, +{h}d: "
                         f"{g[f'pre{h}'].mean():+.4f} "
                         f"(t={nw_tstat(m):+.2f})")
            L.append("")
        g = ev[(ev["kind"] == "RS") & mat_ok].copy()
        if len(g) > 300:
            L.append("## R2 gradiente de magnitude (|corr|/ADV, "
                     "terciles por tri)")
            g["ter"] = g.groupby("period")["mag"].transform(
                lambda s: pd.qcut(s.rank(method="first"), 3, labels=False)
                if len(s) >= 6 else pd.Series(1, index=s.index))
            for h in (1, 3, 5):
                by = g.groupby(["period", "ter"])[f"dirret{h}"].mean() \
                    .unstack()
                if 2 in by.columns and 0 in by.columns:
                    d = (by[2] - by[0]).dropna()
                    L.append(f"- +{h}d T2-T0: {d.mean():+.4f} "
                             f"(t={nw_tstat(d):+.2f}) | terciles "
                             f"{by[0].mean():+.4f} / {by[1].mean():+.4f} "
                             f"/ {by[2].mean():+.4f}")
    (RESULTS / "RS_REPORT.md").write_text("\n".join(L), encoding="utf-8")
    log("done -> results/")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    main(**vars(ap.parse_args()))
