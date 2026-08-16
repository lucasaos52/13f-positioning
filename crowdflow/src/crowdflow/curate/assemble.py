"""Assembly: raw submissions -> curated, bitemporal holdings store.

This is the stage where every data-quality decision is made and, importantly,
*counted*. The output carries a rejection ledger alongside the holdings so that
"we dropped 3.1% of rows" is a number in the memo rather than a hope.

Order of operations matters and is not arbitrary:

1. parse every submission (cover page + table);
2. classify instruments and drop non-equity lines **before** any dollar total is
   computed, so that book size is an equity book size;
3. clean CUSIPs and resolve instrument ids;
4. resolve reporting groups so that combination filings do not double count;
5. build the revision log and the bitemporal store.

Step 2 preceding step 4 is deliberate: reporting-group selection picks the
largest book in a group, and "largest" must already mean largest *equity* book
or a bond-heavy notice filer can win the group.
"""

from __future__ import annotations

import logging
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from ..config import Config
from ..ingest.client import EDGAR_BASE, EdgarClient
from ..ingest.infotable import parse_submission, resolve_value_scale_bulk
from .bitemporal import HoldingsStore, derive_knowledge_ts
from .filers import assign_filer_id, build_reporting_groups, load_family_overrides
from .identifiers import SecurityMaster, classify_instrument, clean_cusip_column

log = logging.getLogger(__name__)


def submission_url(cik: int, accession: str) -> str:
    return f"{EDGAR_BASE}/Archives/edgar/data/{cik}/{accession.replace('-', '')}/{accession}.txt"


def assemble(
    cfg: Config,
    client: EdgarClient,
    manifest: pd.DataFrame,
    security_master: SecurityMaster | None = None,
    family_overrides: Path | None = None,
) -> tuple[HoldingsStore, pd.DataFrame]:
    """Return the store and a per-filing quality ledger."""
    sm = security_master or SecurityMaster(None)
    overrides = load_family_overrides(family_overrides)
    manifest = assign_filer_id(manifest, overrides)

    holdings_parts: list[pd.DataFrame] = []
    ledger_rows: list[dict] = []
    reasons: Counter = Counter()

    for row in manifest.itertuples():
        try:
            raw = client.get(submission_url(int(row.cik), row.accession))
        except Exception as exc:  # noqa: BLE001
            ledger_rows.append({"accession": row.accession, "status": "fetch_failed", "detail": str(exc)[:120]})
            continue

        parsed = parse_submission(
            raw,
            row.filing_date,
            thousands_cutover=cfg.curate.thousands_cutover_date,
            unit_sniff_threshold=cfg.curate.unit_sniff_median_threshold,
        )
        tbl = parsed.holdings
        n_raw = len(tbl)

        if tbl.empty:
            ledger_rows.append(
                {
                    "accession": row.accession,
                    "filer_id": row.filer_id,
                    "cik": row.cik,
                    "period_end": row.period,
                    "form": row.form,
                    "status": "no_table",
                    "report_type": parsed.cover.report_type,
                    "n_raw": 0,
                    "n_kept": 0,
                    "book_usd": 0.0,
                    "amendment_type": parsed.cover.amendment_type,
                    "amendment_no": parsed.cover.amendment_no,
                    "confidential_omitted": parsed.cover.confidential_omitted,
                    "value_scale": parsed.value_scale,
                    "scale_source": parsed.scale_source,
                    "parse_regime": parsed.parse_regime,
                    "other_managers": parsed.cover.other_managers,
                    "warnings": "; ".join(parsed.warnings),
                }
            )
            continue

        # --- instrument class filter ---------------------------------- #
        tbl = tbl.assign(instrument_class=classify_instrument(tbl))
        drop_classes = {"debt"} if cfg.curate.drop_principal_amounts else set()
        if cfg.curate.drop_option_overlays:
            drop_classes |= {"option"}
        rejected = tbl["instrument_class"].isin(drop_classes)
        reasons.update(tbl.loc[rejected, "instrument_class"].value_counts().to_dict())
        tbl = tbl[~rejected]

        # --- identifiers ----------------------------------------------- #
        cleaned = clean_cusip_column(tbl["cusip"], allow_repair=cfg.curate.repair_cusip_check_digit)
        tbl = tbl.drop(columns=["cusip"]).join(cleaned)
        reasons.update({f"cusip_{k}": v for k, v in cleaned["cusip_action"].value_counts().to_dict().items()})
        bad_id = tbl["cusip"].isna()
        reasons["cusip_unresolved"] += int(bad_id.sum())
        tbl = tbl[~bad_id]

        if tbl.empty:
            # The table parsed but every line was filtered (all options, all
            # debt, or all unresolvable CUSIPs). Dropping the filing here with
            # no ledger row makes the filer look like it never filed for the
            # quarter, which corrupts the activation calendar's coverage count
            # and violates the rule that a filing is never silently dropped.
            # Observed in the wild: an amendment whose table is options-only.
            ledger_rows.append(
                {
                    "accession": row.accession,
                    "filer_id": row.filer_id,
                    "cik": row.cik,
                    "period_end": row.period,
                    "form": row.form,
                    "status": "all_rows_rejected",
                    "report_type": parsed.cover.report_type,
                    "n_raw": n_raw,
                    "n_kept": 0,
                    "book_usd": 0.0,
                    "amendment_type": parsed.cover.amendment_type,
                    "amendment_no": parsed.cover.amendment_no,
                    "confidential_omitted": parsed.cover.confidential_omitted,
                    "value_scale": parsed.value_scale,
                    "scale_source": parsed.scale_source,
                    "parse_regime": parsed.parse_regime,
                    "other_managers": parsed.cover.other_managers,
                    "warnings": "; ".join(
                        [*parsed.warnings, f"all {n_raw} rows rejected by class/identifier filters"]
                    ),
                }
            )
            continue

        tbl = tbl.assign(
            accession=row.accession,
            cik=int(row.cik),
            filer_id=row.filer_id,
            period_end=pd.Timestamp(row.period),
            form=row.form,
        )
        tbl = sm.resolve(tbl, asof_col="period_end")

        # Collapse duplicate lines for the same instrument within one filing.
        # Managers routinely split a position across sub-advisers or across
        # discretion categories; the economic position is the sum.
        agg = (
            tbl.groupby(["accession", "filer_id", "cik", "period_end", "instrument_id"], as_index=False)
            .agg(
                cusip=("cusip", "first"),
                cusip6=("cusip6", "first"),
                issuer=("issuer", "first"),
                title_of_class=("title_of_class", "first"),
                instrument_class=("instrument_class", "first"),
                id_source=("id_source", "first"),
                shares=("shares", "sum"),
                value_usd=("value_usd", "sum"),
                n_lines=("shares", "size"),
            )
            .assign(put_call=pd.NA)
        )
        holdings_parts.append(agg)

        ledger_rows.append(
            {
                "accession": row.accession,
                "filer_id": row.filer_id,
                "cik": row.cik,
                "period_end": row.period,
                "form": row.form,
                "status": "ok",
                "report_type": parsed.cover.report_type,
                "n_raw": n_raw,
                "n_kept": len(agg),
                "book_usd": float(agg["value_usd"].sum()),
                "amendment_type": parsed.cover.amendment_type,
                "amendment_no": parsed.cover.amendment_no,
                "confidential_omitted": parsed.cover.confidential_omitted,
                "value_scale": parsed.value_scale,
                "scale_source": parsed.scale_source,
                "parse_regime": parsed.parse_regime,
                "other_managers": parsed.cover.other_managers,
                "warnings": "; ".join(parsed.warnings),
            }
        )

    ledger = pd.DataFrame(ledger_rows)
    if not holdings_parts:
        raise RuntimeError("no holdings parsed; check the manifest and cache")
    holdings = pd.concat(holdings_parts, ignore_index=True)

    # --- reporting groups --------------------------------------------- #
    # ``all_rows_rejected`` filings stay in: the filer *did* disclose, so the
    # filing must exist in the revision log (the activation calendar counts
    # it) even though its equity book is empty.
    covers = ledger[ledger["status"].isin({"ok", "no_table", "all_rows_rejected"})].merge(
        manifest[["accession", "acceptance_dt", "filing_date", "company"]], on="accession", how="left"
    )
    covers = covers.rename(columns={"n_kept": "n_rows"})
    covers["book_usd"] = covers["book_usd"].fillna(0.0)
    covers["other_managers"] = covers["other_managers"].apply(lambda x: x if isinstance(x, list) else [])
    groups = build_reporting_groups(covers)

    keep_acc = set(groups.loc[groups["keep"], "accession"])
    # ``build_reporting_groups`` already keeps amendments belonging to the filer
    # that speaks for each group, and drops amendments to subsumed filings.
    dropped_rows = int((~holdings["accession"].isin(keep_acc)).sum())
    reasons["reporting_group_subsumed"] += dropped_rows
    holdings = holdings[holdings["accession"].isin(keep_acc)].reset_index(drop=True)

    # --- revision log --------------------------------------------------- #
    rev = groups[groups["accession"].isin(keep_acc)].copy()
    rev["knowledge_ts"] = derive_knowledge_ts(rev["acceptance_dt"])
    rev["amendment_type"] = rev["amendment_type"].fillna("")
    revisions = rev[
        [
            "filer_id",
            "cik",  # the versioning key: amendment chains live within one registrant
            "period_end",
            "accession",
            "form",
            "amendment_type",
            "amendment_no",
            "knowledge_ts",
            "acceptance_dt",
            "filing_date",  # lets verify_acceptance_timezone test UTC-vs-ET on real data
            "confidential_omitted",
            "n_rows",
            "book_usd",
            "group_id",
        ]
    ].copy()

    store = HoldingsStore.build(holdings, revisions)
    ledger.attrs["rejections"] = dict(reasons)
    log.info(
        "assembled %d holdings rows / %d filings / %d filers; rejections: %s",
        len(holdings),
        holdings["accession"].nunique(),
        holdings["filer_id"].nunique(),
        dict(reasons),
    )
    return store, ledger


# --------------------------------------------------------------------------- #
# DERA-sourced assembly
# --------------------------------------------------------------------------- #
def assemble_dera(
    cfg: Config,
    holdings_raw: pd.DataFrame,
    covers_raw: pd.DataFrame,
    security_master: SecurityMaster | None = None,
    family_overrides: Path | None = None,
    acceptance: pd.DataFrame | None = None,
) -> tuple[HoldingsStore, pd.DataFrame]:
    """DERA frames (``datasets.to_pipeline_frames``) -> the same store.

    Every decision the raw path makes per filing is made here on whole frames
    at once, *by the same functions*: ``classify_instrument``,
    ``clean_cusip_column``, ``SecurityMaster.resolve``,
    ``build_reporting_groups``, ``derive_knowledge_ts`` and the bulk twin of
    ``resolve_value_scale``. Sharing the functions is what makes
    ``cross_validate`` meaningful - if the two paths applied different
    curation, a mismatch would say nothing about parsing.

    Split into two stages with different memory behaviour:

    * ``curate_rows`` - all row-level work. Independent across ingest slices,
      so a full-history run calls it once per dataset window and only ever
      holds one window's raw rows (~3M) in memory. The output is the
      aggregated position table, roughly a sixth of the raw row count.
    * ``assemble_curated`` - the global work (reporting groups, revision log,
      the bitemporal store), which needs every window at once but operates on
      the already-aggregated rows.

    Calling this function directly on a full 13-year ingest would materialise
    ~140M raw rows and their intermediate copies - tens of GB. The window
    loop in the CLI streams instead; this wrapper remains for tests and for
    single-window use, where the distinction does not matter.

    ``acceptance`` maps accession -> acceptanceDateTime (see
    ``datasets.fetch_acceptance_times``). DERA itself only has the filing
    *date*; filings without an acceptance timestamp fall back to end of
    filing day, which ``derive_knowledge_ts`` rolls to the next session -
    conservative by one day, never anticipatory.
    """
    overrides = load_family_overrides(family_overrides)
    agg, ledger, reasons = curate_rows(cfg, holdings_raw, covers_raw, security_master, overrides)
    return assemble_curated(agg, ledger, reasons, acceptance)


def curate_rows(
    cfg: Config,
    holdings_raw: pd.DataFrame,
    covers_raw: pd.DataFrame,
    security_master: SecurityMaster | None = None,
    overrides: dict[int, str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, Counter]:
    """Row-level curation of one ingest slice: scale, class, identifiers,
    aggregation, and the per-filing ledger. Order preserved from ``assemble``:
    instrument-class filtering precedes everything book-sized, so that
    "largest book" downstream already means largest *equity* book.

    Returns ``(aggregated_positions, ledger, rejection_counter)``.
    """
    sm = security_master or SecurityMaster(None)
    overrides = overrides or {}
    reasons: Counter = Counter()

    covers = covers_raw.copy()
    covers["cik"] = covers["cik"].astype(int)
    covers = assign_filer_id(covers, overrides)
    covers["period_end"] = pd.to_datetime(covers["period_end"])
    meta_cols = ["accession", "cik", "filer_id", "period_end", "form", "filing_date", "amendment_type"]
    tbl = holdings_raw.merge(covers[meta_cols], on="accession", how="inner")
    orphans = len(holdings_raw) - len(tbl)
    if orphans:
        reasons["no_cover_metadata"] += orphans
        log.warning("%d holdings rows reference accessions absent from SUBMISSION; dropped", orphans)
    n_raw_by_acc = tbl.groupby("accession").size()

    # --- value scale, then instrument class, then identifiers ---------- #
    scales = resolve_value_scale_bulk(
        tbl, covers, cfg.curate.thousands_cutover_date, cfg.curate.unit_sniff_median_threshold
    )
    tbl = tbl.merge(scales, on="accession", how="left")
    tbl["value_usd"] = tbl["value_reported"] * tbl["value_scale"]

    tbl = tbl.assign(instrument_class=classify_instrument(tbl))
    drop_classes = {"debt"} if cfg.curate.drop_principal_amounts else set()
    if cfg.curate.drop_option_overlays:
        drop_classes |= {"option"}
    rejected = tbl["instrument_class"].isin(drop_classes)
    reasons.update(tbl.loc[rejected, "instrument_class"].value_counts().to_dict())
    tbl = tbl[~rejected]

    cleaned = clean_cusip_column(tbl["cusip"], allow_repair=cfg.curate.repair_cusip_check_digit)
    tbl = tbl.drop(columns=["cusip"]).join(cleaned)
    reasons.update({f"cusip_{k}": v for k, v in cleaned["cusip_action"].value_counts().to_dict().items()})
    bad_id = tbl["cusip"].isna()
    reasons["cusip_unresolved"] += int(bad_id.sum())
    tbl = tbl[~bad_id]
    tbl = sm.resolve(tbl, asof_col="period_end")

    agg = (
        tbl.groupby(["accession", "filer_id", "cik", "period_end", "instrument_id"], as_index=False)
        .agg(
            cusip=("cusip", "first"),
            cusip6=("cusip6", "first"),
            issuer=("issuer", "first"),
            title_of_class=("title_of_class", "first"),
            instrument_class=("instrument_class", "first"),
            id_source=("id_source", "first"),
            shares=("shares", "sum"),
            value_usd=("value_usd", "sum"),
            n_lines=("shares", "size"),
        )
        .assign(put_call=pd.NA)
    )

    # --- per-filing ledger --------------------------------------------- #
    kept = agg.groupby("accession").agg(n_kept=("instrument_id", "size"), book_usd=("value_usd", "sum"))
    ledger = covers[
        [
            "accession", "filer_id", "cik", "company", "period_end", "form", "report_type",
            "amendment_type", "amendment_no", "filing_date", "confidential_omitted",
            "other_managers", "n_rows_declared", "value_total_declared",
        ]
    ].copy()
    ledger["n_raw"] = ledger["accession"].map(n_raw_by_acc).fillna(0).astype(int)
    ledger = ledger.merge(kept, left_on="accession", right_index=True, how="left")
    ledger[["n_kept", "book_usd"]] = ledger[["n_kept", "book_usd"]].fillna(0)
    ledger = ledger.merge(scales, on="accession", how="left")
    ledger["parse_regime"] = "dera"
    ledger["status"] = np.select(
        [ledger["n_raw"].eq(0), ledger["n_kept"].eq(0)],
        ["no_table", "all_rows_rejected"],
        default="ok",
    )

    # The filer's own declared totals are the cheapest completeness check the
    # source offers, exactly as on the raw path.
    declared_rows = ledger["n_rows_declared"]
    rows_off = declared_rows.notna() & (
        (ledger["n_raw"] - declared_rows).abs() > np.maximum(2, 0.02 * declared_rows.fillna(0))
    )
    ledger["warnings"] = ""
    ledger.loc[rows_off, "warnings"] = [
        f"row count {int(n)} vs declared {int(d)}"
        for n, d in zip(ledger.loc[rows_off, "n_raw"], declared_rows[rows_off])
    ]
    for status, n in ledger["status"].value_counts().items():
        if status != "ok":
            reasons[f"filing_{status}"] += int(n)
    return agg, ledger, reasons


def assemble_curated(
    agg: pd.DataFrame,
    ledger: pd.DataFrame,
    reasons: Counter,
    acceptance: pd.DataFrame | None = None,
) -> tuple[HoldingsStore, pd.DataFrame]:
    """Global stage: reporting groups, revision log, the bitemporal store.

    ``agg`` and ``ledger`` are the (concatenated) outputs of ``curate_rows``.
    Group resolution must see all windows at once - an amendment can arrive
    years after its original and they meet only here.
    """
    # --- reporting groups, revision log, store -------------------------- #
    covers_g = ledger.rename(columns={"n_kept": "n_rows"}).copy()
    covers_g["other_managers"] = covers_g["other_managers"].apply(
        lambda x: x if isinstance(x, list) else []
    )
    if acceptance is not None and not acceptance.empty:
        covers_g = covers_g.merge(acceptance, on="accession", how="left")
    else:
        covers_g["acceptance_dt"] = pd.NA
    missing_acc = covers_g["acceptance_dt"].isna()
    if missing_acc.any():
        log.info(
            "%d/%d filings without an acceptance timestamp; knowledge date falls back "
            "to end of filing day (rolled to the next session).",
            int(missing_acc.sum()), len(covers_g),
        )
        covers_g.loc[missing_acc, "acceptance_dt"] = (
            pd.to_datetime(covers_g.loc[missing_acc, "filing_date"]).dt.strftime("%Y-%m-%d")
            + "T23:59:59.000Z"
        )

    groups = build_reporting_groups(covers_g)
    keep_acc = set(groups.loc[groups["keep"], "accession"])
    dropped_rows = int((~agg["accession"].isin(keep_acc)).sum())
    reasons["reporting_group_subsumed"] += dropped_rows
    holdings = agg[agg["accession"].isin(keep_acc)].reset_index(drop=True)

    rev = groups[groups["accession"].isin(keep_acc)].copy()
    rev["knowledge_ts"] = derive_knowledge_ts(rev["acceptance_dt"])
    rev["amendment_type"] = rev["amendment_type"].fillna("")
    revisions = rev[
        [
            "filer_id", "cik", "period_end", "accession", "form", "amendment_type",
            "amendment_no", "knowledge_ts", "acceptance_dt", "filing_date",
            "confidential_omitted", "n_rows", "book_usd", "group_id",
        ]
    ].copy()

    store = HoldingsStore.build(holdings, revisions)
    ledger.attrs["rejections"] = dict(reasons)
    log.info(
        "assembled (dera) %d holdings rows / %d filings / %d filers; rejections: %s",
        len(holdings), holdings["accession"].nunique(), holdings["filer_id"].nunique(), dict(reasons),
    )
    return store, ledger
