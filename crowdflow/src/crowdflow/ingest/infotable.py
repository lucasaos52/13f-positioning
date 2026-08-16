"""Parsing of 13F submissions into cover-page metadata and holdings rows.

A 13F submission on EDGAR is an SGML envelope containing several ``<DOCUMENT>``
sections. Two matter:

* the **cover page** (``primary_doc.xml``, type ``13F-HR``), which carries the
  report type, the amendment flag, the confidential-omission flag, the
  self-declared row/value totals, and the list of other managers covered;
* the **information table** (type ``INFORMATION TABLE``), the holdings.

Three format regimes exist in the archive and all three appear in a long
backtest window:

1. ``>= 2013Q2`` - XML information table, namespaced. The common case.
2. ``2004Q2 - 2013Q1`` - transitional; some filers already file XML, most file
   a fixed-width text table inside the SGML envelope.
3. ``< 2004`` - paper/text only, no machine-readable table worth trusting.

The parser targets (1) as the primary path and provides a best-effort
fixed-width reader for (2) so that the sample can be extended backwards with an
explicit quality flag rather than a silent gap.

Unit trap
---------
``value`` was reported in **thousands of dollars** until the amendments in SEC
Release 34-95148 took effect, after which it is **whole dollars**. Filings made
on or after 2023-01-03 use whole dollars. Trusting the calendar alone is not
enough - amendments to old periods filed after the cutover, and a tail of
non-compliant filers, break it. We therefore *detect* the unit per filing by
comparing implied price (value / shares) against a plausible equity price band,
and fall back to the calendar rule only when detection is inconclusive.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from lxml import etree

log = logging.getLogger(__name__)

_DOC_RE = re.compile(rb"<DOCUMENT>(.*?)</DOCUMENT>", re.DOTALL | re.IGNORECASE)
_TYPE_RE = re.compile(rb"<TYPE>([^\r\n<]+)", re.IGNORECASE)
_TEXT_RE = re.compile(rb"<TEXT>(.*?)</TEXT>", re.DOTALL | re.IGNORECASE)
_XML_RE = re.compile(rb"<\?xml.*?\?>(.*)", re.DOTALL)


@dataclass
class CoverPage:
    """Normalised 13F cover page."""

    report_type: str = ""  # 13F HOLDINGS REPORT | 13F NOTICE | 13F COMBINATION REPORT
    amendment_type: str = ""  # RESTATEMENT | NEW HOLDINGS | ''
    amendment_no: int | None = None
    is_amendment: bool = False
    confidential_omitted: bool = False
    table_entry_total: int | None = None
    table_value_total: float | None = None
    other_managers: list[int] = field(default_factory=list)
    filer_name: str = ""

    @property
    def is_notice(self) -> bool:
        """A notice declares that holdings are reported by another manager."""
        return "NOTICE" in self.report_type.upper()


@dataclass
class ParsedFiling:
    cover: CoverPage
    holdings: pd.DataFrame
    value_scale: float  # 1.0 for whole dollars, 1000.0 for thousands
    scale_source: str  # 'detected' | 'calendar' | 'default'
    parse_regime: str  # 'xml' | 'legacy_text' | 'empty'
    warnings: list[str] = field(default_factory=list)


HOLDING_COLS = [
    "issuer",
    "title_of_class",
    "cusip",
    "figi",
    "value_reported",
    "shares",
    "share_type",
    "put_call",
    "discretion",
    "other_manager",
    "voting_sole",
    "voting_shared",
    "voting_none",
]


# --------------------------------------------------------------------------- #
# SGML envelope
# --------------------------------------------------------------------------- #
def iter_documents(raw: bytes) -> Iterator[tuple[str, bytes]]:
    """Yield ``(type, body)`` for each ``<DOCUMENT>`` in an SGML submission."""
    for block in _DOC_RE.findall(raw):
        tm = _TYPE_RE.search(block)
        bm = _TEXT_RE.search(block)
        if not tm or not bm:
            continue
        yield tm.group(1).strip().decode("utf-8", "replace").upper(), bm.group(1).strip()


def _localname(tag: Any) -> str:
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1].lower()


def _to_tree(body: bytes) -> etree._Element | None:
    """Parse loosely: 13F XML in the wild has stray prologues and bad encodings."""
    m = _XML_RE.search(body)
    payload = m.group(1) if m else body
    parser = etree.XMLParser(recover=True, resolve_entities=False, huge_tree=True)
    try:
        root = etree.fromstring(payload.strip(), parser=parser)
    except etree.XMLSyntaxError:
        return None
    return root


def _first_text(root: etree._Element, name: str) -> str:
    for el in root.iter():
        if _localname(el.tag) == name and el.text:
            return el.text.strip()
    return ""


# --------------------------------------------------------------------------- #
# Cover page
# --------------------------------------------------------------------------- #
def parse_cover(body: bytes) -> CoverPage:
    root = _to_tree(body)
    cover = CoverPage()
    if root is None:
        return cover

    cover.report_type = _first_text(root, "reporttype")
    cover.filer_name = _first_text(root, "name")

    for el in root.iter():
        if _localname(el.tag) == "amendmentinfo":
            cover.amendment_type = _first_text(el, "amendmenttype")
        if _localname(el.tag) == "amendmentno" and el.text:
            try:
                cover.amendment_no = int(el.text.strip())
            except ValueError:
                pass
        if _localname(el.tag) == "isamendment" and el.text:
            cover.is_amendment = el.text.strip().lower() in {"true", "y", "yes", "1"}
        if _localname(el.tag) == "confdeniedexpired" and el.text:
            cover.confidential_omitted |= el.text.strip().lower() in {"true", "y", "yes", "1"}
        if _localname(el.tag) == "isconfidentialomitted" and el.text:
            cover.confidential_omitted |= el.text.strip().lower() in {"true", "y", "yes", "1"}
        if _localname(el.tag) == "tableentrytotal" and el.text:
            try:
                cover.table_entry_total = int(float(el.text.strip()))
            except ValueError:
                pass
        if _localname(el.tag) == "tablevaluetotal" and el.text:
            try:
                cover.table_value_total = float(el.text.strip().replace(",", ""))
            except ValueError:
                pass

    # Other managers appear under several shapes across schema versions.
    seen: set[int] = set()
    for el in root.iter():
        if _localname(el.tag) in {"othermanager", "othermanager2"}:
            cik_txt = _first_text(el, "cik")
            if cik_txt and cik_txt.strip().isdigit():
                seen.add(int(cik_txt))
    cover.other_managers = sorted(seen)

    if cover.amendment_type:
        cover.is_amendment = True
    return cover


# --------------------------------------------------------------------------- #
# Information table - XML regime
# --------------------------------------------------------------------------- #
def _num(text: str | None) -> float | None:
    if not text:
        return None
    cleaned = text.replace(",", "").replace("$", "").strip()
    if not cleaned or cleaned in {"-", "N/A"}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_infotable_xml(body: bytes) -> pd.DataFrame:
    root = _to_tree(body)
    if root is None:
        return pd.DataFrame(columns=HOLDING_COLS)

    rows: list[dict[str, Any]] = []
    for node in root.iter():
        if _localname(node.tag) != "infotable":
            continue
        rec: dict[str, Any] = {c: None for c in HOLDING_COLS}
        for child in node.iter():
            tag, txt = _localname(child.tag), (child.text or "").strip()
            if tag == "nameofissuer":
                rec["issuer"] = txt
            elif tag == "titleofclass":
                rec["title_of_class"] = txt
            elif tag == "cusip":
                rec["cusip"] = txt.upper().replace(" ", "")
            elif tag == "figi":
                rec["figi"] = txt or None
            elif tag == "value":
                rec["value_reported"] = _num(txt)
            elif tag == "sshprnamt":
                rec["shares"] = _num(txt)
            elif tag == "sshprnamttype":
                rec["share_type"] = txt.upper()
            elif tag == "putcall":
                rec["put_call"] = txt.upper()
            elif tag == "investmentdiscretion":
                rec["discretion"] = txt.upper()
            elif tag == "othermanager":
                rec["other_manager"] = txt
            elif tag == "sole":
                rec["voting_sole"] = _num(txt)
            elif tag == "shared":
                rec["voting_shared"] = _num(txt)
            elif tag == "none":
                rec["voting_none"] = _num(txt)
        rows.append(rec)

    return pd.DataFrame(rows, columns=HOLDING_COLS) if rows else pd.DataFrame(columns=HOLDING_COLS)


# --------------------------------------------------------------------------- #
# Information table - legacy fixed-width regime
# --------------------------------------------------------------------------- #
# Pre-XML information tables are fixed-width text laid out by the filing agent,
# and the layout varies. Three features of the real format broke an earlier
# version of this regex, each producing zero rows silently:
#
#   ConocoPhillips     Com    20825C 10 4     $559,273     9,612,800   X   1, 2, 3
#
#   * the CUSIP is printed in 6-2-1 groups separated by spaces;
#   * the value carries a dollar sign;
#   * there is no SH/PRN marker at all - the old form has one "Shares or
#     Principal Amount" column with the type implied by the row.
#
# Requiring a SH/PRN token, as the first version did, meant every pre-2004
# filing parsed to an empty table and was dropped without an error. That is the
# failure mode this module exists to prevent, so the marker is now optional and
# a legacy filing that yields nothing is reported rather than discarded.
_CUSIP_TOKEN = r"[0-9A-Z]{6}[ ]?[0-9A-Z]{2}[ ]?[0-9A-Z]|[0-9A-Z]{8,9}"

_LEGACY_ROW = re.compile(
    r"^(?P<issuer>\S.{0,58}?)\s{2,}"
    r"(?P<cls>\S.{0,24}?)\s{2,}"
    rf"(?P<cusip>{_CUSIP_TOKEN})\s{{2,}}"
    r"\$?\s*(?P<value>[\d,]+(?:\.\d+)?)\s{2,}"
    r"(?P<shares>[\d,]+(?:\.\d+)?)"
    r"(?P<rest>.*)$",
    re.IGNORECASE,
)

_LEGACY_NOISE = re.compile(
    r"^(column|name of issuer|-{3,}|={3,}|<|total|form 13f|page\b)", re.IGNORECASE
)


def parse_infotable_legacy(body: bytes) -> pd.DataFrame:
    """Best-effort reader for pre-XML fixed-width tables.

    Conservative but not so strict that it silently returns nothing: a row is
    kept when an issuer, a class, a CUSIP-shaped token, a value and a share
    count line up. The SH/PRN marker is honoured when present and left null
    otherwise, because the oldest layouts do not carry it.
    """
    text = body.decode("latin-1", "replace")
    text = re.sub(r"<[^>]+>", " ", text)
    rows: list[dict[str, Any]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if len(line) < 20 or _LEGACY_NOISE.match(line):
            continue
        m = _LEGACY_ROW.match(line)
        if not m:
            continue
        rest = m.group("rest").upper()
        stype = "PRN" if re.search(r"\bPRN\b", rest) else ("SH" if re.search(r"\bSH\b", rest) else None)
        rec = {c: None for c in HOLDING_COLS}
        rec.update(
            issuer=m.group("issuer").strip(),
            title_of_class=m.group("cls").strip(),
            cusip=m.group("cusip").upper().replace(" ", ""),
            value_reported=_num(m.group("value")),
            shares=_num(m.group("shares")),
            share_type=stype,
            put_call="PUT" if " PUT" in rest else ("CALL" if " CALL" in rest else None),
        )
        rows.append(rec)
    return pd.DataFrame(rows, columns=HOLDING_COLS) if rows else pd.DataFrame(columns=HOLDING_COLS)


# --------------------------------------------------------------------------- #
# Cover page - legacy text regime
# --------------------------------------------------------------------------- #
_CHECKED = r"\[\s*[Xx]\s*\]"

_COVER_PATTERNS = {
    "holdings": re.compile(rf"{_CHECKED}\s*13F\s+HOLDINGS\s+REPORT", re.IGNORECASE),
    "notice": re.compile(rf"{_CHECKED}\s*13F\s+NOTICE", re.IGNORECASE),
    "combination": re.compile(rf"{_CHECKED}\s*13F\s+COMBINATION\s+REPORT", re.IGNORECASE),
    "is_amendment": re.compile(rf"Check\s+here\s+if\s+Amendment\s*{_CHECKED}", re.IGNORECASE),
    "restatement": re.compile(rf"{_CHECKED}\s*is\s+a\s+restatement", re.IGNORECASE),
    "new_holdings": re.compile(rf"{_CHECKED}\s*adds\s+new\s+holdings", re.IGNORECASE),
}
_AMEND_NO = re.compile(r"Amendment\s+Number:\s*([0-9]+)", re.IGNORECASE)
_ENTRY_TOTAL = re.compile(r"Information\s+Table\s+Entry\s+Total:\s*\$?\s*([\d,]+)", re.IGNORECASE)
_VALUE_TOTAL = re.compile(r"Information\s+Table\s+Value\s+Total:\s*\$?\s*([\d,]+)", re.IGNORECASE)
_CONFIDENTIAL = re.compile(r"CONFIDENTIAL\s+TREATMENT", re.IGNORECASE)


def parse_cover_text(body: bytes) -> CoverPage:
    """Cover page for the pre-XML regime, read from the printed checkboxes.

    This is not cosmetic metadata. The amendment checkboxes carry the
    restatement-versus-additive distinction, and losing it is destructive in one
    specific direction: an additive amendment mistaken for a restatement
    *replaces* the filer's whole book for that quarter with the handful of rows
    the amendment contains. Berkshire's 2005Q4 confidential-treatment amendment
    holds exactly one line, so the error would delete an entire quarter of
    positions and leave a single ConocoPhillips holding in its place - with no
    exception raised and nothing in the output that looks wrong.
    """
    text = body.decode("latin-1", "replace")
    # Collapse the line breaks the printed form puts between a checkbox and its
    # label, so the patterns can match across them.
    flat = re.sub(r"\s+", " ", text)

    cover = CoverPage()
    if _COVER_PATTERNS["combination"].search(flat):
        cover.report_type = "13F COMBINATION REPORT"
    elif _COVER_PATTERNS["notice"].search(flat):
        cover.report_type = "13F NOTICE"
    elif _COVER_PATTERNS["holdings"].search(flat):
        cover.report_type = "13F HOLDINGS REPORT"

    cover.is_amendment = bool(_COVER_PATTERNS["is_amendment"].search(flat))
    if _COVER_PATTERNS["new_holdings"].search(flat):
        cover.amendment_type = "NEW HOLDINGS"
        cover.is_amendment = True
    elif _COVER_PATTERNS["restatement"].search(flat):
        cover.amendment_type = "RESTATEMENT"
        cover.is_amendment = True

    if m := _AMEND_NO.search(flat):
        cover.amendment_no = int(m.group(1))
    if m := _ENTRY_TOTAL.search(flat):
        cover.table_entry_total = int(m.group(1).replace(",", ""))
    if m := _VALUE_TOTAL.search(flat):
        cover.table_value_total = float(m.group(1).replace(",", ""))
    cover.confidential_omitted = bool(_CONFIDENTIAL.search(flat))
    return cover


# --------------------------------------------------------------------------- #
# Unit resolution
# --------------------------------------------------------------------------- #
def resolve_value_scale(
    holdings: pd.DataFrame,
    filing_date: str,
    cutover: str,
    median_threshold: float,
    is_partial: bool = False,
) -> tuple[float, str]:
    """Decide whether ``value`` is in whole dollars or thousands.

    Detection is by implied price: ``value / shares``. If values are in whole
    dollars the implied price sits in a normal equity band (roughly 1-10,000);
    if in thousands it lands three orders of magnitude below. The median over
    the filing is robust to the handful of rows where shares are zero or the
    issuer is an odd instrument.

    The decision reads **two quantiles**, not one, and the reason was paid
    for with real misreads at the 2022Q4 boundary - the first quarter of the
    dollar rule, where a measured 18% of books were still filed in thousands
    and had to be separated from dollar books that merely *look* small:

    * A genuine thousands book has implied prices that are share prices
      divided by 1000: median ~0.08, and crucially its 90th percentile stays
      near 0.26 - almost nothing trades above $1,000 a share.
    * A SPAC-arbitrage book in whole dollars - the failure mode - has a
      *median* implied of 0.14-0.30, because most of its lines are warrants
      priced in cents. On the median alone it is indistinguishable from
      thousands, and multiplying it by 1000 manufactures a phantom $700bn
      portfolio that would dominate any size ranking. But its 90th
      percentile sits at ~10.25: the $10 trust share. Measured across 6,654
      real boundary filings the two populations are separated by a factor
      of 25 at the 90th percentile (thousands p90 of q90: 0.37; dollars p01
      of q90: 10.4), so the cut at 1.0 sits in empty space.

    Option lines are excluded from the sample - their value-per-share is a
    premium, not a price. Anything the two-quantile test cannot call falls
    through to the book-size check and then the filing-date calendar.

    ``is_partial`` marks a table that is not a whole book - a ``NEW HOLDINGS``
    amendment carries only the rows withheld under a confidential-treatment
    order, often fewer than five. For those the book-size fallback below is
    meaningless: the total is *supposed* to be small, and applying it multiplies
    a legitimate partial disclosure by a thousand.
    """
    pc = (
        holdings["put_call"]
        if "put_call" in holdings.columns
        else pd.Series("", index=holdings.index)
    )
    eq = holdings[
        holdings["share_type"].fillna("SH").str.upper().eq("SH")
        & pc.fillna("").astype(str).str.strip().eq("")
        & holdings["shares"].fillna(0).gt(0)
        & holdings["value_reported"].fillna(0).gt(0)
    ]
    total = holdings["value_reported"].fillna(0).sum()
    if len(eq):
        implied = eq["value_reported"] / eq["shares"]
        med, q90 = implied.median(), implied.quantile(0.9)
        if med < 0.5 and q90 < 1.0 and not _implausible_thousands(total, is_partial):
            return 1000.0, "detected"
        if med > 2.0 and q90 > 20.0:
            return 1.0, "detected"

    # Secondary: a book whose reported total is implausibly small for a filer
    # that cleared the $100mm 13F threshold is almost certainly in thousands.
    # Only meaningful for a table that claims to be a complete book.
    if not is_partial and len(holdings) >= 20:
        if total > 0 and total < median_threshold:
            return 1000.0, "detected"

    if pd.Timestamp(filing_date) >= pd.Timestamp(cutover):
        return 1.0, "calendar"
    if _implausible_thousands(total, is_partial):
        # Pre-cutover calendar says thousands, but multiplying would produce a
        # book beyond the largest real 13F complexes while the as-filed total
        # already clears the $100mm filing threshold: the filer reported whole
        # dollars in the thousands era. Real cases: a $6.6bn book read as
        # $6.6tn, a private bank's $16.6bn sleeve read as $16.6tn.
        return 1.0, "plausibility"
    return 1000.0, "calendar"


# No 13F equity book exceeds a few trillion dollars (the largest index
# complexes run $5-7tn), and no complete book is below the $100mm filing
# threshold. A thousands reading that lands outside both bounds at once is
# self-refuting, whatever the implied prices say.
_MAX_PLAUSIBLE_BOOK_USD = 3e12
_MIN_COMPLETE_BOOK_USD = 1e8


def _implausible_thousands(total_reported: float, is_partial: bool) -> bool:
    if is_partial or not total_reported or total_reported <= 0:
        return False
    return (total_reported * 1000.0 > _MAX_PLAUSIBLE_BOOK_USD
            and total_reported >= _MIN_COMPLETE_BOOK_USD)


def resolve_value_scale_bulk(
    holdings: pd.DataFrame,
    covers: pd.DataFrame,
    cutover: str,
    median_threshold: float,
) -> pd.DataFrame:
    """``resolve_value_scale`` for a whole ingest at once.

    Same decision, same thresholds, same precedence - implied-price detection
    first, the book-size fallback only for complete books, the filing-date
    calendar last - just grouped by accession instead of called half a million
    times. ``test_bulk_scale_agrees_with_scalar`` pins the two implementations
    to each other so they cannot drift apart silently.

    ``holdings`` needs accession, share_type, shares, value_reported.
    ``covers`` needs accession, filing_date, amendment_type.
    Returns one row per accession: value_scale, scale_source.
    """
    h = holdings
    pc = h["put_call"] if "put_call" in h.columns else pd.Series("", index=h.index)
    eq = h[
        h["share_type"].fillna("SH").astype(str).str.upper().eq("SH")
        & pc.fillna("").astype(str).str.strip().eq("")
        & h["shares"].fillna(0).gt(0)
        & h["value_reported"].fillna(0).gt(0)
    ]
    g = (eq["value_reported"] / eq["shares"]).groupby(eq["accession"])
    stats = pd.DataFrame({"med": g.median(), "q90": g.quantile(0.9), "n_eq": g.size()})
    per_acc = h.groupby("accession").agg(
        n_rows=("value_reported", "size"), total=("value_reported", "sum")
    )
    out = covers[["accession", "filing_date", "amendment_type"]].drop_duplicates("accession").copy()
    out = out.merge(stats, left_on="accession", right_index=True, how="left")
    out = out.merge(per_acc, left_on="accession", right_index=True, how="left")

    n_eq = out["n_eq"].fillna(0)
    is_partial = (
        out["amendment_type"].fillna("").astype(str).str.upper().str.strip().eq("NEW HOLDINGS")
    )
    total = out["total"].fillna(0)
    # Self-refuting thousands reading: multiplying would exceed the largest
    # real 13F complexes while the as-filed total already clears the $100mm
    # filing threshold. Same bounds as the scalar twin.
    implausible_th = (
        ~is_partial
        & (total * 1000.0 > _MAX_PLAUSIBLE_BOOK_USD)
        & (total >= _MIN_COMPLETE_BOOK_USD)
    )

    det_thousands = (n_eq > 0) & (out["med"] < 0.5) & (out["q90"] < 1.0) & ~implausible_th
    det_dollars = (n_eq > 0) & (out["med"] > 2.0) & (out["q90"] > 20.0)

    small_book = (
        ~is_partial
        & ~det_thousands
        & ~det_dollars
        & out["n_rows"].fillna(0).ge(20)
        & total.gt(0)
        & total.lt(median_threshold)
    )

    pre_cutover = pd.to_datetime(out["filing_date"], errors="coerce") < pd.Timestamp(cutover)
    out["value_scale"] = np.select(
        [det_thousands, det_dollars, small_book, pre_cutover & implausible_th, pre_cutover],
        [1000.0, 1.0, 1000.0, 1.0, 1000.0],
        default=1.0,
    )
    out["scale_source"] = np.select(
        [det_thousands | det_dollars | small_book, pre_cutover & implausible_th],
        ["detected", "plausibility"],
        default="calendar",
    )
    return out[["accession", "value_scale", "scale_source"]]


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def parse_submission(
    raw: bytes,
    filing_date: str,
    *,
    thousands_cutover: str = "2023-01-03",
    unit_sniff_threshold: float = 50_000.0,
) -> ParsedFiling:
    cover = CoverPage()
    table = pd.DataFrame(columns=HOLDING_COLS)
    regime = "empty"
    warnings: list[str] = []

    docs = list(iter_documents(raw))
    if not docs:  # bare document, not an SGML envelope
        docs = [("INFORMATION TABLE", raw)]

    for doc_type, body in docs:
        if doc_type.startswith("13F-") and b"<" in body[:2000]:
            parsed_cover = parse_cover(body)
            if parsed_cover.report_type or parsed_cover.table_entry_total:
                cover = parsed_cover
        elif "INFORMATION TABLE" in doc_type or doc_type in {"XML", "INFOTABLE"}:
            candidate = parse_infotable_xml(body)
            if not candidate.empty:
                table, regime = candidate, "xml"
            else:
                candidate = parse_infotable_legacy(body)
                if not candidate.empty:
                    table, regime = candidate, "legacy_text"

    if table.empty:  # last resort: scan every document
        for _, body in docs:
            candidate = parse_infotable_xml(body)
            if candidate.empty:
                candidate = parse_infotable_legacy(body)
            if not candidate.empty:
                table = candidate
                regime = "xml" if b"infoTable" in body or b"infotable" in body.lower() else "legacy_text"
                break

    if not cover.report_type and not cover.table_entry_total:
        # Pre-XML submission: the cover page is printed text, not a schema.
        for _, body in docs:
            candidate = parse_cover_text(body)
            if candidate.report_type or candidate.table_entry_total or candidate.amendment_type:
                cover = candidate
                break

    if table.empty:
        note = "no information table found"
        if cover.table_entry_total:
            # The filer declared rows and we found none. This is a parse
            # failure, not an empty filing, and it must not be mistaken for a
            # notice further down the pipeline.
            note = (
                f"PARSE FAILURE: cover declares {cover.table_entry_total} entries, "
                f"parser recovered 0"
            )
        return ParsedFiling(cover, table, 1.0, "default", regime, [note])

    # A NEW HOLDINGS amendment carries only previously withheld rows, so its
    # table is a fragment of a book rather than a book.
    is_partial = (cover.amendment_type or "").upper().strip() == "NEW HOLDINGS"
    scale, source = resolve_value_scale(
        table, filing_date, thousands_cutover, unit_sniff_threshold, is_partial=is_partial
    )
    table = table.assign(value_usd=table["value_reported"] * scale)

    # Reconciliation against the filer's own declared totals is the cheapest
    # available check that the parse is complete.
    if cover.table_entry_total and abs(len(table) - cover.table_entry_total) > max(
        2, 0.02 * cover.table_entry_total
    ):
        warnings.append(f"row count {len(table)} vs declared {cover.table_entry_total}")
    if cover.table_value_total:
        declared = cover.table_value_total * scale
        got = table["value_usd"].sum()
        if declared > 0 and abs(got - declared) / declared > 0.05:
            warnings.append(f"value total {got:,.0f} vs declared {declared:,.0f}")

    return ParsedFiling(cover, table, scale, source, regime, warnings)
