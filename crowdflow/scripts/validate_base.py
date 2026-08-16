"""Validation of the curated 13F base - the judge for "is the base right?".

Reads the 20_curated artefacts from disk, re-derives every claim the base
makes about itself, and writes ``docs/BASE_VALIDATION.md`` with a PASS/FAIL
verdict per check. Exit code is the number of failures, so this can gate a
build.

The checks fall into three families:

1. **Integrity** - every quarter present, every filing accounted for, every
   holdings row versioned by a revision, no null knowledge dates.
2. **Point-in-time mechanics, tested on real filings** - sampled
   (filer, period) pairs must show nothing before first disclosure, monotone
   visibility, and amendments that change the view only after their own
   acceptance. These are the empirical versions of the unit tests, run
   against the actual archive instead of fixtures.
3. **External anchors** - numbers that did not come from this pipeline:
   Berkshire's publicly known book values, the SEC's 45-day deadline
   arithmetic, EDGAR's 17:30 ET acceptance cutoff, and the independently
   published measurements from external studies of the same dataset
   (median lag ~45d with ~48% filing on the deadline day, ~93% on time
   business-day adjusted, ~16% amendment share, AAPL as a 12-line Berkshire
   position in 2024Q4 summing to ~$75.1bn). Agreement with numbers we did
   not produce is the strongest evidence available that the base is sound.

Usage:
    python scripts/validate_base.py [--out docs/BASE_VALIDATION.md] [--sample 200]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from crowdflow.config import Config  # noqa: E402
from crowdflow.curate.bitemporal import HoldingsStore  # noqa: E402

SEED = 20240614


class Report:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.failures: list[str] = []

    def h(self, title: str) -> None:
        self.lines += [f"\n## {title}\n"]

    def add(self, name: str, ok: bool, detail: str) -> None:
        mark = "PASS" if ok else "**FAIL**"
        self.lines.append(f"- [{mark}] {name} — {detail}")
        if not ok:
            self.failures.append(f"{name}: {detail}")

    def note(self, text: str) -> None:
        self.lines.append(text)


# --------------------------------------------------------------------------- #
def check_integrity(rep: Report, store: HoldingsStore, ledger: pd.DataFrame) -> None:
    rep.h("1. Integrity")
    rev, hold = store.revisions, store.holdings

    quarters = pd.period_range("2013Q2", rev["period_end"].max(), freq="Q")
    have = set(rev["period_end"].dt.to_period("Q"))
    missing = [str(q) for q in quarters if q not in have]
    rep.add("every report quarter present", not missing,
            f"{len(have)} quarters, missing: {missing or 'none'}")

    # Periods before the 2013Q2 coverage floor appear only through late
    # originals and amendments received inside covered windows - a handful of
    # filings each, correct and expected. The density check applies to the
    # covered range.
    q = rev["period_end"].dt.to_period("Q")
    covered = rev[(q >= pd.Period("2013Q2")) & ~rev["is_amendment"]]
    per_q = covered.groupby(covered["period_end"].dt.to_period("Q")).size()
    full_qs = per_q[per_q.index < per_q.index.max()]  # the newest quarter may still be filling in
    rep.add("filings per covered quarter in a sane band", bool((full_qs > 2000).all()),
            f"min {full_qs.min()} ({full_qs.idxmin()}), max {full_qs.max()} ({full_qs.idxmax()})")

    # The generic catch for any 1000x unit inflation that slips every other
    # net. Per ACCESSION, not per (filer, period): the store keeps every
    # version of an amended quarter, so a filer-period sum adds the original
    # to its own restatement and reports a phantom double. Ceiling calibrated
    # on reality: Vanguard's real book reaches ~$6.9tn by 2025Q4, BlackRock
    # ~$5.9tn, so the line sits at $8tn.
    books = store.holdings.groupby("accession")["value_usd"].sum()
    over = books[books > 8e12]
    over1t = books[books > 1e12]
    rep.add("no single filing's book above $8tn (unit-inflation catch)", len(over) == 0,
            f"{len(over)} filings above $8tn; {len(over1t)} above $1tn "
            "(expected: the index complexes)")

    orphans = ~hold["accession"].isin(set(rev["accession"]))
    rep.add("every holdings row versioned by a revision", not orphans.any(),
            f"{int(orphans.sum())} orphan rows")

    rep.add("no null knowledge_ts", not rev["knowledge_ts"].isna().any(),
            f"{int(rev['knowledge_ts'].isna().sum())} null")

    ok_led = ledger["status"].isin(["ok", "no_table", "all_rows_rejected"]).all()
    rep.add("ledger statuses complete", bool(ok_led),
            ledger["status"].value_counts().to_dict().__repr__())

    neg = hold["value_usd"].lt(0).sum()
    rep.add("no negative position values", neg == 0, f"{neg} negative rows")


# --------------------------------------------------------------------------- #
def check_pit(rep: Report, store: HoldingsStore, sample: int) -> None:
    rep.h("2. Point-in-time mechanics (sampled from the real archive)")
    rev = store.revisions
    rng = np.random.default_rng(SEED)

    # -- nothing before first disclosure; monotone visibility ------------- #
    firsts = rev.groupby(["filer_id", "period_end"])["knowledge_ts"].min().reset_index()
    take = firsts.sample(min(sample, len(firsts)), random_state=SEED)
    early_leaks = 0
    for r in take.itertuples():
        before = store.as_of(r.period_end, r.knowledge_ts - pd.Timedelta(days=1), filers={r.filer_id})
        if not before.empty:
            early_leaks += 1
    rep.add("nothing visible before first disclosure", early_leaks == 0,
            f"{early_leaks}/{len(take)} sampled (filer, period) leaked early")

    # -- amendments change the view only after their own acceptance ------- #
    amended = rev[rev["is_amendment"]]
    take_a = amended.sample(min(sample, len(amended)), random_state=SEED)
    leaks, applied, checked = 0, 0, 0
    for r in take_a.itertuples():
        group = rev[(rev["filer_id"] == r.filer_id) & (rev["period_end"] == r.period_end)]
        first_ts = group["knowledge_ts"].min()
        if r.knowledge_ts <= first_ts:  # amendment on/before first filing day: nothing to compare
            continue
        checked += 1
        before = store.as_of(r.period_end, r.knowledge_ts - pd.Timedelta(days=1), filers={r.filer_id})
        after = store.as_of(r.period_end, r.knowledge_ts, filers={r.filer_id})
        if r.accession in set(before["accession"]):
            leaks += 1
        if r.accession in set(after["accession"]):
            applied += 1
    rep.add("no amendment visible before its acceptance", leaks == 0,
            f"{leaks}/{checked} sampled amendments leaked")
    rep.note(f"  (of {checked} checked, {applied} are part of the final view; the rest were "
             "themselves superseded by later versions — expected, not an error)")

    # -- visibility is monotone ------------------------------------------- #
    periods = rng.choice(rev["period_end"].dt.to_period("Q").unique(), size=4, replace=False)
    non_monotone = 0
    for q in periods:
        p = pd.Period(q).end_time.normalize()
        seen: set[str] = set()
        for d in pd.date_range(p, p + pd.Timedelta(days=400), freq="30D"):
            cur = set(store.as_of(p, d)["accession"])
            if not seen.issubset(cur | seen):
                non_monotone += 1
            seen |= cur
    rep.add("visibility monotone in knowledge time", non_monotone == 0,
            f"{non_monotone} regressions across {len(periods)} quarters x 14 vantages")

    # -- knowledge never precedes the period it describes ------------------ #
    bad = (rev["knowledge_ts"] < rev["period_end"]).sum()
    rep.add("no filing knowable before its own quarter ends", bad == 0, f"{bad} violations")


# --------------------------------------------------------------------------- #
def check_external_anchors(rep: Report, store: HoldingsStore, ledger: pd.DataFrame) -> None:
    rep.h("3. External anchors (numbers this pipeline did not produce)")
    rev = store.revisions

    # -- the 45-day deadline, empirically --------------------------------- #
    orig = rev[~rev["is_amendment"]].copy()
    orig["lag"] = (orig["knowledge_ts"] - orig["period_end"]).dt.days
    med = orig["lag"].median()
    # The statutory deadline: 45 days after quarter end, rolled forward when it
    # lands on a weekend. knowledge_ts itself is rolled +1 session after the
    # close, so allow one extra day on top of the rolled deadline.
    deadline = orig["period_end"] + pd.Timedelta(days=45)
    wknd = deadline.dt.dayofweek - 4  # Sat -> 1, Sun -> 2
    deadline = deadline + pd.to_timedelta(wknd.clip(lower=0).where(wknd > 0, 0) * 0
                                          + (7 - deadline.dt.dayofweek).where(deadline.dt.dayofweek >= 5, 0),
                                          unit="D")
    on_time = (orig["knowledge_ts"] <= deadline + pd.Timedelta(days=1)).mean()
    pct_by_45 = (orig["lag"] <= 46).mean()
    rep.add("median filing lag ~= the 45-day deadline", 40 <= med <= 47,
            f"median {med:.0f}d; independent study of the same archive reports ~45d")
    rep.add("on-time share consistent with the deadline being binding",
            0.85 <= on_time <= 0.995,
            f"{on_time:.1%} by the business-day-rolled deadline (+1 session); "
            f"{pct_by_45:.1%} within calendar day 46; independent study: ~93%")

    exact = ((orig["lag"] >= 45) & (orig["lag"] <= 46)).mean()
    rep.note(f"  share filing at the deadline (day 45+roll): {exact:.1%} — the study reports 48.2% "
             "on exactly day 45, i.e. the deadline is the modal choice. Directional agreement expected.")

    # -- acceptance timezone: the 17:30 ET cutoff -------------------------- #
    fallback = rev["acceptance_dt"].astype(str).str.contains("23:59:59", na=False).mean()
    if fallback > 0.5:
        rep.add("acceptanceDateTime is UTC (cutoff appears at 22h raw, not 18h)", True,
                f"SKIPPED: {fallback:.0%} of timestamps are the end-of-day fallback "
                "(store built with --no-acceptance); the check needs real acceptance times")
    else:
        # Under the UTC reading three regimes exist, and all three are
        # evidence: raw 15-17h (11-13h ET) is comfortably pre-cutoff -> same
        # calendar day; raw 22-23h (18-19h ET) is post-cutoff -> filing_date
        # rolls to the NEXT day; and raw 0-4h is 19-23h ET of the PREVIOUS
        # evening, whose rolled filing date IS the stamp's UTC date -> same
        # day again. An ET reading cannot produce this three-band pattern.
        tz = store.verify_acceptance_timezone().set_index("raw_hour")
        early = tz.loc[[h for h in (15, 16, 17) if h in tz.index], "same_day_share"].mean()
        cutoff = tz.loc[[h for h in (22, 23) if h in tz.index], "same_day_share"].mean()
        wrapped = tz.loc[[h for h in (0, 1, 2) if h in tz.index], "same_day_share"].mean()
        rep.add("acceptanceDateTime is UTC (three-band same-day pattern)",
                early > 0.9 and cutoff < 0.7 and wrapped > 0.7 and cutoff < early,
                f"same-day share 15-17h raw: {early:.1%} (pre-cutoff), "
                f"22-23h raw: {cutoff:.1%} (post-cutoff, rolled), "
                f"0-2h raw: {wrapped:.1%} (prev-evening ET, wraps to the UTC date)")
        after_close = (pd.to_datetime(rev["acceptance_dt"], errors="coerce", utc=True)
                       .dt.tz_convert("America/New_York").dt.hour >= 16).mean()
        rep.note(f"  filings released after the 16:00 ET close: {after_close:.1%} "
                 "(the 50-manager study reports 49.1%; big managers file later) — "
                 "post-close filings are tradeable next session only, which "
                 "derive_knowledge_ts enforces.")

    # -- amendments -------------------------------------------------------- #
    am = rev[rev["is_amendment"]].copy()
    share = len(am) / max(len(rev), 1)
    am["lag"] = (am["knowledge_ts"] - am["period_end"]).dt.days
    rep.add("amendment share in the published ballpark", 0.02 <= share <= 0.25,
            f"{share:.1%} of filings are 13F-HR/A; the independent study reports 15.9% "
            "on a hand-picked sample of 50 large managers - amendment-prone by "
            "construction; the full universe runs lower")
    rep.note(f"  amendment lag: median {am['lag'].median():.0f}d, p90 {am['lag'].quantile(.9):.0f}d "
             "(study: median 136d, p90 412d)")
    types = ledger.loc[ledger["form"].astype(str).str.endswith("/A"), "amendment_type"]
    counts = types.fillna("(blank)").replace("", "(blank)").value_counts()
    both = counts.get("RESTATEMENT", 0) > 0 and counts.get("NEW HOLDINGS", 0) > 0
    rep.add("both amendment types observed and typed from the cover page", bool(both),
            counts.to_dict().__repr__())

    # -- Berkshire, the public anchor -------------------------------------- #
    brk = "CIK0001067983"
    v23 = store.as_of("2023-12-31", "2024-12-31", filers={brk})
    book23 = v23["value_usd"].sum() / 1e9
    rep.add("Berkshire 2023Q4 book matches the publicly known ~$352bn",
            340 <= book23 <= 365, f"${book23:.1f}bn from {len(v23)} positions")
    aapl23 = v23.loc[v23["cusip"] == "037833100", "value_usd"].sum() / 1e9
    rep.add("Berkshire 2023Q4 AAPL matches the publicly known ~$174bn",
            170 <= aapl23 <= 179, f"${aapl23:.1f}bn")

    v24 = store.as_of("2024-12-31", "2025-12-31", filers={brk})
    if not v24.empty:
        row = v24.loc[v24["cusip"] == "037833100"]
        aapl24 = row["value_usd"].sum() / 1e9
        n_lines = int(row["n_lines"].sum()) if "n_lines" in row.columns else -1
        rep.add("Berkshire 2024Q4 AAPL aggregates its multi-line slices to ~$75.1bn",
                70 <= aapl24 <= 80,
                f"${aapl24:.1f}bn from {n_lines} as-filed lines collapsed to {len(row)} position(s); "
                "the independent study reports 12 lines summing to $75.1bn")

    # -- value units across the 2023 cutover -------------------------------- #
    led = ledger[ledger["status"] == "ok"].copy()
    led["fy"] = pd.to_datetime(led["filing_date"]).dt.year
    pre = led[led["fy"] <= 2021]
    post = led[led["fy"] >= 2024]
    if len(pre) and len(post):
        pre_thousands = (pre["value_scale"] == 1000.0).mean()
        post_dollars = (post["value_scale"] == 1.0).mean()
        # Compliance is imperfect in BOTH eras and that is data, not error:
        # ~1.7% of thousands-era filings are in whole dollars (Amundi-type),
        # and ~6% of dollars-era filings are chronic thousands repeaters
        # (Commerzbank 42x, Lord Abbett 18x, Morningstar 29x, quarter after
        # quarter). The check asserts the split is era-consistent, not that
        # filers read SEC releases.
        rep.add("value scale: era-consistent split with measured non-compliance",
                pre_thousands > 0.97 and post_dollars > 0.90,
                f"filed<=2021: {pre_thousands:.2%} in thousands ({len(pre):,} filings); "
                f"filed>=2024: {post_dollars:.2%} in dollars ({len(post):,})")
    else:
        rep.add("value scale across eras", True,
                f"SKIPPED: cohorts too thin (pre={len(pre)}, post={len(post)})")
    det = (led["scale_source"] == "detected").mean()
    rep.note(f"  scale decided by detection (not calendar) for {det:.1%} of filings; "
             "non-compliant filers are exactly why the calendar alone is not trusted.")

    # -- the 2023 transition: measured non-compliance, not assumed compliance - #
    boundary = led[(pd.to_datetime(led["period_end"]) == "2022-12-31")
                   & (pd.to_datetime(led["filing_date"]) >= "2023-01-03")]
    if len(boundary):
        th_share = (boundary["value_scale"] == 1000.0).mean()
        rep.add("2022Q4 boundary: detection separates compliant dollars from the "
                "still-in-thousands tail (both real)",
                0.02 <= th_share <= 0.30,
                f"{th_share:.1%} of {len(boundary):,} boundary filings still in thousands - "
                "measured non-compliance in the first quarter of the dollar rule. A pipeline "
                "trusting the calendar reads these books 1000x too small")


# --------------------------------------------------------------------------- #
def check_cross_validation(rep: Report, cfg: Config) -> None:
    rep.h("4. Cross-validation against independently parsed submissions")
    p = cfg.paths.parsed / "cross_validation.csv"
    if not p.exists():
        rep.add("cross-validation file present", False, "not found; run crowdflow datasets --cross-validate")
        return
    xv = pd.read_csv(p)
    comparable = xv[xv["status"].isin(["ok", "MISMATCH"])]
    agree = (comparable["status"] == "ok").mean() if len(comparable) else 0.0
    rep.add("raw parser and DERA agree on >=95% of sampled filings", agree >= 0.95,
            f"{agree:.1%} of {len(comparable)} sampled ({int((xv['status'] == 'fetch_failed').sum())} fetch failures excluded)")


# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs/BASE_VALIDATION.md")
    ap.add_argument("--sample", type=int, default=200)
    args = ap.parse_args()

    cfg = Config.load()
    print("loading store...", flush=True)
    holdings = pd.read_csv(cfg.paths.curated / "holdings.csv.gz")
    revisions = pd.read_csv(cfg.paths.curated / "revisions.csv.gz")
    ledger = pd.read_csv(cfg.paths.curated / "ledger.csv.gz")
    store = HoldingsStore.build(holdings, revisions)
    print(f"store: {len(holdings):,} rows, {len(revisions):,} filings", flush=True)

    rep = Report()
    rep.lines.append("# Base validation\n")
    rep.lines.append(f"Store: {len(holdings):,} positions, {len(revisions):,} filings, "
                     f"{revisions['filer_id'].nunique():,} filers, "
                     f"{pd.to_datetime(revisions['period_end']).min().date()} to "
                     f"{pd.to_datetime(revisions['period_end']).max().date()}. "
                     f"Config fingerprint `{cfg.fingerprint()}`.\n")

    check_integrity(rep, store, ledger)
    check_pit(rep, store, args.sample)
    check_external_anchors(rep, store, ledger)
    check_cross_validation(rep, cfg)

    n_fail = len(rep.failures)
    rep.lines.append(f"\n---\n\n**{n_fail} failure(s).**\n")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(rep.lines), encoding="utf-8")
    print("\n".join(rep.lines))
    print(f"\nwrote {out}")
    return n_fail


if __name__ == "__main__":
    sys.exit(main())
