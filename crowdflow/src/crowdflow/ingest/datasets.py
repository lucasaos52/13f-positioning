"""The SEC's own structured 13F datasets, and cross-validation against them.

There are two ways to get 13F holdings out of EDGAR and they fail differently,
which is the whole reason this module exists alongside the raw-filing crawl.

**Raw filings** (``ingest.infotable``) fetch the submission bytes and parse them
here. That works for the entire archive back to 1999, and it means the parse is
auditable: the bytes are on disk and any disagreement can be traced to a line.
It costs one request per filing, so a full history is on the order of a hundred
thousand requests, and the pre-2013 fixed-width layouts vary by filing agent —
the best-known open-source parser reports roughly 93% success on that era, and a
parser that silently returns an empty table is indistinguishable from a filer
that reported nothing.

**DERA datasets** (this module) are the SEC's own extraction of the XML filings
into tab-separated tables, published quarterly as one zip per quarter. Roughly
fifty downloads covers 2013Q2 onward. The tables are already normalised, and
``OTHERMANAGER`` hands over the reporting-group graph directly instead of making
us reconstruct it from cover pages. The costs: coverage starts at 2013Q2, the
publication lags the filings by weeks, and you inherit the SEC's parsing
decisions with no way to check them from the dataset alone.

So neither source is sufficient and they are not redundant either. The design
here is to use DERA for bulk and the raw filings for (a) everything before
2013Q2 and (b) verification — ``cross_validate`` re-parses a random sample of
raw submissions and compares them row-for-row against DERA. Two independently
derived answers agreeing is the strongest evidence available that the ingestion
is sound; where they disagree, the accession number localises the bug to one
document.

Known shape hazards, each of which produces a silent undercount rather than an
error, and each guarded below:

* the TSVs are not always at the zip root — at least one quarter nests them in a
  subdirectory, so members are resolved by basename rather than by fixed path;
* a quarter whose zip is missing or malformed must raise, because "0 filings"
  logged at INFO looks exactly like a quiet quarter;
* column names drift in case and occasionally in spelling across vintages, so
  lookups are case-insensitive and the required set is asserted up front.
"""

from __future__ import annotations

import io
import logging
import zipfile
from dataclasses import dataclass

import pandas as pd

from .client import EDGAR_BASE, EdgarClient

log = logging.getLogger(__name__)

# Tables we require. The dataset ships more (SIGNATURE, OTHERMANAGER2); those
# are optional and read when present.
REQUIRED_TABLES = ("SUBMISSION", "COVERPAGE", "INFOTABLE")
OPTIONAL_TABLES = ("SUMMARYPAGE", "OTHERMANAGER", "OTHERMANAGER2")

# Minimum columns per table, lower-cased. Asserted rather than assumed, because
# a renamed column would otherwise surface as an all-null field downstream.
REQUIRED_COLUMNS = {
    "SUBMISSION": {"accession_number", "cik", "periodofreport", "filing_date", "submissiontype"},
    "COVERPAGE": {"accession_number", "reporttype", "isamendment"},
    "INFOTABLE": {"accession_number", "nameofissuer", "cusip", "value", "sshprnamt"},
}


@dataclass(frozen=True)
class DatasetWindow:
    """One published dataset zip: a *receipt* window, not a report quarter.

    The distinction went live in 2024. Through 2023Q4 the SEC published one
    zip per calendar quarter of receipt (``2023q4_form13f.zip``). From March
    2024 the files are three-month rolling windows offset from the calendar
    (``01mar2024-31may2024_form13f.zip``: Mar-May, Jun-Aug, Sep-Nov,
    Dec-Feb), bridged by a one-off two-month stub covering January-February
    2024. All of this was established by probing the server - requesting
    ``2024q1_form13f.zip`` returns 404, which under a bare except once meant
    "a quiet quarter" rather than "the URL scheme changed underneath us".

    Either way the zip contains whatever was *accepted* in the window, so a
    single window mixes report periods: fresh filings for the just-ended
    quarter plus amendments to arbitrarily old ones. Report-period filtering
    belongs downstream; this class only names the file correctly.
    """

    label: str
    start: str  # ISO date, first receipt day covered
    end: str  # ISO date, last receipt day covered

    @property
    def url(self) -> str:
        return f"{EDGAR_BASE}/files/structureddata/data/form-13f-data-sets/{self.label}_form13f.zip"


_ROLLING_ERA_START = pd.Timestamp("2024-03-01")
_STUB = ("01jan2024-29feb2024", "2024-01-01", "2024-02-29")


def _rolling_label(start: pd.Timestamp) -> tuple[str, pd.Timestamp]:
    """(label, end) for the three-month window beginning at ``start``."""
    end = start + pd.DateOffset(months=3) - pd.Timedelta(days=1)
    fmt = lambda d: f"{d.day:02d}{d.strftime('%b').lower()}{d.year}"
    return f"{fmt(start)}-{fmt(end)}", end


def windows_between(
    first: str,
    last: str,
    pad_quarters: int = 4,
    today: str | pd.Timestamp | None = None,
) -> list[DatasetWindow]:
    """Receipt windows needed to cover report quarters ``first``..``last``.

    Two different cutoffs, deliberately not conflated:

    * **coverage** - ``pad_quarters`` extends past the last report quarter,
      because a quarter's filings are received in the *following* window and
      its amendments arrive for months after that. A window is relevant when
      it *overlaps* the coverage range, including one that starts inside it
      and ends beyond it (the Dec-Feb window straddles every year end);
    * **publication** - a window that has not ended by ``today`` cannot have
      been published, and enumerating it would guarantee one spurious
      failure per run.

    DERA coverage starts at 2013Q2; anything earlier needs the raw-filing
    path and says so.
    """
    a = pd.Period(first.replace("Q", "-Q"), freq="Q")
    floor = pd.Period("2013-Q2", freq="Q")
    if a < floor:
        log.warning(
            "DERA datasets begin at 2013Q2; %s to %s will not be covered here and needs "
            "the raw-filing path", first, str(floor)
        )
        a = floor
    lo = a.start_time.normalize()
    cov_end = (pd.Period(last.replace("Q", "-Q"), freq="Q") + pad_quarters).end_time.normalize()
    published = pd.Timestamp(today) if today is not None else pd.Timestamp.today().normalize()

    def _keep(s: pd.Timestamp, e: pd.Timestamp) -> bool:
        return e >= lo and s <= cov_end and e <= published

    out: list[DatasetWindow] = []
    # Calendar-quarter era, through 2023Q4.
    for p in pd.period_range(floor, pd.Period("2023-Q4", freq="Q"), freq="Q"):
        s, e = p.start_time.normalize(), p.end_time.normalize()
        if _keep(s, e):
            out.append(DatasetWindow(f"{p.year}q{p.quarter}", str(s.date()), str(e.date())))
    # The two-month transition stub.
    if _keep(pd.Timestamp(_STUB[1]), pd.Timestamp(_STUB[2])):
        out.append(DatasetWindow(*_STUB))
    # Rolling era.
    start = _ROLLING_ERA_START
    while start <= cov_end:
        label, end = _rolling_label(start)
        if _keep(start, end):
            out.append(DatasetWindow(label, str(start.date()), str(end.date())))
        start = start + pd.DateOffset(months=3)
    return out


# --------------------------------------------------------------------------- #
def _read_zip(blob: bytes, label: str) -> dict[str, pd.DataFrame]:
    """Extract the TSVs, resolving members by basename.

    Opening by a fixed path is the failure that costs a whole quarter: one
    published zip nests its tables in a subdirectory, a fixed-path lookup raises
    KeyError, and a bare except turns that into an empty quarter that nobody
    notices until the factor has a hole in it.
    """
    try:
        zf = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile as exc:
        raise ValueError(f"{label}: not a readable zip ({exc})") from exc

    by_name: dict[str, str] = {}
    for member in zf.namelist():
        if member.endswith("/"):
            continue
        stem = member.rsplit("/", 1)[-1].upper().removesuffix(".TSV").removesuffix(".TXT")
        by_name.setdefault(stem, member)

    missing = [t for t in REQUIRED_TABLES if t not in by_name]
    if missing:
        raise ValueError(
            f"{label}: required tables {missing} absent. Members present: "
            f"{sorted(by_name)}"
        )

    out: dict[str, pd.DataFrame] = {}
    for table in REQUIRED_TABLES + OPTIONAL_TABLES:
        if table not in by_name:
            continue
        with zf.open(by_name[table]) as fh:
            df = pd.read_csv(fh, sep="\t", dtype=str, on_bad_lines="warn", encoding_errors="replace")
        df.columns = [c.strip().lower() for c in df.columns]
        need = REQUIRED_COLUMNS.get(table, set())
        if gap := need - set(df.columns):
            raise ValueError(f"{label}/{table}: expected columns {sorted(gap)} not found")
        out[table] = df

    if out["INFOTABLE"].empty or out["SUBMISSION"].empty:
        raise ValueError(f"{label}: tables present but empty; treat as a failed download")
    return out


def load_window(client: EdgarClient, w: DatasetWindow) -> dict[str, pd.DataFrame]:
    blob = client.get(w.url)
    tables = _read_zip(blob, w.label)
    log.info(
        "%s: %d filings, %d holdings rows",
        w.label, len(tables["SUBMISSION"]), len(tables["INFOTABLE"]),
    )
    return tables


def fetch_acceptance_times(client: EdgarClient, ciks: list[int]) -> pd.DataFrame:
    """``accession -> acceptance_dt`` for every 13F filing of the given CIKs.

    The one thing the DERA datasets do not carry is the acceptance timestamp -
    they have a filing *date*, which says nothing about whether the market
    could act that day. The submissions API has it, at one request per CIK
    (plus pagination), so a full history costs on the order of ten thousand
    requests - half an hour at our rate limit, against the day and a half a
    per-filing crawl would take. Filings the API does not return simply stay
    absent here; the assembler falls back to end-of-filing-day, which
    ``derive_knowledge_ts`` then rolls to the next session - conservative,
    never anticipatory.
    """
    from .discovery import fetch_submission_history

    frames = [h for cik in sorted(set(ciks)) if not (h := fetch_submission_history(client, cik)).empty]
    if not frames:
        return pd.DataFrame(columns=["accession", "acceptance_dt"])
    out = pd.concat(frames, ignore_index=True)
    return out[["accession", "acceptance_dt"]].drop_duplicates("accession").reset_index(drop=True)


# --------------------------------------------------------------------------- #
def to_pipeline_frames(tables: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Reshape the DERA tables into the ``(holdings, covers)`` the curate layer
    already consumes, so the two ingestion paths converge before curation and
    every downstream decision is made once rather than twice.

    Note what is *not* done here: no deduplication, no CUSIP repair, no unit
    resolution. Those belong to ``curate`` and must run identically whichever
    source produced the rows, or the cross-validation below would be comparing
    two different pipelines rather than two readings of the same filings.
    """
    sub, cover, info = tables["SUBMISSION"], tables["COVERPAGE"], tables["INFOTABLE"]

    meta = sub.merge(cover, on="accession_number", how="left", suffixes=("", "_cp"))
    if "SUMMARYPAGE" in tables:
        meta = meta.merge(tables["SUMMARYPAGE"], on="accession_number", how="left", suffixes=("", "_sp"))

    covers = pd.DataFrame(
        {
            "accession": meta["accession_number"],
            "cik": pd.to_numeric(meta["cik"], errors="coerce").astype("Int64"),
            # DERA dates are uniformly DD-MON-YYYY ('31-MAR-2023'). Naming the
            # format matters twice: inference falls back to per-element parsing
            # (minutes over a full ingest), and a silent format drift in a new
            # vintage should surface as NaT + the downstream loud checks, not
            # as a creatively misread date.
            "period_end": pd.to_datetime(meta["periodofreport"], format="%d-%b-%Y", errors="coerce"),
            "filing_date": pd.to_datetime(meta["filing_date"], format="%d-%b-%Y", errors="coerce"),
            "form": meta["submissiontype"],
            "report_type": meta.get("reporttype"),
            "amendment_type": meta.get("amendmenttype"),
            "amendment_no": pd.to_numeric(meta.get("amendmentno"), errors="coerce"),
            "company": meta.get("filingmanager_name"),
            "n_rows_declared": pd.to_numeric(meta.get("tableentrytotal"), errors="coerce"),
            "value_total_declared": pd.to_numeric(meta.get("tablevaluetotal"), errors="coerce"),
            "confidential_omitted": meta.get("isconfidentialomitted", pd.Series(dtype=str))
            .astype(str).str.upper().isin({"Y", "TRUE", "1"}),
            "source": "dera",
        }
    )

    # The reporting-group graph, handed over rather than reconstructed.
    om_frames = [tables[t] for t in ("OTHERMANAGER", "OTHERMANAGER2") if t in tables]
    if om_frames:
        om = pd.concat(om_frames, ignore_index=True)
        cik_col = next((c for c in om.columns if c.endswith("cik")), None)
        if cik_col:
            grouped = (
                om.assign(_c=pd.to_numeric(om[cik_col], errors="coerce"))
                .dropna(subset=["_c"])
                .groupby("accession_number")["_c"]
                .apply(lambda s: sorted({int(x) for x in s}))
            )
            covers["other_managers"] = covers["accession"].map(grouped)
    covers["other_managers"] = covers.get(
        "other_managers", pd.Series(index=covers.index, dtype=object)
    ).apply(lambda x: x if isinstance(x, list) else [])

    holdings = pd.DataFrame(
        {
            "accession": info["accession_number"],
            "issuer": info["nameofissuer"],
            "title_of_class": info.get("titleofclass"),
            "cusip": info["cusip"],
            "figi": info.get("figi"),
            "value_reported": pd.to_numeric(info["value"], errors="coerce"),
            "shares": pd.to_numeric(info["sshprnamt"], errors="coerce"),
            "share_type": info.get("sshprnamttype"),
            "put_call": info.get("putcall"),
            "discretion": info.get("investmentdiscretion"),
            "other_manager": info.get("othermanager"),
        }
    )
    return holdings, covers


# --------------------------------------------------------------------------- #
def cross_validate(
    client: EdgarClient,
    acc_stats: pd.DataFrame,
    meta_frame: pd.DataFrame,
    sample: int = 25,
    seed: int = 20240614,
    value_tolerance: float = 0.01,
) -> pd.DataFrame:
    """Re-derive a random sample of filings from raw bytes and compare.

    This is the check that neither ingestion path can perform on itself. DERA
    cannot tell you whether the SEC's extraction dropped a row; the raw parser
    cannot tell you whether *its* reading is the odd one out. Running both over
    the same accession numbers and comparing row counts and value totals turns
    "the parse looked fine" into a number.

    ``acc_stats`` carries one row per accession with ``rows_dera`` and
    ``value_dera`` - precomputed per window so a full-history run never has to
    hold the raw holdings in memory just to be checked. ``meta_frame`` needs
    accession, cik and filing_date (the curation ledger qualifies).

    A disagreement is not automatically the parser's fault, and the output says
    so: it reports both sides and the accession, so the document can be opened.
    Systematic disagreement in one direction is the signal worth chasing — a
    handful of scattered mismatches on unusual filings is expected.
    """
    from .infotable import parse_submission

    # Only filings that actually carry a table are comparable; a 13F-NT has
    # no INFOTABLE rows on either side, so sampling one tests nothing.
    rng = pd.Series(acc_stats.loc[acc_stats["rows_dera"].gt(0), "accession"].unique())
    picks = rng.sample(min(sample, len(rng)), random_state=seed).tolist()

    by_acc_rows = acc_stats.set_index("accession")["rows_dera"]
    by_acc_val = acc_stats.set_index("accession")["value_dera"]
    meta = meta_frame.drop_duplicates("accession").set_index("accession")

    rows = []
    for acc in picks:
        cik = meta.loc[acc, "cik"]
        url = f"{EDGAR_BASE}/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/{acc}.txt"
        try:
            raw = client.get(url)
        except Exception as exc:  # noqa: BLE001
            rows.append({"accession": acc, "status": "fetch_failed", "detail": str(exc)[:80]})
            continue

        parsed = parse_submission(raw, str(pd.Timestamp(meta.loc[acc, "filing_date"]).date()))
        n_raw, n_dera = len(parsed.holdings), int(by_acc_rows.get(acc, 0))
        v_raw = float(parsed.holdings["value_reported"].sum()) if n_raw else 0.0
        v_dera = float(by_acc_val.get(acc, 0.0))
        rel = abs(v_raw - v_dera) / v_dera if v_dera else (0.0 if v_raw == 0 else 1.0)

        rows.append(
            {
                "accession": acc,
                "status": "ok" if (n_raw == n_dera and rel <= value_tolerance) else "MISMATCH",
                "rows_raw": n_raw,
                "rows_dera": n_dera,
                "value_raw": v_raw,
                "value_dera": v_dera,
                "value_rel_diff": rel,
                "parse_regime": parsed.parse_regime,
            }
        )

    out = pd.DataFrame(rows)
    if not out.empty:
        agree = (out["status"] == "ok").mean()
        log.info(
            "cross-validation: %d filings, %.1f%% agree on both row count and value total",
            len(out), 100 * agree,
        )
        if agree < 0.95:
            log.warning(
                "cross-validation agreement below 95%%. Inspect the MISMATCH rows before "
                "trusting either source."
            )
    return out
