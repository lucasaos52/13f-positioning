"""Discovery of 13F filings and their *acceptance* timestamps.

Two-stage crawl, chosen to minimise requests against EDGAR:

Stage 1 - quarterly ``form.idx`` full indices. One request per calendar quarter
returns every filing of every form type accepted in that quarter. We keep the
13F-HR / 13F-HR/A / 13F-NT rows. This tells us *which* CIKs to care about
without touching a single filing.

Stage 2 - the per-CIK submissions JSON on ``data.sec.gov``. One request per
filer returns its whole filing history including ``acceptanceDateTime``, which
is the field that actually matters for point-in-time work and which is *absent*
from the full index.

Why acceptance time rather than filing date: EDGAR deems anything accepted after
17:30 ET to be filed on the next business day, so ``filingDate`` is a rounded,
sometimes forward-shifted proxy. We keep both and derive a conservative
``knowledge_date`` downstream.

Note that the index quarter is the quarter of *filing*, not of the reported
period. A 2019Q4 position report filed in Feb 2020 lives in the 2020Q1 index,
and a restatement of it may live in the 2021Q3 index. The crawl window is
therefore widened on both ends.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

import pandas as pd

from .client import EDGAR_BASE, EDGAR_DATA, EdgarClient, OfflineFetchError

log = logging.getLogger(__name__)

THIRTEEN_F_FORMS = {"13F-HR", "13F-HR/A", "13F-NT", "13F-NT/A"}
_ACCESSION_RE = re.compile(r"(\d{10})-?(\d{2})-?(\d{6})")


@dataclass(frozen=True)
class FilingRef:
    """A single 13F submission, before its contents are read."""

    cik: int
    accession: str  # dashed form, 0001067983-24-000010
    form: str
    period: str  # 'YYYY-MM-DD' quarter end as reported
    filing_date: str
    acceptance_dt: str  # ISO 8601 with time, ET
    company: str

    @property
    def nodash(self) -> str:
        return self.accession.replace("-", "")

    @property
    def submission_url(self) -> str:
        """Full SGML submission: cover page and information table in one file.

        Fetching this instead of the individual documents halves or thirds the
        request count, which is the binding constraint on a full history crawl.
        """
        return f"{EDGAR_BASE}/Archives/edgar/data/{self.cik}/{self.nodash}/{self.accession}.txt"

    @property
    def report_quarter(self) -> str:
        d = pd.Timestamp(self.period)
        return f"{d.year}Q{d.quarter}"


def quarter_range(first: str, last: str, pad_back: int = 0, pad_fwd: int = 0) -> list[str]:
    """Inclusive list of 'YYYYQn' labels, optionally padded on both ends."""
    a = pd.Period(first.replace("Q", "-Q"), freq="Q") - pad_back
    b = pd.Period(last.replace("Q", "-Q"), freq="Q") + pad_fwd
    return [f"{p.year}Q{p.quarter}" for p in pd.period_range(a, b, freq="Q")]


def _normalise_accession(raw: str) -> str:
    m = _ACCESSION_RE.search(raw)
    if not m:
        raise ValueError(f"unparseable accession: {raw!r}")
    return "-".join(m.groups())


# --------------------------------------------------------------------------- #
# Stage 1
# --------------------------------------------------------------------------- #
def crawl_form_index(client: EdgarClient, quarters: list[str]) -> pd.DataFrame:
    """Return every 13F row across the given *filing* quarters."""
    frames = []
    for q in quarters:
        year, qtr = q.split("Q")
        url = f"{EDGAR_BASE}/Archives/edgar/full-index/{year}/QTR{qtr}/form.idx"
        try:
            text = client.get_text(url)
        except (FileNotFoundError, OfflineFetchError):
            # No index for this quarter: either it is in the future, or we are
            # offline and no filing in the fixture set was accepted then.
            log.debug("no full index available for %s", q)
            continue
        frames.append(_parse_form_idx(text, q))
    if not frames:
        return pd.DataFrame(columns=["form", "company", "cik", "filing_date", "path", "index_quarter"])
    out = pd.concat(frames, ignore_index=True)
    return out[out["form"].isin(THIRTEEN_F_FORMS)].reset_index(drop=True)


_IDX_TAIL = re.compile(r"(\d+)\s+(\d{4}-\d{2}-\d{2})\s+(\S+)\s*$")


def _parse_form_idx(text: str, index_quarter: str) -> pd.DataFrame:
    """``form.idx`` is nominally fixed-width with a dashed rule under the header.

    The obvious reader - column offsets taken from the header labels - is
    wrong on real vintages: at least 2022QTR4 lays the data columns wider than
    the header, so the "Date Filed" slice lands three characters short and
    yields ``2022-11`` instead of ``2022-11-03``. That truncation is invisible
    downstream because ``to_datetime`` happily reads a bare year-month as the
    first of the month - and the filing date feeds the value-scale cutover,
    where "filed 2023-01-01" versus "filed 2023-01-20" changes the answer.

    So only the form type is read positionally (it starts at column zero).
    The CIK, date and path are anchored to the line's *tail* by pattern -
    integer, full ISO date, path - which no width drift can shift, and the
    company name is whatever sits between the form and the CIK.
    """
    lines = text.splitlines()
    rule = next((i for i, ln in enumerate(lines) if set(ln.strip()) == {"-"}), None)
    if rule is None or rule == 0:
        return pd.DataFrame()

    rows = []
    for ln in lines[rule + 1 :]:
        form, _, rest = ln.partition("  ")
        form = form.strip()
        if form not in THIRTEEN_F_FORMS:
            continue
        m = _IDX_TAIL.search(rest)
        if not m:
            continue
        cik, filed, path = m.groups()
        rows.append(
            {
                "form": form,
                "company": rest[: m.start()].strip(),
                "cik": int(cik),
                "filing_date": filed,
                "path": path,
                "index_quarter": index_quarter,
            }
        )
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Stage 2
# --------------------------------------------------------------------------- #
def fetch_submission_history(client: EdgarClient, cik: int) -> pd.DataFrame:
    """All 13F submissions for one CIK, with acceptance timestamps."""
    url = f"{EDGAR_DATA}/submissions/CIK{cik:010d}.json"
    try:
        blob = json.loads(client.get_text(url))
    except (FileNotFoundError, OfflineFetchError):
        log.warning("no submissions record for CIK %d", cik)
        return pd.DataFrame()

    company = blob.get("name", "")
    chunks = [blob.get("filings", {}).get("recent", {})]

    # Filers with long histories are paginated into extra JSON shards.
    for extra in blob.get("filings", {}).get("files", []):
        shard_url = f"{EDGAR_DATA}/submissions/{extra['name']}"
        try:
            chunks.append(json.loads(client.get_text(shard_url)))
        except (FileNotFoundError, OfflineFetchError):
            continue

    rows = []
    for chunk in chunks:
        forms = chunk.get("form", [])
        for i, form in enumerate(forms):
            if form not in THIRTEEN_F_FORMS:
                continue
            rows.append(
                {
                    "cik": cik,
                    "company": company,
                    "form": form,
                    "accession": chunk["accessionNumber"][i],
                    "period": chunk["reportDate"][i],
                    "filing_date": chunk["filingDate"][i],
                    "acceptance_dt": chunk["acceptanceDateTime"][i],
                }
            )
    return pd.DataFrame(rows)


def build_manifest(client: EdgarClient, quarters: list[str], ciks: list[int] | None = None) -> pd.DataFrame:
    """Full manifest of 13F submissions with acceptance times.

    Falls back to the full-index ``filing_date`` (as an end-of-day timestamp)
    for any submission the API does not return, so the manifest never silently
    loses a filing.
    """
    idx = crawl_form_index(client, quarters)
    if idx.empty:
        return pd.DataFrame(columns=[f.name for f in FilingRef.__dataclass_fields__.values()])

    target = sorted(set(ciks) if ciks else set(idx["cik"]))
    # Filter the index to the target CIKs *before* the merge. Without this the
    # left-join filtered implicitly and the "filings lack a report period"
    # warning counted every out-of-scope row - tens of thousands on a smoke
    # test - drowning the case where that warning matters: a targeted CIK
    # whose submissions record genuinely failed to come back.
    idx = idx[idx["cik"].isin(set(target))].reset_index(drop=True)
    log.info("discovered %d 13F rows across %d filers", len(idx), len(target))

    hist = [h for cik in target if not (h := fetch_submission_history(client, cik)).empty]
    api = pd.concat(hist, ignore_index=True) if hist else pd.DataFrame()

    if not api.empty:
        api["accession"] = api["accession"].map(_normalise_accession)
        api = api.drop_duplicates(subset=["accession"])

    idx["accession"] = idx["path"].str.extract(r"(\d{10}-\d{2}-\d{6})", expand=False)
    idx = idx.dropna(subset=["accession"])

    if api.empty:
        merged = idx.assign(period=pd.NA, acceptance_dt=idx["filing_date"] + "T23:59:59.000Z")
    else:
        merged = idx.merge(
            api[["accession", "period", "acceptance_dt", "form", "company"]],
            on="accession",
            how="left",
            suffixes=("_idx", ""),
        )
        merged["form"] = merged["form"].fillna(merged["form_idx"])
        merged["company"] = merged["company"].fillna(merged["company_idx"])
        merged["acceptance_dt"] = merged["acceptance_dt"].fillna(merged["filing_date"] + "T23:59:59.000Z")

    keep = ["cik", "accession", "form", "period", "filing_date", "acceptance_dt", "company"]
    merged = merged.reindex(columns=keep)
    missing_period = merged["period"].isna().sum()
    if missing_period:
        log.warning("%d filings lack a report period and will be dropped", missing_period)
    return merged.dropna(subset=["period"]).drop_duplicates("accession").reset_index(drop=True)
