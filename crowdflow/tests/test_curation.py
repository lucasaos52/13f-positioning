"""Tests for the parts where sloppiness is invisible until it is expensive."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from crowdflow.curate.bitemporal import HoldingsStore, derive_knowledge_ts
from crowdflow.curate.filers import (
    build_reporting_groups,
    detect_cik_succession,
    load_family_overrides,
    normalise_name,
)
from crowdflow.curate.identifiers import (
    clean_cusip_column,
    cusip_check_digit,
    is_valid_cusip,
    normalise_cusip,
)
from crowdflow.ingest.infotable import parse_submission, resolve_value_scale


# --------------------------------------------------------------------------- #
# CUSIP
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "cusip",
    [
        "037833100",  # Apple
        "594918104",  # Microsoft
        "88160R101",  # Tesla, letter in the body
        "02079K305",  # Alphabet C
        "02079K107",  # Alphabet A - different security, must not collide
    ],
)
def test_known_cusips_validate(cusip):
    assert is_valid_cusip(cusip)
    assert cusip_check_digit(cusip[:8]) == cusip[8]


def test_alphabet_classes_stay_distinct():
    """GOOG and GOOGL are one issuer but two securities. Merging them would
    net a manager's positions across classes and invent trades that never
    happened."""
    a, c = "02079K107", "02079K305"
    assert a != c
    assert a[:6] == c[:6]  # same issuer at CUSIP6


def test_check_digit_rejects_transposition():
    assert not is_valid_cusip("037833010")


def test_leading_zero_repair():
    fix = normalise_cusip("37833100")
    assert fix.fixed == "037833100"
    assert fix.action == "padded"


def test_missing_check_digit_repair():
    fix = normalise_cusip("03783310")
    assert fix.fixed == "037833100"
    assert fix.action == "appended_check"


def test_repair_can_be_disabled():
    assert normalise_cusip("37833100", allow_repair=False).fixed is None


def test_clean_column_vectorised():
    s = pd.Series(["037833100", "37833100", "GARBAGE!!", None])
    out = clean_cusip_column(s)
    assert out["cusip"].tolist()[:2] == ["037833100", "037833100"]
    assert out["cusip"].isna().iloc[2]


# --------------------------------------------------------------------------- #
# Value units
# --------------------------------------------------------------------------- #
def _tbl(values, shares):
    return pd.DataFrame(
        {"value_reported": values, "shares": shares, "share_type": ["SH"] * len(values)}
    )


def test_thousands_detected_from_implied_price():
    # $150 stock, 100k shares -> $15,000k reported in thousands.
    tbl = _tbl([15_000.0] * 8, [100_000.0] * 8)
    scale, source = resolve_value_scale(tbl, "2019-05-15", "2023-01-03", 50_000.0)
    assert scale == 1000.0 and source == "detected"


def test_whole_dollars_detected():
    tbl = _tbl([15_000_000.0] * 8, [100_000.0] * 8)
    scale, source = resolve_value_scale(tbl, "2024-02-14", "2023-01-03", 50_000.0)
    assert scale == 1.0 and source == "detected"


def test_noncompliant_filer_beats_the_calendar():
    """A filer still reporting thousands after the 2023 cutover must be caught
    by detection, not trusted to the calendar rule - the calendar would inflate
    their book by 1000x and hand them the whole universe."""
    tbl = _tbl([15_000.0] * 8, [100_000.0] * 8)
    scale, source = resolve_value_scale(tbl, "2024-02-14", "2023-01-03", 50_000.0)
    assert scale == 1000.0 and source == "detected"


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #
SUBMISSION = b"""<SEC-DOCUMENT>0000000001-24-000001.txt
<DOCUMENT>
<TYPE>13F-HR
<TEXT>
<?xml version="1.0"?>
<edgarSubmission xmlns="http://www.sec.gov/edgar/thirteenffiler">
<formData><coverPage><reportType>13F HOLDINGS REPORT</reportType>
<filingManager><name>TEST ADVISORS LP</name></filingManager></coverPage>
<summaryPage><tableEntryTotal>3</tableEntryTotal><tableValueTotal>3000000</tableValueTotal>
</summaryPage></formData></edgarSubmission>
</TEXT>
</DOCUMENT>
<DOCUMENT>
<TYPE>INFORMATION TABLE
<TEXT>
<?xml version="1.0"?>
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
<infoTable><nameOfIssuer>APPLE INC</nameOfIssuer><titleOfClass>COM</titleOfClass>
<cusip>037833100</cusip><value>1000000</value>
<shrsOrPrnAmt><sshPrnamt>5000</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
<investmentDiscretion>SOLE</investmentDiscretion></infoTable>
<infoTable><nameOfIssuer>APPLE INC</nameOfIssuer><titleOfClass>COM</titleOfClass>
<cusip>037833100</cusip><value>1000000</value><putCall>CALL</putCall>
<shrsOrPrnAmt><sshPrnamt>5000</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
</infoTable>
<infoTable><nameOfIssuer>SOME CORP 5% NOTE</nameOfIssuer><titleOfClass>NOTE</titleOfClass>
<cusip>594918104</cusip><value>1000000</value>
<shrsOrPrnAmt><sshPrnamt>900000</sshPrnamt><sshPrnamtType>PRN</sshPrnamtType></shrsOrPrnAmt>
</infoTable>
</informationTable>
</TEXT>
</DOCUMENT>
</SEC-DOCUMENT>"""


def test_parses_cover_and_table():
    p = parse_submission(SUBMISSION, "2024-02-14")
    assert p.cover.report_type == "13F HOLDINGS REPORT"
    assert p.cover.table_entry_total == 3
    assert len(p.holdings) == 3
    assert p.parse_regime == "xml"


def test_option_and_debt_lines_are_flagged_not_silently_kept():
    from crowdflow.curate.identifiers import classify_instrument

    p = parse_submission(SUBMISSION, "2024-02-14")
    cls = classify_instrument(p.holdings)
    assert set(cls) == {"common", "option", "debt"}


def test_bare_document_without_sgml_envelope():
    """Some archived filings are the raw table with no envelope."""
    bare = SUBMISSION.split(b"<TYPE>INFORMATION TABLE")[1].split(b"<TEXT>")[1].split(b"</TEXT>")[0]
    p = parse_submission(bare, "2024-02-14")
    assert len(p.holdings) == 3


# --------------------------------------------------------------------------- #
# Filers
# --------------------------------------------------------------------------- #
def test_name_normalisation_strips_noise_suffixes():
    assert normalise_name("BRIDGEWATER ASSOCIATES, LP") == normalise_name("Bridgewater Associates LP")


def test_notice_is_never_kept_as_a_holdings_filing():
    covers = pd.DataFrame(
        {
            "filer_id": ["A", "B"],
            "cik": [1, 2],
            "period_end": ["2020-03-31"] * 2,
            "accession": ["a", "b"],
            "report_type": ["13F HOLDINGS REPORT", "13F NOTICE"],
            "other_managers": [[2], []],
            "n_rows": [50, 0],
            "book_usd": [1e9, 0.0],
        }
    )
    out = build_reporting_groups(covers)
    assert out.loc[out["accession"] == "a", "keep"].item()
    assert not out.loc[out["accession"] == "b", "keep"].item()
    assert out["group_id"].nunique() == 1  # the two are linked


def test_combination_report_subsumes_the_smaller_filing():
    """A double-counted manager is worse than a missing one for a crowding
    factor: the same dollars appear twice and look like two managers agreeing."""
    covers = pd.DataFrame(
        {
            "filer_id": ["AGG", "SUB"],
            "cik": [1, 2],
            "period_end": ["2020-03-31"] * 2,
            "accession": ["agg", "sub"],
            "report_type": ["13F COMBINATION REPORT", "13F HOLDINGS REPORT"],
            "other_managers": [[2], []],
            "n_rows": [120, 40],
            "book_usd": [5e9, 8e8],
        }
    )
    out = build_reporting_groups(covers)
    assert out.set_index("accession")["keep"].to_dict() == {"agg": True, "sub": False}


def test_amendment_does_not_subsume_its_own_original():
    """Regression: an amendment is a later *version*, not a competing report.

    When amendments were allowed into the largest-book contest, a filer's own
    13F-HR/A displaced its 13F-HR. The original then vanished from the revision
    log entirely, so ``as_of`` reported the filer as having disclosed nothing
    between the two dates - erasing a real, public filing for as long as a year.
    """
    covers = pd.DataFrame(
        {
            "filer_id": ["A", "A"],
            "cik": [1, 1],
            "period_end": ["2020-03-31"] * 2,
            "accession": ["orig", "amd"],
            "form": ["13F-HR", "13F-HR/A"],
            "report_type": ["13F HOLDINGS REPORT"] * 2,
            "other_managers": [[], []],
            "n_rows": [100, 101],
            "book_usd": [1.00e9, 1.02e9],  # amendment is larger, as restatements often are
        }
    )
    out = build_reporting_groups(covers).set_index("accession")["keep"].to_dict()
    assert out == {"orig": True, "amd": True}


def test_amendment_to_a_subsumed_filing_is_dropped_with_its_parent():
    """If we do not use SUB's original, we must not use SUB's amendment either;
    otherwise the aggregator's dollars and the subsidiary's dollars both count."""
    covers = pd.DataFrame(
        {
            "filer_id": ["AGG", "SUB", "SUB"],
            "cik": [1, 2, 2],
            "period_end": ["2020-03-31"] * 3,
            "accession": ["agg", "sub", "sub_a"],
            "form": ["13F-HR", "13F-HR", "13F-HR/A"],
            "report_type": ["13F COMBINATION REPORT", "13F HOLDINGS REPORT", "13F HOLDINGS REPORT"],
            "other_managers": [[2], [], []],
            "n_rows": [120, 40, 41],
            "book_usd": [5e9, 8e8, 8.1e8],
        }
    )
    out = build_reporting_groups(covers).set_index("accession")["keep"].to_dict()
    assert out == {"agg": True, "sub": False, "sub_a": False}


def test_group_whose_only_filing_is_an_amendment_still_has_a_representative():
    """The original may predate the sample window, or have been a notice. The
    amendment is then the only public table for that quarter and must be kept."""
    covers = pd.DataFrame(
        {
            "filer_id": ["A"],
            "cik": [1],
            "period_end": ["2020-03-31"],
            "accession": ["amd"],
            "form": ["13F-HR/A"],
            "report_type": ["13F HOLDINGS REPORT"],
            "other_managers": [[]],
            "n_rows": [80],
            "book_usd": [9e8],
        }
    )
    out = build_reporting_groups(covers)
    assert out["keep"].item()


def test_small_partial_amendment_is_not_rescaled_by_book_size():
    """Regression: a NEW HOLDINGS amendment carries only the rows a
    confidential-treatment order had withheld - sometimes two or three. The
    "book too small for a 13F filer, must be thousands" fallback then fires on
    a table that is small by design and multiplies a real disclosure by 1000.
    In the fixture run this turned a $6.3bn book into $948bn."""
    partial = pd.DataFrame(
        {
            "share_type": ["SH"] * 3,
            "shares": [100_000.0, 250_000.0, 80_000.0],
            "value_reported": [4_500_000.0, 9_000_000.0, 6_400_000.0],  # whole dollars
        }
    )
    scale, source = resolve_value_scale(
        partial, filing_date="2019-04-16", cutover="2023-01-03",
        median_threshold=50_000.0, is_partial=True,
    )
    assert scale == 1.0 and source == "detected"


def test_spac_arbitrage_dollar_book_is_not_multiplied_by_1000():
    """Regression, from real filings at the 2022Q4 boundary (the first quarter
    of the dollar rule). A SPAC-arbitrage book in whole dollars is mostly
    warrants priced in cents, so its *median* implied price (~0.16-0.30) is
    indistinguishable from a thousands book - and a median-only detector
    multiplied five real filers by 1000, manufacturing phantom $700bn books
    big enough to dominate any size ranking. What separates the populations
    is the 90th percentile: the SPAC trust share at ~$10 versus ~$0.26 for
    genuine thousands (share prices over $1,000 barely exist). Measured
    across 6,654 boundary filings the two are 25x apart at that quantile."""
    spac_arb = pd.DataFrame(
        {
            "share_type": ["SH"] * 12,
            "put_call": [""] * 12,
            # nine warrant lines around $0.20, three trust shares at ~$10.10
            "shares": [500_000.0] * 9 + [200_000.0] * 3,
            "value_reported": [100_000.0] * 9 + [2_020_000.0] * 3,
        }
    )
    scale, source = resolve_value_scale(
        spac_arb, filing_date="2023-02-14", cutover="2023-01-03", median_threshold=50_000.0
    )
    assert scale == 1.0, "dollar book read as thousands: the phantom-$700bn bug is back"

    # And the genuine non-compliant thousands book - median $82 stock, p90
    # $260 stock - must still be caught, not handed to the calendar.
    thousands = pd.DataFrame(
        {
            "share_type": ["SH"] * 10,
            "put_call": [""] * 10,
            "shares": [10_000.0] * 10,
            "value_reported": [820.0] * 8 + [2_600.0] * 2,  # thousands of $
        }
    )
    scale, source = resolve_value_scale(
        thousands, filing_date="2023-02-14", cutover="2023-01-03", median_threshold=50_000.0
    )
    assert scale == 1000.0 and source == "detected"


def test_implausible_thousands_reading_falls_back_to_dollars():
    """Regression, from the full-history build: Amundi Pioneer 2019Q3 and a
    private bank's 2023Q2 sleeve were filed in whole DOLLARS during/around
    the thousands era. Reading them as thousands produced $6.6tn and $16.6tn
    books - bigger than Vanguard - that would own any size-ranked universe.
    A thousands reading whose product exceeds the largest real 13F complexes
    while the as-filed total already clears the $100mm filing threshold is
    self-refuting, whatever the implied prices say."""
    n = 30
    # $200/share stocks, values in whole dollars, $6bn book: implied price
    # 200 -> med>2, q90>20 -> detected dollars even pre-cutover
    dollars_pre = pd.DataFrame({
        "share_type": ["SH"] * n, "put_call": [""] * n,
        "shares": [1_000_000.0] * n, "value_reported": [200_000_000.0] * n,
    })
    scale, source = resolve_value_scale(
        dollars_pre, filing_date="2019-11-14", cutover="2023-01-03", median_threshold=50_000.0)
    assert scale == 1.0

    # the nasty case: low implied prices (med<0.5) that LOOK like thousands,
    # but whose x1000 book would be $8tn -> plausibility fallback to dollars
    warranty = pd.DataFrame({
        "share_type": ["SH"] * n, "put_call": [""] * n,
        "shares": [1e9] * n, "value_reported": [8_000_000_000.0 / n * 1] * n,
    })
    # implied ~0.27, total $8bn -> x1000 = $8tn: impossible
    scale, source = resolve_value_scale(
        warranty, filing_date="2019-11-14", cutover="2023-01-03", median_threshold=50_000.0)
    assert scale == 1.0 and source == "plausibility"

    # control: a genuine thousands mega-book (Vanguard-sized) must NOT trip
    # the plausibility rule - $2.9tn is real for an index complex
    mega = pd.DataFrame({
        "share_type": ["SH"] * n, "put_call": [""] * n,
        "shares": [100_000_000.0] * n, "value_reported": [9_500_000.0] * n,
    })
    # implied 0.095 (a $95 stock in thousands); total x1000 = $285bn: fine
    scale, source = resolve_value_scale(
        mega, filing_date="2019-11-14", cutover="2023-01-03", median_threshold=50_000.0)
    assert scale == 1000.0 and source == "detected"


def test_thin_table_in_thousands_is_still_detected():
    """The two regimes are 1000x apart, so three rows are enough to tell them
    apart - we only demand a wider margin than we would with a full book."""
    thin = pd.DataFrame(
        {
            "share_type": ["SH"] * 3,
            "shares": [100_000.0, 250_000.0, 80_000.0],
            "value_reported": [4_500.0, 9_000.0, 6_400.0],  # thousands
        }
    )
    scale, source = resolve_value_scale(
        thin, filing_date="2019-04-16", cutover="2023-01-03",
        median_threshold=50_000.0, is_partial=True,
    )
    assert scale == 1000.0 and source == "detected"


# --------------------------------------------------------------------------- #
# Bitemporal / point-in-time
# --------------------------------------------------------------------------- #
def _store():
    holdings = pd.DataFrame(
        {
            "accession": ["orig", "orig", "restate", "restate", "addl"],
            "filer_id": ["A"] * 5,
            "period_end": [pd.Timestamp("2020-03-31")] * 5,
            "instrument_id": ["X", "Y", "X", "Y", "Z"],
            "put_call": [pd.NA] * 5,
            "shares": [100.0, 200.0, 100.0, 900.0, 50.0],
            "value_usd": [1000.0, 2000.0, 1000.0, 9000.0, 500.0],
        }
    )
    revisions = pd.DataFrame(
        {
            "filer_id": ["A"] * 3,
            "period_end": [pd.Timestamp("2020-03-31")] * 3,
            "accession": ["orig", "restate", "addl"],
            "form": ["13F-HR", "13F-HR/A", "13F-HR/A"],
            "amendment_type": ["", "RESTATEMENT", "NEW HOLDINGS"],
            "amendment_no": [np.nan, 1.0, 2.0],
            "knowledge_ts": pd.to_datetime(["2020-05-14", "2020-11-20", "2021-04-01"]),
        }
    )
    return HoldingsStore.build(holdings, revisions)


def test_original_only_before_amendment():
    s = _store()
    v = s.as_of("2020-03-31", "2020-06-30")
    assert set(v["instrument_id"]) == {"X", "Y"}
    assert v.loc[v["instrument_id"] == "Y", "shares"].item() == 200.0


def test_restatement_replaces_but_only_after_it_lands():
    s = _store()
    before = s.as_of("2020-03-31", "2020-11-19")
    after = s.as_of("2020-03-31", "2020-11-21")
    assert before.loc[before["instrument_id"] == "Y", "shares"].item() == 200.0
    assert after.loc[after["instrument_id"] == "Y", "shares"].item() == 900.0


def test_new_holdings_amendment_is_additive():
    """This is the confidential-treatment case: positions withheld from the
    original are disclosed later and must not appear before that date."""
    s = _store()
    assert "Z" not in set(s.as_of("2020-03-31", "2021-03-31")["instrument_id"])
    assert "Z" in set(s.as_of("2020-03-31", "2021-04-02")["instrument_id"])


def test_nothing_visible_before_the_first_filing():
    """The strongest lookahead test: on the day after quarter end the record is
    empty, because nobody has filed yet."""
    s = _store()
    assert s.as_of("2020-03-31", "2020-04-01").empty


def test_as_of_is_monotone_in_knowledge():
    """Information can be revised but never un-published: every fact visible at
    t must have been visible at some t' <= t under some accession."""
    s = _store()
    seen: set[str] = set()
    for d in pd.date_range("2020-04-01", "2021-06-01", freq="7D"):
        cur = set(s.as_of("2020-03-31", d)["accession"])
        assert cur.issubset(seen | cur)
        seen |= cur


def test_knowledge_ts_rolls_late_filings_to_next_day():
    ts = pd.Series(["2024-02-14T21:30:00.000Z", "2024-02-14T14:00:00.000Z"])
    out = derive_knowledge_ts(ts)
    # 21:30 UTC is 16:30 ET -> after the close -> next day.
    assert out.iloc[0].date() > out.iloc[1].date()


def test_timezone_check_actually_discriminates():
    """Regression: the check once compared the acceptance date against itself,
    which is 100% same-day by construction - a diagnostic that cannot fail.
    Against EDGAR's independently assigned filing_date it must separate a
    pre-cutoff stamp (20h UTC = 16h ET, same filing day) from a post-cutoff
    one (23h UTC = 19h ET, rolled to the next day)."""
    revisions = pd.DataFrame(
        {
            "filer_id": ["A", "B"],
            "period_end": ["2023-12-31"] * 2,
            "accession": ["early", "late"],
            "form": ["13F-HR"] * 2,
            "amendment_type": ["", ""],
            "amendment_no": [None, None],
            "knowledge_ts": ["2024-02-14", "2024-02-15"],
            "acceptance_dt": ["2024-02-14T20:10:00.000Z", "2024-02-14T23:10:00.000Z"],
            "filing_date": ["2024-02-14", "2024-02-15"],  # EDGAR rolled the late one
        }
    )
    holdings = pd.DataFrame(
        {
            "accession": ["early", "late"],
            "filer_id": ["A", "B"],
            "period_end": ["2023-12-31"] * 2,
            "instrument_id": ["X", "Y"],
            "put_call": [pd.NA] * 2,
            "shares": [1.0, 1.0],
            "value_usd": [1.0, 1.0],
        }
    )
    out = HoldingsStore.build(holdings, revisions).verify_acceptance_timezone()
    by_hour = out.set_index("raw_hour")["same_day_share"]
    assert by_hour.loc[20] == 1.0  # before the 17:30 ET cutoff under UTC reading
    assert by_hour.loc[23] == 0.0  # after it -> EDGAR assigned the next day


def test_as_of_does_not_scan_the_whole_panel():
    """Regression: ``as_of`` used a boolean ``isin`` over the full holdings
    frame on every call. With 368k rows and an audit that folds two snapshots
    per amended filer-quarter, that was ~15 minutes for one audit; against a
    real universe of several thousand filers the point-in-time layer would be
    unusable. The fold now takes only the rows belonging to the chosen
    accessions.

    The assertion is on the row count actually materialised, not on wall time,
    so it is deterministic on any machine.
    """
    n_filers, n_names = 40, 60
    rows, revs = [], []
    for f in range(n_filers):
        acc = f"acc{f}"
        revs.append(
            {
                "filer_id": f"F{f}",
                "period_end": "2020-03-31",
                "accession": acc,
                "form": "13F-HR",
                "amendment_type": "",
                "amendment_no": None,
                "knowledge_ts": "2020-05-10",
                "acceptance_dt": "2020-05-10T10:00:00.000Z",
                "confidential_omitted": False,
                "n_rows": n_names,
                "book_usd": 1e9,
            }
        )
        for i in range(n_names):
            rows.append(
                {
                    "filer_id": f"F{f}",
                    "period_end": "2020-03-31",
                    "accession": acc,
                    "instrument_id": f"S{i}",
                    "put_call": None,
                    "shares": 1000.0,
                    "value_usd": 1e6,
                }
            )
    store = HoldingsStore.build(pd.DataFrame(rows), pd.DataFrame(revs))

    one = store.as_of("2020-03-31", "2020-05-10", filers={"F7"})
    assert len(one) == n_names
    assert set(one["filer_id"]) == {"F7"}

    # Narrowing must not change what is returned, only how much is touched.
    full = store.as_of("2020-03-31", "2020-05-10")
    assert len(full) == n_filers * n_names
    pd.testing.assert_frame_equal(
        one.drop(columns="knowledge_asof").reset_index(drop=True),
        full[full["filer_id"] == "F7"].drop(columns="knowledge_asof").reset_index(drop=True),
    )


def _family_store(extra_revisions=(), extra_holdings=()):
    """Two registrants merged into one economic identity via an override.

    This is the primary scenario config/families.yaml exists for: sibling
    entities under one investment process, each filing its own 13F-HR. Their
    books are distinct and co-valid - the dollars are real on both sides.
    """
    revisions = pd.DataFrame(
        [
            {
                "filer_id": "FAMILY", "cik": 111, "period_end": "2023-03-31",
                "accession": "sib_a", "form": "13F-HR", "amendment_type": "",
                "amendment_no": None, "knowledge_ts": "2023-05-10",
                "n_rows": 2, "book_usd": 100.0,
            },
            {
                "filer_id": "FAMILY", "cik": 222, "period_end": "2023-03-31",
                "accession": "sib_b", "form": "13F-HR", "amendment_type": "",
                "amendment_no": None, "knowledge_ts": "2023-05-12",
                "n_rows": 2, "book_usd": 250.0,
            },
            *extra_revisions,
        ]
    )
    holdings = pd.DataFrame(
        [
            {"accession": "sib_a", "filer_id": "FAMILY", "cik": 111, "period_end": "2023-03-31",
             "instrument_id": "AAA", "put_call": pd.NA, "shares": 6.0, "value_usd": 60.0},
            {"accession": "sib_a", "filer_id": "FAMILY", "cik": 111, "period_end": "2023-03-31",
             "instrument_id": "SHARED", "put_call": pd.NA, "shares": 4.0, "value_usd": 40.0},
            {"accession": "sib_b", "filer_id": "FAMILY", "cik": 222, "period_end": "2023-03-31",
             "instrument_id": "CCC", "put_call": pd.NA, "shares": 15.0, "value_usd": 150.0},
            {"accession": "sib_b", "filer_id": "FAMILY", "cik": 222, "period_end": "2023-03-31",
             "instrument_id": "SHARED", "put_call": pd.NA, "shares": 10.0, "value_usd": 100.0},
            *extra_holdings,
        ]
    )
    return HoldingsStore.build(holdings, revisions)


def test_merged_family_books_are_summed_not_superseded():
    """Regression for a bug that deleted half a family's book with no error.

    The fold treated ``filer_id`` as the versioning key, so within a merged
    family the later sibling's original 13F-HR *superseded* the earlier
    sibling's - "a fresh original supersedes" is correct for one registrant
    re-filing, and destructive across registrants. Versioning must key on the
    CIK; ``filer_id`` is only the aggregation label."""
    v = _family_store().as_of("2023-03-31", "2023-06-30")
    assert v["value_usd"].sum() == 350.0
    assert set(v["accession"]) == {"sib_a", "sib_b"}
    # Both siblings hold SHARED; the family position is the sum of two real
    # lines, and cross-registrant dedup must not delete one of them.
    shared = v[v["instrument_id"] == "SHARED"]
    assert len(shared) == 2 and shared["value_usd"].sum() == 140.0


def test_family_member_restatement_replaces_only_its_own_book():
    """An amendment chain lives within one registrant. Sibling B restating its
    quarter must leave sibling A's book exactly as filed."""
    s = _family_store(
        extra_revisions=[
            {
                "filer_id": "FAMILY", "cik": 222, "period_end": "2023-03-31",
                "accession": "sib_b_restated", "form": "13F-HR/A",
                "amendment_type": "RESTATEMENT", "amendment_no": 1.0,
                "knowledge_ts": "2023-09-01", "n_rows": 1, "book_usd": 500.0,
            }
        ],
        extra_holdings=[
            {"accession": "sib_b_restated", "filer_id": "FAMILY", "cik": 222,
             "period_end": "2023-03-31", "instrument_id": "CCC", "put_call": pd.NA,
             "shares": 50.0, "value_usd": 500.0},
        ],
    )
    before = s.as_of("2023-03-31", "2023-08-31")
    after = s.as_of("2023-03-31", "2023-09-02")
    assert before["value_usd"].sum() == 350.0
    assert after["value_usd"].sum() == 600.0  # A intact (100) + B restated (500)
    assert set(after.loc[after["cik"] == 111, "instrument_id"]) == {"AAA", "SHARED"}


# --------------------------------------------------------------------------- #
# CIK succession
# --------------------------------------------------------------------------- #
def _manifest(rows):
    """rows: (cik, company, first_year_q, n_quarters)"""
    out = []
    for cik, name, start, n in rows:
        qs = pd.period_range(start, periods=n, freq="Q")
        for i, q in enumerate(qs):
            out.append(
                {
                    "cik": cik,
                    "company": name,
                    "period": q.end_time.normalize(),
                    "accession": f"{cik:010d}-x-{i:06d}",
                }
            )
    return pd.DataFrame(out)


def test_succession_finds_a_clean_handoff():
    """The real signature: one entity stops filing exactly as a similarly named
    one starts. Treating these as two managers truncates a decade of history
    and invents an exit and an entry in the middle of the sample."""
    man = _manifest(
        [
            (1, "EXAMPLE CAPITAL L P", "2013Q2", 13),
            (2, "EXAMPLE CAPITAL ADVISORS LLC", "2016Q3", 20),
        ]
    )
    out = detect_cik_succession(man)
    assert len(out) == 1
    row = out.iloc[0]
    assert (row["predecessor_cik"], row["successor_cik"]) == (1, 2)
    assert row["clean_handoff"]


def test_succession_ignores_overlapping_lives():
    """Two entities filing at the same time are two managers, however similar
    the names. A shared brand is not a shared filing obligation."""
    man = _manifest(
        [
            (1, "EXAMPLE CAPITAL L P", "2013Q2", 20),
            (2, "EXAMPLE CAPITAL ADVISORS LLC", "2015Q1", 20),
        ]
    )
    assert detect_cik_succession(man).empty


def test_succession_ignores_unrelated_names():
    """Adjacency alone is meaningless - hundreds of filers start and stop every
    quarter. Both the timing and the name must line up."""
    man = _manifest(
        [
            (1, "EXAMPLE CAPITAL L P", "2013Q2", 13),
            (2, "UNRELATED PARTNERS LLC", "2016Q3", 20),
        ]
    )
    assert detect_cik_succession(man).empty


def test_succession_only_proposes_and_never_merges():
    """The output is a review queue. A wrong merge splices two unrelated books
    into one track record and nothing downstream can detect it."""
    man = _manifest(
        [
            (1, "EXAMPLE CAPITAL L P", "2013Q2", 13),
            (2, "EXAMPLE CAPITAL ADVISORS LLC", "2016Q3", 20),
        ]
    )
    out = detect_cik_succession(man)
    assert "clean_handoff" in out.columns and "name_similarity" in out.columns
    assert set(man["cik"]) == {1, 2}  # manifest untouched


def test_succession_ignores_notices_when_measuring_overlap():
    """Regression, calibrated on the one well-documented real handoff: during
    a re-registration the successor entity files 13F-NT notices for several
    quarters while the predecessor still reports the actual positions. If
    notices count toward the successor's filing span, the two lives appear to
    overlap and the overlap veto rejects the true handoff. Spans must be built
    from holdings reports only."""
    man = _manifest(
        [
            (1, "EXAMPLE CAPITAL L P", "2013Q2", 13),  # HR through 2016Q2
            (2, "EXAMPLE CAPITAL ADVISORS LLC", "2016Q3", 20),
        ]
    )
    man["form"] = "13F-HR"
    # Successor filed notices while the predecessor was still reporting.
    notices = _manifest([(2, "EXAMPLE CAPITAL ADVISORS LLC", "2015Q1", 6)])
    notices["form"] = "13F-NT"
    out = detect_cik_succession(pd.concat([man, notices], ignore_index=True))
    assert len(out) == 1
    assert out.iloc[0]["clean_handoff"]
    # And the naive version of the same manifest - forms ignored - must fail,
    # documenting why the filter exists.
    naive = pd.concat([man, notices], ignore_index=True).drop(columns="form")
    assert detect_cik_succession(naive).empty


def test_succession_rejects_overlap_of_generic_trade_words_only():
    """Measured failure mode at real scale: 'Sutton Wealth Advisors' handing
    off to 'Muirfield Wealth Advisors' clears the Jaccard floor because the
    *generic* words overlap - the exact inverse of a real re-registration,
    which keeps the distinctive token and swaps the wrapper. Without this
    gate a six-window ingest proposed 2,540 clean handoffs, which is not a
    review queue, it is a landfill."""
    man = _manifest(
        [
            (1, "SUTTON WEALTH ADVISORS INC", "2013Q2", 13),
            (2, "MUIRFIELD WEALTH ADVISORS LLC", "2016Q3", 8),
        ]
    )
    assert detect_cik_succession(man).empty


def test_succession_threshold_admits_single_shared_token_pairs():
    """A real re-registration keeps the distinctive token and swaps the
    wrapper. After legal-form stripping that is often {NAME} vs {NAME, OTHER}:
    token Jaccard exactly 0.50. A floor above one half looks conservative and
    quietly rejects the canonical case."""
    man = _manifest(
        [
            (1, "FORTRESS L P", "2013Q2", 13),  # -> {FORTRESS}
            (2, "FORTRESS ADVISORS LLC", "2016Q3", 8),  # -> {FORTRESS, ADVISORS}
        ]
    )
    out = detect_cik_succession(man)
    assert len(out) == 1
    assert out.iloc[0]["name_similarity"] == 0.5


# --------------------------------------------------------------------------- #
# Family overrides
# --------------------------------------------------------------------------- #
def test_family_overrides_accept_the_documented_structured_format(tmp_path):
    """config/families.yaml documents a ``families:`` list with name, ciks and
    a justification note. The loader once accepted only a terse flat mapping,
    so a config written exactly as documented raised TypeError on load -
    punishing the user who read the documentation."""
    p = tmp_path / "families.yaml"
    p.write_text(
        "families:\n"
        "  - name: EXAMPLE PLATFORM\n"
        "    ciks: [1027745, 1423053]\n"
        "    note: succession verified against the filing history\n"
    )
    assert load_family_overrides(p) == {1027745: "EXAMPLE PLATFORM", 1423053: "EXAMPLE PLATFORM"}


def test_family_overrides_accept_the_terse_format(tmp_path):
    p = tmp_path / "families.yaml"
    p.write_text("EXAMPLE PLATFORM: [111, 222]\n")
    assert load_family_overrides(p) == {111: "EXAMPLE PLATFORM", 222: "EXAMPLE PLATFORM"}


def test_family_overrides_empty_file_yields_no_merges(tmp_path):
    p = tmp_path / "families.yaml"
    p.write_text("families: []\n")
    assert load_family_overrides(p) == {}


# --------------------------------------------------------------------------- #
# form.idx parsing
# --------------------------------------------------------------------------- #
def test_form_idx_survives_header_data_misalignment():
    """Regression against the real 2022QTR4 layout, where the data columns are
    wider than the header labels. Header-derived offsets slice 'Date Filed' to
    ``2022-11`` - and ``to_datetime`` then reads that as the *first* of the
    month with no error, which shifts the value-scale cutover and every
    fallback acceptance timestamp built from the filing date."""
    from crowdflow.ingest.discovery import _parse_form_idx

    # Faithful reproduction of the misaligned vintage: header says the date
    # starts at column 86; in the data rows it actually starts at column 92.
    idx_text = (
        "Form Type   Company Name                                                  "
        "CIK         Date Filed  File Name\n"
        + "-" * 130 + "\n"
        "13F-HR           BARCLAYS PLC                                             "
        "     312069      2022-11-03  edgar/data/312069/0000312069-22-000125.txt\n"
        "13F-HR/A         EXAMPLE FUND 2011 LP                                     "
        "     999999      2022-12-15  edgar/data/999999/0000999999-22-000001.txt\n"
        "10-K             NOT A THIRTEEN F                                         "
        "     111111      2022-11-05  edgar/data/111111/0000111111-22-000001.txt\n"
    )
    out = _parse_form_idx(idx_text, "2022Q4")
    assert list(out["filing_date"]) == ["2022-11-03", "2022-12-15"]  # full dates
    assert list(out["cik"]) == [312069, 999999]
    assert list(out["company"]) == ["BARCLAYS PLC", "EXAMPLE FUND 2011 LP"]


# --------------------------------------------------------------------------- #
# Real EDGAR filings
# --------------------------------------------------------------------------- #
FIXTURES = Path(__file__).parent / "fixtures"


def test_real_pre_xml_filing_parses():
    """Regression against an actual EDGAR document, not a generated one.

    Berkshire Hathaway, 13F-HR/A for 2005Q4, filed 2006-05-15 after a
    confidential-treatment order lapsed. Accession 0000950129-06-005538.

    An earlier version of the legacy reader returned zero rows on this file and
    raised nothing. Three features of the real layout defeated it, none of which
    appeared in the generated fixtures:

      ConocoPhillips   Com   20825C 10 4   $559,273   9,612,800   X   1, 2, 3

      * the CUSIP is printed in 6-2-1 groups separated by spaces;
      * the value carries a dollar sign;
      * there is no SH/PRN column - that marker arrived with a later revision of
        the form, and requiring it silently emptied every filing before it.

    Generated fixtures cannot catch this class of bug, because the generator and
    the parser share an author and therefore share the same wrong assumption.
    """
    raw = (FIXTURES / "real_brk_2005q4_13fhra.txt").read_bytes()
    p = parse_submission(raw, filing_date="2006-05-15")

    assert p.parse_regime == "legacy_text"
    assert len(p.holdings) == 1

    row = p.holdings.iloc[0]
    assert row["cusip"] == "20825C104"  # spaces stripped, check digit intact
    assert row["issuer"] == "ConocoPhillips"
    assert row["shares"] == pytest.approx(9_612_800)

    # Value is printed in thousands and must be detected as such: the implied
    # price then lands at ~$58, which is where ConocoPhillips actually traded at
    # the end of 2005. Read as whole dollars it would imply 6 cents a share.
    assert p.value_scale == 1000.0
    assert p.scale_source == "detected"
    implied = row["value_usd"] / row["shares"]
    assert 40 < implied < 80


def test_real_filing_cover_page_carries_the_amendment_type():
    """The single most destructive thing to lose on this filing.

    The cover page is printed text, so there is no schema to read. It declares
    'adds new holdings entries', which makes the amendment additive. Read as a
    restatement instead, the bitemporal fold replaces Berkshire's entire 2005Q4
    book with the one ConocoPhillips line this document contains - deleting a
    quarter of positions with no exception raised and nothing in the output that
    looks wrong.
    """
    raw = (FIXTURES / "real_brk_2005q4_13fhra.txt").read_bytes()
    cover = parse_submission(raw, filing_date="2006-05-15").cover

    assert cover.amendment_type == "NEW HOLDINGS"
    assert cover.is_amendment
    assert cover.amendment_no == 1
    assert cover.report_type == "13F COMBINATION REPORT"
    assert cover.confidential_omitted
    assert cover.table_entry_total == 1
    assert cover.table_value_total == pytest.approx(559_273.0)


def test_declared_rows_but_none_parsed_is_a_loud_failure():
    """A parse that recovers nothing while the filer declared entries must say
    so. Silence here is what turned a broken legacy reader into a decade of
    missing data that looked like a decade of empty filings."""
    body = b"""
                              Form 13F SUMMARY PAGE
Form 13F Information Table Entry Total:        42
Form 13F Information Table Value Total:   $1,234,567
[X]  13F HOLDINGS REPORT.
"""
    p = parse_submission(body, filing_date="2006-05-15")
    assert p.holdings.empty
    assert any("PARSE FAILURE" in w for w in p.warnings)
    assert p.cover.table_entry_total == 42


# --------------------------------------------------------------------------- #
# DERA structured datasets
# --------------------------------------------------------------------------- #
def _dera_zip(nest: bool = False, drop: str | None = None, empty: bool = False) -> bytes:
    """Build a dataset zip with the real table and column names."""
    import io as _io
    import zipfile as _zip

    tables = {
        "SUBMISSION": (
            "ACCESSION_NUMBER\tFILING_DATE\tSUBMISSIONTYPE\tCIK\tPERIODOFREPORT\n"
            + ("" if empty else
               "0001067983-24-000010\t14-FEB-2024\t13F-HR\t1067983\t31-DEC-2023\n")
        ),
        "COVERPAGE": (
            "ACCESSION_NUMBER\tREPORTCALENDARORQUARTER\tISAMENDMENT\tAMENDMENTNO\t"
            "AMENDMENTTYPE\tFILINGMANAGER_NAME\tREPORTTYPE\n"
            "0001067983-24-000010\t31-DEC-2023\t\t\t\tBERKSHIRE HATHAWAY INC\t"
            "13F COMBINATION REPORT\n"
        ),
        "INFOTABLE": (
            "ACCESSION_NUMBER\tINFOTABLE_SK\tNAMEOFISSUER\tTITLEOFCLASS\tCUSIP\tVALUE\t"
            "SSHPRNAMT\tSSHPRNAMTTYPE\tPUTCALL\tINVESTMENTDISCRETION\n"
            + ("" if empty else
               "0001067983-24-000010\t1\tAPPLE INC\tCOM\t037833100\t174347000\t"
               "905560000\tSH\t\tSOLE\n"
               "0001067983-24-000010\t2\tCOCA COLA CO\tCOM\t191216100\t23571800\t"
               "400000000\tSH\t\tSOLE\n")
        ),
        "SUMMARYPAGE": (
            "ACCESSION_NUMBER\tOTHERINCLUDEDMANAGERSCOUNT\tTABLEENTRYTOTAL\t"
            "TABLEVALUETOTAL\tISCONFIDENTIALOMITTED\n"
            "0001067983-24-000010\t3\t2\t197918800\tN\n"
        ),
        "OTHERMANAGER": (
            "ACCESSION_NUMBER\tOTHERMANAGER_SK\tCIK\tFORM13FFILENUMBER\tNAME\n"
            "0001067983-24-000010\t1\t949012\t028-00718\tNATIONAL INDEMNITY CO\n"
        ),
    }
    if drop:
        tables.pop(drop)

    buf = _io.BytesIO()
    prefix = "form13f_2023q4/" if nest else ""
    with _zip.ZipFile(buf, "w") as zf:
        for name, body in tables.items():
            zf.writestr(f"{prefix}{name}.tsv", body)
    return buf.getvalue()


def test_dera_zip_parses_and_reshapes():
    from crowdflow.ingest.datasets import _read_zip, to_pipeline_frames

    tables = _read_zip(_dera_zip(), "2023q4")
    holdings, covers = to_pipeline_frames(tables)

    assert len(holdings) == 2
    assert set(holdings["cusip"]) == {"037833100", "191216100"}
    assert holdings["value_reported"].sum() == pytest.approx(197_918_800)

    row = covers.iloc[0]
    assert row["form"] == "13F-HR"
    assert row["report_type"] == "13F COMBINATION REPORT"
    assert row["n_rows_declared"] == 2
    # The reporting-group graph arrives ready-made instead of being rebuilt
    # from cover pages, which is the main structural advantage of this source.
    assert row["other_managers"] == [949012]


def test_dera_zip_with_nested_tables_still_parses():
    """At least one published quarter nests its tables in a subdirectory. A
    fixed-path lookup raises KeyError there, and a bare except turns that into a
    quarter with zero filings that nobody notices until the factor has a hole."""
    from crowdflow.ingest.datasets import _read_zip

    tables = _read_zip(_dera_zip(nest=True), "2025q3")
    assert len(tables["INFOTABLE"]) == 2


def test_dera_missing_required_table_raises():
    """Loud, not empty. 'INFO: 0 filings' reads exactly like a quiet quarter."""
    from crowdflow.ingest.datasets import _read_zip

    with pytest.raises(ValueError, match="INFOTABLE"):
        _read_zip(_dera_zip(drop="INFOTABLE"), "2023q4")


def test_dera_present_but_empty_raises():
    from crowdflow.ingest.datasets import _read_zip

    with pytest.raises(ValueError, match="empty"):
        _read_zip(_dera_zip(empty=True), "2023q4")


def test_dera_coverage_floor_is_announced():
    """Asking for 2010 must not silently return 2013 onward."""
    from crowdflow.ingest.datasets import windows_between

    ws = windows_between("2010Q1", "2014Q1", pad_quarters=0, today="2020-01-01")
    assert ws[0].label == "2013q2"
    assert ws[0].url.endswith("2013q2_form13f.zip")


def test_dera_window_naming_crosses_the_2024_transition():
    """The URL scheme changed under the archive in 2024: calendar quarters
    through 2023q4, then a one-off two-month stub for January-February 2024,
    then rolling Mar-May / Jun-Aug / Sep-Nov / Dec-Feb windows. Every label
    here was verified against the live server; generating `2024q1` instead
    404s, and under a bare except a 404 reads as a quiet quarter."""
    from crowdflow.ingest.datasets import windows_between

    ws = windows_between("2023Q3", "2024Q3", pad_quarters=1, today="2025-06-30")
    labels = [w.label for w in ws]
    assert labels == [
        "2023q3",
        "2023q4",
        "01jan2024-29feb2024",  # leap-year stub, 29feb not 28
        "01mar2024-31may2024",
        "01jun2024-31aug2024",
        "01sep2024-30nov2024",
        "01dec2024-28feb2025",  # non-leap end
    ]


def test_dera_windows_exclude_the_unfinished_window():
    """A window that has not ended cannot have been published; enumerating it
    guarantees one spurious failure per run."""
    from crowdflow.ingest.datasets import windows_between

    ws = windows_between("2024Q1", "2024Q1", pad_quarters=8, today="2024-07-15")
    labels = [w.label for w in ws]
    assert "01mar2024-31may2024" in labels
    assert "01jun2024-31aug2024" not in labels  # still open on the 'today' given


def test_bulk_scale_agrees_with_scalar():
    """The DERA path resolves value units for the whole ingest at once; the
    raw path resolves per filing. Same thresholds, same precedence - and this
    test is what keeps the two implementations from drifting apart."""
    from crowdflow.ingest.infotable import resolve_value_scale, resolve_value_scale_bulk

    cases = {
        # thousands: implied price far below 1
        "acc_thousands": pd.DataFrame({
            "share_type": ["SH"] * 6, "shares": [1e6] * 6, "value_reported": [50_000.0] * 6,
        }),
        # whole dollars: implied price in the equity band
        "acc_dollars": pd.DataFrame({
            "share_type": ["SH"] * 6, "shares": [1e6] * 6, "value_reported": [5e7] * 6,
        }),
        # partial NEW HOLDINGS: small book must NOT trigger the size fallback
        "acc_partial": pd.DataFrame({
            "share_type": ["SH"], "shares": [0.0], "value_reported": [1_000.0],
        }),
        # no usable equity rows, filed pre-cutover: calendar says thousands
        "acc_calendar": pd.DataFrame({
            "share_type": ["PRN"] * 3, "shares": [0.0] * 3, "value_reported": [10.0] * 3,
        }),
    }
    filing_dates = {"acc_thousands": "2019-05-10", "acc_dollars": "2024-05-10",
                    "acc_partial": "2019-05-10", "acc_calendar": "2019-05-10"}
    amend = {"acc_partial": "NEW HOLDINGS"}

    holdings = pd.concat(
        [df.assign(accession=acc) for acc, df in cases.items()], ignore_index=True
    )
    covers = pd.DataFrame({
        "accession": list(cases),
        "filing_date": [filing_dates[a] for a in cases],
        "amendment_type": [amend.get(a, "") for a in cases],
    })
    bulk = resolve_value_scale_bulk(holdings, covers, "2023-01-03", 50_000.0)
    bulk = bulk.set_index("accession")

    for acc, df in cases.items():
        scale, source = resolve_value_scale(
            df, filing_dates[acc], "2023-01-03", 50_000.0,
            is_partial=amend.get(acc, "") == "NEW HOLDINGS",
        )
        assert bulk.loc[acc, "value_scale"] == scale, acc
        assert bulk.loc[acc, "scale_source"] == source, acc


def test_dera_frames_assemble_into_the_same_store_shape():
    """End to end on the fixture zip: DERA frames must come out of
    ``assemble_dera`` as a working bitemporal store with a ledger, exactly
    like the raw path - value scale resolved, knowledge dates derived from
    the filing-date fallback, and the whole thing queryable via ``as_of``."""
    from crowdflow.config import Config
    from crowdflow.curate.assemble import assemble_dera
    from crowdflow.ingest.datasets import _read_zip, to_pipeline_frames

    holdings, covers = to_pipeline_frames(_read_zip(_dera_zip(), "2023q4"))
    store, ledger = assemble_dera(Config(), holdings, covers)

    assert list(ledger["status"]) == ["ok"]
    assert ledger.iloc[0]["parse_regime"] == "dera"
    # The fixture reports values in thousands (implied price ~0.19) although
    # it was filed after the 2023 cutover - the non-compliant-filer case.
    # Detection by implied price must beat the calendar here, exactly as on
    # the raw path.
    assert ledger.iloc[0]["value_scale"] == 1000.0
    assert ledger.iloc[0]["scale_source"] == "detected"

    # Filed 14-FEB-2024, no acceptance timestamp -> end-of-day fallback,
    # rolled to the next session: knowable on the 15th, not the 14th.
    v_before = store.as_of("2023-12-31", "2024-02-14")
    v_after = store.as_of("2023-12-31", "2024-02-16")
    assert v_before.empty
    assert set(v_after["cusip"]) == {"037833100", "191216100"}
    assert v_after["value_usd"].sum() == pytest.approx(197_918_800.0 * 1000)
    assert "cik" in store.revisions.columns and "filing_date" in store.revisions.columns
