"""Heavy prep for analysis_v1.ipynb — run once, notebook reads the CSVs.

Pattern borrowed from the reference project: the notebook stays light and
re-runnable; everything that touches the 58M-row store lives here.

Every quarter is materialised through ``store.as_of(p, p + 70d)`` — a fixed
70-day vantage approximating what was knowable when a portfolio would be
formed (by day 70 ~95% of originals are in). Exploration-grade point in
time: the production path would use the activation calendar instead, but
nothing here peeks past the vantage.

Outputs (notebooks/data/):
    funds_per_quarter.csv     originals filed, distinct filers, entries/exits
    aum_per_quarter.csv       total/median/p90 13F equity book
    eligibility_per_quarter.csv  price-free eligibility waterfall
    imbalance_panel.csv.gz    per (quarter, instrument): TI, VI, n_active...
    imbalance_agg.csv         cross-sectional aggregates per quarter
    split_adjustments.csv     corporate-action ratios detected and applied
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "crowdflow" / "src"))

from crowdflow.curate.bitemporal import HoldingsStore  # noqa: E402

CURATED = ROOT / "crowdflow" / "data" / "20_curated"
OUT = Path(__file__).resolve().parent / "data"
OUT.mkdir(parents=True, exist_ok=True)

VANTAGE_DAYS = 70          # p + 70d: ~95% of originals are public
MIN_ACTIVE = 10            # paper's minimum-active-managers filter (their m)
SPLIT_MIN_HOLDERS = 10     # need this many common holders to infer a ratio
SPLIT_MODE_MASS = 0.10     # the modal exact ratio must carry >= 10% of holders
SPLIT_MIN_RATIO = 1.2      # modal ratio this far from 1 = corporate action


def log(msg: str) -> None:
    print(f"{time.strftime('%H:%M:%S')} - {msg}", flush=True)


def main() -> None:
    log("loading store (58M rows, a few minutes)...")
    holdings = pd.read_csv(
        CURATED / "holdings.csv.gz",
        usecols=["accession", "filer_id", "cik", "period_end", "instrument_id",
                 "shares", "value_usd", "put_call"],
    )
    revisions = pd.read_csv(CURATED / "revisions.csv.gz")
    store = HoldingsStore.build(holdings, revisions)
    del holdings
    log(f"store: {len(store.holdings):,} rows, {len(store.revisions):,} filings")

    ledger = pd.read_csv(
        CURATED / "ledger.csv.gz",
        usecols=["cik", "filer_id", "period_end", "form", "status", "filing_date"],
    )
    ledger["period_end"] = pd.to_datetime(ledger["period_end"])

    periods = sorted(
        p for p in store.revisions["period_end"].dt.normalize().unique()
        if pd.Timestamp("2013-06-30") <= p <= pd.Timestamp("2026-03-31")
        and pd.Timestamp(p).is_quarter_end
    )
    log(f"{len(periods)} quarters {periods[0].date()} -> {periods[-1].date()}")

    # ---- per-quarter views at the fixed vantage ------------------------- #
    funds_rows, aum_rows, elig_rows = [], [], []
    slim: dict[pd.Timestamp, pd.DataFrame] = {}
    history_count: dict[str, int] = {}

    for p in periods:
        v = store.as_of(p, p + pd.Timedelta(days=VANTAGE_DAYS))
        if v.empty:
            continue
        by_filer = v.groupby("filer_id")["value_usd"].agg(book="sum", top1="max")
        n_pos = v.groupby("filer_id")["instrument_id"].nunique()
        by_filer["n_pos"] = n_pos
        by_filer["top1_w"] = by_filer["top1"] / by_filer["book"]
        for f in by_filer.index:
            history_count[f] = history_count.get(f, 0) + 1
        by_filer["hist_q"] = pd.Series({f: history_count[f] for f in by_filer.index})

        funds_rows.append({
            "period_end": p,
            "filers_visible": len(by_filer),
            "originals_filed": int(
                ((ledger["period_end"] == p)
                 & (ledger["form"] == "13F-HR")
                 & (ledger["status"] != "no_table")).sum()),
        })
        aum_rows.append({
            "period_end": p,
            "total_book_usd": float(by_filer["book"].sum()),
            "median_book_usd": float(by_filer["book"].median()),
            "p90_book_usd": float(by_filer["book"].quantile(0.9)),
            "top10_share": float(by_filer["book"].nlargest(10).sum() / by_filer["book"].sum()),
        })
        elig_rows.append({
            "period_end": p,
            "all_filers": len(by_filer),
            "book_ge_500m": int((by_filer["book"] >= 5e8).sum()),
            "and_ge_15_pos": int(((by_filer["book"] >= 5e8) & (by_filer["n_pos"] >= 15)).sum()),
            "and_top1_le_60": int(((by_filer["book"] >= 5e8) & (by_filer["n_pos"] >= 15)
                                   & (by_filer["top1_w"] <= 0.60)).sum()),
            "and_hist_ge_4q": int(((by_filer["book"] >= 5e8) & (by_filer["n_pos"] >= 15)
                                   & (by_filer["top1_w"] <= 0.60) & (by_filer["hist_q"] >= 4)).sum()),
        })
        slim[p] = v[["cik", "filer_id", "instrument_id", "shares"]].copy()
        log(f"{p.date()}: {len(by_filer):,} filers, {len(v):,} positions")

    pd.DataFrame(funds_rows).to_csv(OUT / "funds_per_quarter.csv", index=False)
    pd.DataFrame(aum_rows).to_csv(OUT / "aum_per_quarter.csv", index=False)
    pd.DataFrame(elig_rows).to_csv(OUT / "eligibility_per_quarter.csv", index=False)

    # ---- imbalance panel (Miori & Cucuringu) --------------------------- #
    # Delta shares per (filer, stock) between consecutive quarters, only for
    # filers VISIBLE in both (else the delta measures filing churn, not
    # trading). Corporate actions: 13F share counts are as-filed, so a split
    # multiplies every holder's count by the same ratio and pushes TI/VI to
    # +1 for everyone at once - normalisation does NOT remove a shared sign.
    # With no vendor split file, the holders themselves are the detector -
    # but via the MODAL ATOM, not a tightness test. An untouched position's
    # ratio is EXACTLY the split factor; holders who also traded scatter
    # around it. On AAPL's 4:1 (2,745 common holders) the ratio IQR is 10% -
    # any dispersion gate fails - yet 16.6% of holders sit at exactly 4.00,
    # an atom that ordinary trading cannot produce: hundreds of independent
    # managers never land on the same exact non-unit ratio by choice.
    imb_rows, split_rows, imb_af_rows, imb_c6_rows = [], [], [], []
    for prev_p, p in zip(periods[:-1], periods[1:]):
        if prev_p not in slim or p not in slim:
            continue
        a_all, b_all = slim[prev_p], slim[p]
        common_filers = np.intersect1d(a_all["cik"].unique(), b_all["cik"].unique())
        a = a_all[a_all["cik"].isin(common_filers)]
        b = b_all[b_all["cik"].isin(common_filers)]
        m = a.merge(b, on=["cik", "instrument_id"], how="outer",
                    suffixes=("_prev", "_cur"))
        m[["shares_prev", "shares_cur"]] = m[["shares_prev", "shares_cur"]].fillna(0.0)

        # corporate-action ratio per instrument: the modal exact ratio.
        # Acceptance is mass OR dominance: in mega-held names most holders
        # trade every quarter, so the untouched-holder atom carries only
        # 5-9% of mass (AAPL 4:1: 167 of 2,745 holders at exactly 4.00) -
        # but it towers over the runner-up atom (3-11x). 30+ independent
        # managers on the same exact non-unit ratio cannot be trading.
        both = m[(m["shares_prev"] > 0) & (m["shares_cur"] > 0)].copy()
        both["r2"] = (both["shares_cur"] / both["shares_prev"]).round(2)
        counts = (both.groupby(["instrument_id", "r2"]).size().rename("k")
                  .reset_index().sort_values("k", ascending=False))
        top = counts.drop_duplicates("instrument_id").set_index("instrument_id")
        second = (counts[~counts.index.isin(counts.drop_duplicates("instrument_id").index)]
                  .drop_duplicates("instrument_id").set_index("instrument_id")["k"])
        n_holders = both.groupby("instrument_id").size().rename("n")
        top = top.join(n_holders).join(second.rename("k2")).fillna({"k2": 0})
        top["mass"] = top["k"] / top["n"]
        is_action = (top["r2"] >= SPLIT_MIN_RATIO) | (top["r2"] <= 1 / SPLIT_MIN_RATIO)
        strong = (top["mass"] >= SPLIT_MODE_MASS) | (
            (top["k"] >= 30) & (top["k"] >= 2.5 * top["k2"].clip(lower=1)))
        adj = top[(top["n"] >= SPLIT_MIN_HOLDERS) & is_action & strong]
        if len(adj):
            factor = m["instrument_id"].map(adj["r2"])
            m.loc[factor.notna(), "shares_prev"] = (
                m.loc[factor.notna(), "shares_prev"] * factor[factor.notna()])
            for iid, r in adj.iterrows():
                split_rows.append({"period_end": p, "instrument_id": iid,
                                   "ratio": float(r["r2"]), "n_holders": int(r["n"]),
                                   "modal_mass": float(round(r["mass"], 3))})

        m["delta"] = m["shares_cur"] - m["shares_prev"]
        act = m[m["delta"] != 0]
        buys = act[act["delta"] > 0].groupby("instrument_id")["delta"].agg(
            vol_buy="sum", n_buy="size")
        sells = act[act["delta"] < 0].groupby("instrument_id")["delta"].agg(
            vol_sell="sum", n_sell="size")
        s = buys.join(sells, how="outer").fillna(0.0)
        s["vol_sell"] = s["vol_sell"].abs()
        s["n_active"] = s["n_buy"] + s["n_sell"]
        s["ti"] = (s["n_buy"] - s["n_sell"]) / s["n_active"].replace(0, np.nan)
        s["vi"] = (s["vol_buy"] - s["vol_sell"]) / (s["vol_buy"] + s["vol_sell"]).replace(0, np.nan)
        s = s[s["n_active"] >= MIN_ACTIVE].reset_index()
        s["period_end"] = p
        imb_rows.append(s)

        # ---- all-filers variant (the paper's likely reading) ------------ #
        # No common-filer restriction: a filer's first quarter counts its
        # whole book as buys, its disappearance as a full sale. This mixes
        # filing churn into "trading" - which is why the main panel filters
        # it - but the paper's D matrices seem to include it, and the two
        # variants diverge most exactly where VI lives (entries and exits
        # are whole positions, dwarfing incremental deltas).
        m2 = a_all.merge(b_all, on=["cik", "instrument_id"], how="outer",
                         suffixes=("_prev", "_cur"))
        m2[["shares_prev", "shares_cur"]] = m2[["shares_prev", "shares_cur"]].fillna(0.0)
        if len(adj):
            factor2 = m2["instrument_id"].map(adj["r2"])
            m2.loc[factor2.notna(), "shares_prev"] = (
                m2.loc[factor2.notna(), "shares_prev"] * factor2[factor2.notna()])
        m2["delta"] = m2["shares_cur"] - m2["shares_prev"]
        act2 = m2[m2["delta"] != 0]
        b2 = act2[act2["delta"] > 0].groupby("instrument_id")["delta"].agg(vol_buy="sum", n_buy="size")
        s2_ = act2[act2["delta"] < 0].groupby("instrument_id")["delta"].agg(vol_sell="sum", n_sell="size")
        s2 = b2.join(s2_, how="outer").fillna(0.0)
        s2["vol_sell"] = s2["vol_sell"].abs()
        s2["n_active"] = s2["n_buy"] + s2["n_sell"]
        s2["ti"] = (s2["n_buy"] - s2["n_sell"]) / s2["n_active"].replace(0, np.nan)
        s2["vi"] = (s2["vol_buy"] - s2["vol_sell"]) / (s2["vol_buy"] + s2["vol_sell"]).replace(0, np.nan)
        s2 = s2[s2["n_active"] >= MIN_ACTIVE].reset_index()
        s2["period_end"] = p
        imb_af_rows.append(s2)

        # ---- paper full recipe: all-filers AND CUSIP6 (issuer) level ----- #
        # The paper aggregates share classes to CUSIP6 before computing
        # deltas (GOOG+GOOGL = one asset), on top of the all-filers deltas.
        m6 = m2.assign(c6=m2["instrument_id"].str.slice(0, 6))
        m6 = m6.groupby(["cik", "c6"], as_index=False)[["shares_prev", "shares_cur"]].sum()
        m6["delta"] = m6["shares_cur"] - m6["shares_prev"]
        act6 = m6[m6["delta"] != 0]
        b6 = act6[act6["delta"] > 0].groupby("c6")["delta"].agg(vol_buy="sum", n_buy="size")
        s6_ = act6[act6["delta"] < 0].groupby("c6")["delta"].agg(vol_sell="sum", n_sell="size")
        s6 = b6.join(s6_, how="outer").fillna(0.0)
        s6["vol_sell"] = s6["vol_sell"].abs()
        s6["n_active"] = s6["n_buy"] + s6["n_sell"]
        s6["ti"] = (s6["n_buy"] - s6["n_sell"]) / s6["n_active"].replace(0, np.nan)
        s6["vi"] = (s6["vol_buy"] - s6["vol_sell"]) / (s6["vol_buy"] + s6["vol_sell"]).replace(0, np.nan)
        s6 = s6[s6["n_active"] >= MIN_ACTIVE].reset_index().rename(columns={"c6": "instrument_id"})
        s6["period_end"] = p
        imb_c6_rows.append(s6)

        log(f"imbalance {p.date()}: {len(s):,} stocks with >= {MIN_ACTIVE} active managers, "
            f"{len(adj)} corporate-action ratios applied")
        del slim[prev_p]

    panel = pd.concat(imb_rows, ignore_index=True)
    panel.to_csv(OUT / "imbalance_panel.csv.gz", index=False)
    pd.concat(imb_af_rows, ignore_index=True).to_csv(
        OUT / "imbalance_panel_allfilers.csv.gz", index=False)
    pd.concat(imb_c6_rows, ignore_index=True).to_csv(
        OUT / "imbalance_panel_cusip6.csv.gz", index=False)
    pd.DataFrame(split_rows).to_csv(OUT / "split_adjustments.csv", index=False)

    agg = panel.groupby("period_end").agg(
        n_stocks=("instrument_id", "size"),
        ti_mean=("ti", "mean"), ti_median=("ti", "median"),
        vi_mean=("vi", "mean"),
        pct_ti_extreme=("ti", lambda s: float((s.abs() >= 0.5).mean())),
        n_active_median=("n_active", "median"),
    ).reset_index()
    agg.to_csv(OUT / "imbalance_agg.csv", index=False)
    log(f"panel: {len(panel):,} stock-quarters; done.")


if __name__ == "__main__":
    main()
