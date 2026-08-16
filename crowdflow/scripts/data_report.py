"""Audit report for the ingestion and curation layers.

By default loads the curated layer already on disk (the output of
``crowdflow datasets`` or ``crowdflow curate``) and audits it; with
``--rebuild`` it re-runs the raw ingest+curate first. Re-running by default
was a trap: against the full config that means re-crawling hundreds of
thousands of filings to produce a report about data that is already sitting
in ``20_curated``.

The point is that every discretionary decision in the data layer - which rows
to drop, which filer speaks for a group, what units a value is in, when a fact
became public - is *counted* here rather than asserted in prose. If a number
looks wrong, that is the report doing its job.

    python scripts/data_report.py --out docs/DATA.md --label "SEC EDGAR, DERA path"
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import io
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from crowdflow.config import Config, PathsCfg  # noqa: E402
from crowdflow.curate.bitemporal import HoldingsStore  # noqa: E402
from crowdflow.curate.filers import detect_cik_succession  # noqa: E402


def load_curated_layer(cfg: Config):
    """Store + ledger + manifest-like frame from the 20_curated artefacts."""
    holdings = pd.read_csv(cfg.paths.curated / "holdings.csv.gz")
    revisions = pd.read_csv(cfg.paths.curated / "revisions.csv.gz")
    ledger = pd.read_csv(cfg.paths.curated / "ledger.csv.gz")
    rej_path = cfg.paths.curated / "rejections.json"
    if rej_path.exists():
        import json
        ledger.attrs["rejections"] = json.loads(rej_path.read_text())
    manifest = ledger.rename(columns={"period_end": "period"})[
        [c for c in ("cik", "company", "period", "accession", "form") if c in
         ledger.rename(columns={"period_end": "period"}).columns]
    ]
    return HoldingsStore.build(holdings, revisions), ledger, manifest

SNAPSHOT_DAYS = [30, 45, 60, 75, 120, 400]


class Report:
    """Accumulates markdown and echoes a plain-text version to stdout."""

    def __init__(self) -> None:
        self.md: list[str] = []

    def h(self, text: str, level: int = 2) -> None:
        self.md.append(f"\n{'#' * level} {text}\n")
        print(f"\n{'=' * 74}\n{text}\n{'=' * 74}")

    def p(self, text: str) -> None:
        self.md.append(text + "\n")
        print(text)

    def kv(self, rows: list[tuple[str, str]], header: tuple[str, str] = ("", "")) -> None:
        self.md.append(f"| {header[0]} | {header[1]} |")
        self.md.append("|---|---|")
        for k, v in rows:
            self.md.append(f"| {k} | {v} |")
            print(f"{k:<46}{v:>12}")
        self.md.append("")

    def table(self, df: pd.DataFrame, floatfmt: str = "{:,.2f}") -> None:
        d = df.copy()
        for c in d.columns:
            if pd.api.types.is_float_dtype(d[c]):
                d[c] = d[c].map(lambda x: floatfmt.format(x) if pd.notna(x) else "")
        self.md.append("| " + " | ".join(str(c) for c in d.columns) + " |")
        self.md.append("|" + "---|" * len(d.columns))
        for r in d.itertuples(index=False):
            self.md.append("| " + " | ".join(str(x) for x in r) + " |")
        self.md.append("")
        print(d.to_string(index=False))

    def write(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(self.md).lstrip() + "\n")
        return path


# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser("data_report")
    ap.add_argument("-c", "--config", default="config/default.yaml")
    ap.add_argument("--out", default="docs/DATA.md")
    ap.add_argument("--crosswalk", default=None)
    ap.add_argument("--families", default=None)
    ap.add_argument("--cache", default=None, help="override the EDGAR cache directory")
    ap.add_argument("--root", default=None, help="override the data root")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--period", default=None, help="quarter to snapshot, e.g. 2021-06-30")
    ap.add_argument("--label", default=None, help="text describing the data source")
    ap.add_argument("--first-quarter", default=None)
    ap.add_argument("--last-quarter", default=None)
    ap.add_argument("--rebuild", action="store_true",
                    help="re-run raw ingest+curate instead of loading 20_curated from disk")
    args = ap.parse_args(argv)

    logging.disable(logging.INFO)
    cfg = Config.load(args.config)
    if args.root:
        cfg = dataclasses.replace(cfg, paths=PathsCfg(root=args.root))
    if args.offline:
        cfg = dataclasses.replace(cfg, offline=True)
    if args.first_quarter or args.last_quarter:
        cfg = dataclasses.replace(
            cfg,
            edgar=dataclasses.replace(
                cfg.edgar,
                first_quarter=args.first_quarter or cfg.edgar.first_quarter,
                last_quarter=args.last_quarter or cfg.edgar.last_quarter,
            ),
        )
    if args.rebuild:
        from crowdflow.ingest.client import EdgarClient
        from crowdflow.pipeline import stage_curate, stage_ingest
        client = EdgarClient(cfg.edgar, cache_dir=args.cache or cfg.paths.raw, offline=cfg.offline)
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            manifest = stage_ingest(cfg, client)
            store, ledger = stage_curate(cfg, client, manifest, args.crosswalk, args.families)
    else:
        store, ledger, manifest = load_curated_layer(cfg)
    rej = ledger.attrs.get("rejections", {})
    rev = store.revisions
    r = Report()

    # ---------------------------------------------------------------- #
    r.md.append("# Data layer audit\n")
    r.p(
        f"Source: {args.label or ('generated EDGAR fixtures' if cfg.offline else 'SEC EDGAR')}. "
        f"Quarters {cfg.edgar.first_quarter} to {cfg.edgar.last_quarter}. "
        f"Config fingerprint `{cfg.fingerprint()}`."
    )
    r.p(
        "\nEvery figure below is produced by `scripts/data_report.py` from the same "
        "objects the factor layer consumes. Nothing here is hand-copied."
    )

    # 1 ---------------------------------------------------------------- #
    r.h("1. Filing ledger")
    r.p(
        "One row per document fetched, recording how it was parsed and why any of "
        "it was discarded. A filing is never silently dropped."
    )
    is_notice = ledger["report_type"].fillna("").str.upper().str.contains("NOTICE")
    is_amend = ledger["form"].astype(str).str.endswith("/A")
    r.kv(
        [
            ("filings discovered", f"{len(manifest):,}"),
            ("13F-NT notices (no table by design)", f"{int(is_notice.sum()):,}"),
            ("13F-HR/A amendments", f"{int(is_amend.sum()):,}"),
            ("parsed with an information table", f"{int((ledger['status'] == 'ok').sum()):,}"),
            ("tables fully rejected by class/id filters", f"{int((ledger['status'] == 'all_rows_rejected').sum()):,}"),
            ("parse failures", f"{int((~ledger['status'].isin(['ok', 'no_table', 'all_rows_rejected'])).sum()):,}"),
            ("holdings rows retained", f"{len(store.holdings):,}"),
            ("rows dropped: option overlays", f"{rej.get('option', 0):,}"),
            ("rows dropped: debt (sshPrnamtType=PRN)", f"{rej.get('debt', 0):,}"),
            ("rows dropped: duplicate group reporting", f"{rej.get('reporting_group_subsumed', 0):,}"),
        ],
        ("stage", "count"),
    )
    r.p(
        "\nOption overlays and principal amounts are removed *before* any book total "
        "is computed. A `putCall` line reports notional exposure, not ownership, and "
        "a PRN line is face value of debt. Leaving them in inflates the book and "
        "distorts every downstream size ranking."
    )

    # 2 ---------------------------------------------------------------- #
    r.h("2. Value units")
    ok = ledger[ledger["status"] == "ok"]
    scale_tab = (
        ok.groupby([ok["period_end"].str.slice(0, 4), "value_scale"])
        .size()
        .unstack(fill_value=0)
        .reset_index()
    )
    scale_tab.columns = ["period year"] + [f"scale={int(c)}" for c in scale_tab.columns[1:]]
    r.table(scale_tab, floatfmt="{:,.0f}")
    late_thousands = int((ok[ok["period_end"] > "2023-01-01"]["value_scale"] == 1000).sum())
    r.p(
        "\nSEC Release 34-95148 moved 13F values from thousands to whole dollars for "
        "filings made **on or after 2023-01-03**. Two things defeat a calendar rule:\n\n"
        "1. the cutover keys on the *filing* date, not the period - a 2022Q4 book is "
        "filed in 2023 and reports whole dollars, so the period year is the wrong key;\n"
        f"2. {late_thousands} filings after the cutover still report thousands.\n\n"
        "Scale is therefore inferred per filing from the median implied price "
        "(`value / shares`): whole dollars land in a normal equity band, thousands "
        "land three orders of magnitude below. The calendar is only a last resort, "
        "recorded in the ledger as `scale_source='calendar'`."
    )
    src = ok["scale_source"].value_counts()
    r.kv([(str(k), f"{int(v):,}") for k, v in src.items()], ("scale decided by", "filings"))

    # 3 ---------------------------------------------------------------- #
    r.h("3. CUSIP hygiene")
    keys = [
        ("cusip_ok", "clean on arrival"),
        ("cusip_padded", "leading zero restored"),
        ("cusip_appended_check", "check digit reconstructed"),
        ("cusip_unresolved", "unrecoverable, dropped"),
    ]
    tot = sum(rej.get(k, 0) for k, _ in keys) or 1
    r.kv(
        [(lbl, f"{rej.get(k, 0):,} ({rej.get(k, 0) / tot:.2%})") for k, lbl in keys],
        ("outcome", "rows"),
    )
    r.p(
        "\nThe two corruption modes that actually occur are a leading zero eaten by a "
        "spreadsheet and a truncated check digit. Both are repaired only when the "
        "mod-10 double-add-double checksum confirms exactly one candidate; anything "
        "ambiguous is dropped rather than guessed. Share classes stay distinct - "
        "GOOG (02079K107) and GOOGL (02079K305) must never merge."
    )

    # 4 ---------------------------------------------------------------- #
    r.h("4. Filer deduplication")
    r.kv(
        [
            ("distinct CIKs filing", f"{manifest['cik'].nunique():,}"),
            ("filers after group resolution", f"{rev['filer_id'].nunique():,}"),
            ("duplicate holdings rows removed", f"{rej.get('reporting_group_subsumed', 0):,}"),
        ],
        ("", "count"),
    )
    r.p(
        "\nA parent files a combination report listing subsidiaries under "
        "`<otherManagers>`; the subsidiary files either a 13F-NT notice or - the "
        "dangerous case - its own duplicate table. Union-find over those edges, "
        "rebuilt every quarter because group membership changes, keeps one filing "
        "per group. Uncorrected, the same dollars appear twice and a crowding factor "
        "reads that as two managers independently agreeing.\n\n"
        "Name-based clustering only *proposes* merges for human review "
        "(`config/families.yaml`); it never merges automatically, because "
        "distinct legal entities routinely share a brand."
    )

    succ = detect_cik_succession(manifest)
    if not succ.empty:
        r.p(
            f"\n{len(succ)} candidate CIK successions detected "
            f"({int(succ['clean_handoff'].sum())} clean handoffs). A manager that "
            "re-registers under a new CIK is invisible to the otherManagers graph: "
            "its history is truncated at the handover, so the minimum-history screen "
            "rejects a manager that has been filing for a decade, and the universe "
            "records a spurious exit and entry mid-sample. These are proposals for "
            "review, never automatic merges.\n"
        )
        cols = ["predecessor_name", "predecessor_last_q", "successor_name",
                "successor_first_q", "name_similarity"]
        r.table(succ[cols].head(8))

    # 5 ---------------------------------------------------------------- #
    r.h("5. Filing lag: the 45-day rule is a floor, not a schedule")
    lag = store.filing_lag_profile()
    r.kv(
        [
            ("median lag (days)", f"{lag['median'].median():.0f}"),
            ("p90", f"{lag['p90'].median():.0f}"),
            ("p99", f"{lag['p99'].median():.0f}"),
            ("worst observed", f"{lag['worst'].max():.0f}"),
            ("filed by day 45, mean quarter", f"{lag['pct_by_day_45'].mean():.1%}"),
            ("filed by day 45, worst quarter", f"{lag['pct_by_day_45'].min():.1%}"),
        ],
        ("statistic", "value"),
    )
    r.p(
        f"\nTrading on day 46 would use a book that roughly "
        f"{1 - lag['pct_by_day_45'].mean():.0%} of filers had not yet disclosed. The "
        "rebalance calendar therefore activates a quarter on the first rebalance "
        "date where a threshold share of *the selected universe* has actually filed, "
        "with a hard backstop so a chronically late filer cannot stall the period "
        "indefinitely."
    )

    # 6 ---------------------------------------------------------------- #
    r.h("6. Amendments: where lookahead hides")
    ra = store.restatement_audit()
    lagged = ra[ra["lag_days"] > 0]
    r.kv(
        [
            ("amended filer-quarters", f"{len(ra):,}"),
            ("  RESTATEMENT (replaces the table)", f"{int(ra['amendment_types'].str.contains('RESTATEMENT').sum()):,}"),
            ("  NEW HOLDINGS (additive)", f"{int(ra['amendment_types'].str.contains('NEW HOLDINGS').sum()):,}"),
            ("median days, original to final", f"{lagged['lag_days'].median():.0f}"),
            ("p90", f"{lagged['lag_days'].quantile(0.9):.0f}"),
            ("max", f"{lagged['lag_days'].max():.0f}"),
            ("median absolute book revision", f"{lagged['book_delta_pct'].abs().median():.2%}"),
            ("largest book revision", f"{lagged['book_delta_pct'].abs().max():.2%}"),
        ],
        ("statistic", "value"),
    )
    r.p(
        "\nAmendment semantics follow the cover page rather than a guess:\n\n"
        "- **RESTATEMENT** - the amendment's table replaces everything previously on "
        "file for that (filer, period).\n"
        "- **NEW HOLDINGS** - the table is additive and carries only rows omitted "
        "from the original, which is the shape a lapsed confidential-treatment order "
        "takes. Those positions genuinely did not exist in the public record at the "
        "original date.\n"
        "- missing or unparseable - treated as a restatement, the conservative choice, "
        "because it never invents holdings the amendment did not contain.\n\n"
        "A period-keyed pipeline reads the final version at the original date. That is "
        "lookahead, and it is invisible: the row looks entirely ordinary."
    )
    cols = ["filer_id", "period_end", "first_knowledge", "final_knowledge", "lag_days", "amendment_types", "book_delta_pct"]
    top = lagged.reindex(lagged["book_delta_pct"].abs().sort_values(ascending=False).index)
    top = top[cols].head(6).copy()
    top["period_end"] = pd.to_datetime(top["period_end"]).dt.date
    top["first_knowledge"] = pd.to_datetime(top["first_knowledge"]).dt.date
    top["final_knowledge"] = pd.to_datetime(top["final_knowledge"]).dt.date
    top["book_delta_pct"] = top["book_delta_pct"].map("{:+.2%}".format)
    r.p("\nLargest revisions:\n")
    r.table(top)

    # 7 ---------------------------------------------------------------- #
    r.h("7. Point-in-time: one quarter, read from six different days")
    period = args.period or str(rev["period_end"].quantile(0.5, interpolation="nearest").date())
    rows = []
    for d in SNAPSHOT_DAYS:
        asof = pd.Timestamp(period) + pd.Timedelta(days=d)
        v = store.as_of(period, asof)
        rows.append(
            {
                "days after quarter end": d,
                "as of": asof.date(),
                "filers visible": v["filer_id"].nunique(),
                "positions": len(v),
                "book USD bn": round(v["value_usd"].sum() / 1e9, 1),
            }
        )
    r.p(f"Quarter {period}, as a researcher would have seen it:\n")
    r.table(pd.DataFrame(rows))
    r.p(
        "\nThis is the one query the entire factor layer is built on:\n\n"
        "```python\n"
        "store.as_of(period_end, knowledge_date)\n"
        "```\n\n"
        "`knowledge_date` comes from EDGAR's `acceptanceDateTime`, interpreted in "
        "Eastern time and rolled to the next session when acceptance is after the "
        "close. Filing date is not used: it is a date, not an instant, and it does "
        "not say whether the market could have acted that day.\n\n"
        "Both the current and prior quarter are always materialised at the *same* "
        "vantage date, so a quarter-on-quarter position change never mixes what was "
        "known then with what is known now."
    )

    r.h("Reproducing this report")
    r.p(
        "```bash\n"
        "make data-report            # against whatever config/default.yaml points at\n"
        "make demo && make data-report ARGS='--offline'   # against generated fixtures\n"
        "```\n\n"
        "The audits themselves are library functions, not report code: "
        "`store.filing_lag_profile()`, `store.restatement_audit()` and "
        "`detect_residual_duplication()` are importable and tested, so the same "
        "checks can run inside a scheduled job rather than only when someone "
        "remembers to look."
    )

    out = r.write(Path(args.out))
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
