"""Build an auditable ETF identity table from 13F CUSIPs.

The curated 13F ``instrument_class`` is intentionally not an identity source:
it mixes ETFs with closed-end funds, BDCs and ordinary shares.  CUSIP is the
anchor here.  OpenFIGI supplies the CUSIP-to-ticker bridge, while the SEC
Form N-CEN and the Nasdaq symbol directories supply independent regulatory
and exchange ETF labels.  A text match can nominate a candidate but can never
promote it into the confirmed universe by itself.

The module keeps raw downloads and OpenFIGI responses on disk.  That is both a
speed feature (the public unauthenticated API is deliberately rate limited)
and a research invariant: every final flag can be traced to the exact source
observation that produced it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import time
from typing import Callable, Iterable
from urllib.parse import urljoin
from urllib.request import Request, urlopen
import zipfile

import numpy as np
import pandas as pd


SEC_NCEN_PAGE = "https://www.sec.gov/data-research/sec-markets-data/form-n-cen-data-sets"
SEC_SERIES_PAGE = (
    "https://www.sec.gov/data-research/sec-markets-data/"
    "investment-company-series-class-information"
)
NASDAQ_URLS = {
    "nasdaqlisted.txt": "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
    "otherlisted.txt": "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt",
}
OPENFIGI_MAPPING_URL = "https://api.openfigi.com/v3/mapping"
DEFAULT_USER_AGENT = "ETF positioning research contact lsilva@example.com"


_FIXED_INCOME = re.compile(
    r"\b(?:BOND|TREASUR(?:Y|IES)|MUNICIPAL|MUNI|FIXED[ -]INCOME|HIGH[ -]YIELD|"
    r"CORPORATE[ -]BOND|AGGREGATE[ -]BOND|MBS|MORTGAGE|FLOATING[ -]RATE|"
    r"SENIOR[ -]LOAN|BANK[ -]LOAN|CLO|DURATION|TIPS|T[ -]?BILL|DEBT|CREDIT|"
    r"PREFERRED|CONVERTIBLE[ -]SECURIT(?:Y|IES)|INFLATION[ -]PROTECTED|SHORT[ -]MATURITY|"
    r"ULTRA[ -]SHORT|TERM[ -]CORPORATE|CORE[ -]PLUS[ -]INCOME|MONEY[ -]MARKET|"
    r"GOVERNMENT[ -]BOND)\b",
    re.IGNORECASE,
)
_COMMODITY = re.compile(
    r"\b(?:COMMODIT(?:Y|IES)|GOLD|SILVER|PALLADIUM|PLATINUM|COPPER|URANIUM|"
    r"CRUDE|OIL|NATURAL[ -]GAS|AGRICULTUR(?:E|AL))\b",
    re.IGNORECASE,
)
_CRYPTO = re.compile(r"\b(?:BITCOIN|ETHER(?:EUM)?|CRYPTO|BLOCKCHAIN)\b", re.IGNORECASE)
_VOLATILITY = re.compile(r"\b(?:VIX|VOLATILITY|TAIL[ -]RISK)\b", re.IGNORECASE)
_EQUITY = re.compile(
    r"\b(?:EQUITY|EQUITIES|STOCK|S&P|RUSSELL|MSCI|NASDAQ|DOW[ -]JONES|"
    r"FTSE|STOXX|CSI|ALL[ -]WORLD|DEVELOPED[ -](?:MARKETS?|WORLD)|"
    r"EMERGING[ -]MARKETS?|BROAD[ -]MARKET|EXTENDED[ -]MARKET|"
    r"EUROPE|JAPAN|INDIA|CHINA|LATIN[ -]AMERICA|EX[ -]?US|GLOBAL[ -]100|"
    r"LARGE[ -]CAP|MID[ -]CAP|SMALL[ -]CAP|MICRO[ -]CAP|VALUE|GROWTH|DIVIDEND|"
    r"TECHNOLOG(?:Y|IES)|TECH|SEMICONDUCTOR|BIOTECH(?:NOLOGY)?|HEALTH(?:CARE)?|"
    r"FINANCIALS?|ENERGY|INDUSTRIALS?|MATERIALS?|CONSUMER|UTILIT(?:Y|IES)|"
    r"REAL[ -]ESTATE|REIT|MEGA[ -]?CAP|LARGE[ -]?CAP|MID[ -]?CAP|SMALL[ -]?CAP|"
    r"COMMUNICATION|AEROSPACE|DEFENSE|SOFTWARE|INFRASTRUCTURE|MEDICAL|"
    r"HOME[ -]CONSTRUCTION|BANKS?|TRANSPORTATION|NATURAL[ -]RESOURCES|MLP|"
    r"WATER|PROFITABILITY|MOAT|EARNINGS|BUYBACK|CAPITAL[ -]STRENGTH|"
    r"COMPAN(?:Y|IES)|ENTERPRISES?)\b",
    re.IGNORECASE,
)
_EQUITY_OVERRIDE = re.compile(
    r"\b(?:EQUITY|EQUITIES|STOCK|MINERS?|MINING|PRODUCERS?|EXPLORATION|"
    r"SEMICONDUCTOR|BIOTECH(?:NOLOGY)?|TECHNOLOG(?:Y|IES)|HEALTH(?:CARE)?|"
    r"FINANCIALS?|INDUSTRIALS?|"
    r"CONSUMER|REAL[ -]ESTATE|REIT)\b",
    re.IGNORECASE,
)
_LEVERAGED_STRONG = re.compile(
    r"(?:\b(?:2X|3X|ULTRAPRO|ULTRASHORT|INVERSE|BEAR|LEVERAGED)\b|[- ](?:2|3)X\b)",
    re.IGNORECASE,
)
_DURATION_SHORT = re.compile(
    r"\b(?:ULTRA[ -]SHORT|SHORT[ -]TERM|SHORT[ -]MATURITY)\b", re.IGNORECASE
)
_DIRECTIONAL_SHORT = re.compile(r"\b(?:ULTRA|SHORT)\b", re.IGNORECASE)
_SECTOR = re.compile(
    r"\b(?:TECHNOLOG(?:Y|IES)|TECH|SEMICONDUCTOR|BIOTECH(?:NOLOGY)?|"
    r"HEALTH(?:CARE)?|FINANCIALS?|ENERGY|INDUSTRIALS?|MATERIALS?|CONSUMER|"
    r"UTILIT(?:Y|IES)|REAL[ -]ESTATE|REIT|"
    r"COMMUNICATION)\b",
    re.IGNORECASE,
)
_FACTOR = re.compile(
    r"\b(?:QUALITY|MOMENTUM|MIN(?:IMUM)?[ -]VOLATILITY|LOW[ -]VOLATILITY|"
    r"VALUE|GROWTH|DIVIDEND|EQUAL[ -]WEIGHT|MULTI[ -]FACTOR|PROFITABILITY|"
    r"RAFI|MOAT|EARNINGS|BUYBACK|FUNDAMENTAL|CAPITAL[ -]STRENGTH)\b",
    re.IGNORECASE,
)
_THEMATIC = re.compile(
    r"\b(?:CLEAN[ -]ENERGY|SOLAR|ROBOT|CYBER|GENOMIC|INNOVATION|CANNABIS|"
    r"ARTIFICIAL[ -]INTELLIGENCE|CLOUD|LITHIUM|URANIUM|SPACE|FINTECH)\b",
    re.IGNORECASE,
)
_BROAD = re.compile(
    r"\b(?:S&P[ -]?500|TOTAL[ -](?:STOCK|MARKET)|RUSSELL[ -]?(?:1000|2000|3000)|"
    r"MSCI[ -]?(?:USA|WORLD|ACWI|EAFE)|BROAD[ -]MARKET|DOW[ -]JONES[ -]INDUSTRIAL)\b",
    re.IGNORECASE,
)
_FIGI_ETF = re.compile(r"(?:EXCHANGE[ -]TRADED[ -]FUND|\bETF\b)", re.IGNORECASE)
_IDENTITY_STOPWORDS = {
    "A", "AN", "AND", "THE", "ETF", "ETFS", "FUND", "FUNDS", "TRUST",
    "INDEX", "PORTFOLIO", "SERIES", "SHARE", "SHARES", "INC", "LTD", "LP",
    "OF", "THE", "US", "USD", "TR",
}
_CUSIP_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ*@#"
_CUSIP_VALUE = {char: value for value, char in enumerate(_CUSIP_CHARS)}


def _truthy(value: object) -> bool:
    return str(value).strip().upper() in {"Y", "YES", "TRUE", "1"}


def normalize_ticker(value: object) -> str:
    """Normalize only display separators; never perform fuzzy ticker joins."""

    if value is None or pd.isna(value):
        return ""
    out = str(value).strip().upper().replace(".", "-").replace("/", "-")
    return re.sub(r"\s+", "-", out)


def valid_cusip(value: object) -> bool:
    """Validate both CUSIP shape and modulus-10 check digit."""

    cusip = str(value).strip().upper()
    if not re.fullmatch(r"[0-9A-Z*@#]{9}", cusip):
        return False
    total = 0
    for index, char in enumerate(cusip[:8]):
        number = _CUSIP_VALUE[char]
        if index % 2 == 1:
            number *= 2
        total += number // 10 + number % 10
    return str((10 - total % 10) % 10) == cusip[8]


def valid_figi(value: object) -> bool:
    """Recognize Bloomberg Global IDs stored as the 13F fallback identifier."""

    return bool(re.fullmatch(r"BBG[0-9A-Z]{9}", str(value).strip().upper()))


def _openfigi_job(value: str) -> dict[str, str]:
    if valid_cusip(value):
        id_type = "ID_CUSIP"
    elif valid_figi(value):
        id_type = "ID_BB_GLOBAL"
    else:  # defensive: callers filter before constructing jobs
        raise ValueError(f"unsupported security identifier: {value}")
    return {"idType": id_type, "idValue": value, "exchCode": "US"}


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self.hrefs.append(href)


def _read_url(url: str, user_agent: str, timeout: int = 90) -> bytes:
    req = Request(url, headers={"User-Agent": user_agent, "Accept-Encoding": "identity"})
    with urlopen(req, timeout=timeout) as response:
        return response.read()


def download_file(
    url: str,
    destination: str | Path,
    *,
    user_agent: str = DEFAULT_USER_AGENT,
    refresh: bool = False,
    retries: int = 4,
) -> Path:
    """Download atomically so an interrupted run never masquerades as a valid source."""

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size > 0 and not refresh:
        return destination
    error: Exception | None = None
    for attempt in range(retries):
        try:
            payload = _read_url(url, user_agent)
            if not payload:
                raise RuntimeError(f"empty response from {url}")
            part = destination.with_suffix(destination.suffix + ".part")
            part.write_bytes(payload)
            part.replace(destination)
            return destination
        except Exception as exc:  # pragma: no cover - exercised against live endpoints
            error = exc
            time.sleep(2**attempt)
    raise RuntimeError(f"failed to download {url}: {error}")


def _page_links(page_url: str, user_agent: str) -> list[str]:
    parser = _LinkParser()
    parser.feed(_read_url(page_url, user_agent).decode("utf-8", errors="replace"))
    return [urljoin(page_url, href) for href in parser.hrefs]


def _quarter_key(year: int, quarter: int) -> int:
    return year * 4 + quarter


def download_reference_sources(
    raw_dir: str | Path,
    *,
    through: str = "2026q1",
    user_agent: str = DEFAULT_USER_AGENT,
    refresh: bool = False,
    include_series_class: bool = True,
    log: Callable[[str], None] = print,
) -> dict[str, list[Path]]:
    """Download official Nasdaq, N-CEN and SEC series/class source files."""

    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    match = re.fullmatch(r"(\d{4})q([1-4])", through.lower())
    if not match:
        raise ValueError("through must have format YYYYqN")
    end_key = _quarter_key(int(match.group(1)), int(match.group(2)))

    result: dict[str, list[Path]] = {"nasdaq": [], "ncen": [], "series_class": []}
    for filename, url in NASDAQ_URLS.items():
        log(f"download Nasdaq: {filename}")
        result["nasdaq"].append(
            download_file(url, raw_dir / filename, user_agent=user_agent, refresh=refresh)
        )

    ncen_links = _page_links(SEC_NCEN_PAGE, user_agent)
    for url in ncen_links:
        found = re.search(
            r"(\d{4})q([1-4])_ncen(?:_\d+)?\.zip(?:\?|$)", url, re.IGNORECASE
        )
        if not found:
            continue
        if _quarter_key(int(found.group(1)), int(found.group(2))) > end_key:
            continue
        filename = f"{found.group(1)}q{found.group(2)}_ncen.zip"
        log(f"download SEC N-CEN: {filename}")
        result["ncen"].append(
            download_file(url, raw_dir / filename, user_agent=user_agent, refresh=refresh)
        )

    if include_series_class:
        series_links = _page_links(SEC_SERIES_PAGE, user_agent)
        for url in series_links:
            if not re.search(r"\.csv(?:\?|$)", url, re.IGNORECASE):
                continue
            year_match = re.search(r"(20\d{2})", Path(url.split("?")[0]).name)
            if not year_match or int(year_match.group(1)) > int(match.group(1)):
                continue
            filename = f"series_class_{year_match.group(1)}.csv"
            log(f"download SEC series/class: {filename}")
            result["series_class"].append(
                download_file(url, raw_dir / filename, user_agent=user_agent, refresh=refresh)
            )
        # The 2016 link is the sole annual file whose basename contains no
        # year, so it cannot be discovered by the otherwise stable rule above.
        legacy_2016 = next((
            url for url in series_links
            if url.lower().endswith("/investment_company_series_class.csv")
        ), None)
        if legacy_2016 and int(match.group(1)) >= 2016:
            filename = "series_class_2016.csv"
            log(f"download SEC series/class: {filename}")
            result["series_class"].append(
                download_file(
                    legacy_2016, raw_dir / filename, user_agent=user_agent, refresh=refresh
                )
            )
    return result


def parse_nasdaq_directory(raw_dir: str | Path) -> pd.DataFrame:
    """Parse the explicit exchange ETF flag from both US symbol directories."""

    raw_dir = Path(raw_dir)
    frames: list[pd.DataFrame] = []
    for filename in NASDAQ_URLS:
        path = raw_dir / filename
        if not path.exists():
            raise FileNotFoundError(path)
        data = pd.read_csv(path, sep="|", dtype=str)
        data = data[~data.iloc[:, 0].astype(str).str.startswith("File Creation Time")].copy()
        ticker_col = "Symbol" if "Symbol" in data else "NASDAQ Symbol"
        if ticker_col not in data and "ACT Symbol" in data:
            ticker_col = "ACT Symbol"
        if "ETF" not in data:
            raise ValueError(f"{filename} has no ETF field")
        data["ticker"] = data[ticker_col].map(normalize_ticker)
        data["name"] = data.get("Security Name", "")
        data["is_exchange_etf"] = data["ETF"].map(_truthy)
        data["exchange_source"] = filename
        data["exchange"] = data.get("Exchange", "NASDAQ")
        test = data.get("Test Issue", pd.Series("N", index=data.index)).fillna("N")
        frames.append(data.loc[test.ne("Y"), [
            "ticker", "name", "is_exchange_etf", "exchange", "exchange_source"
        ]])
    out = pd.concat(frames, ignore_index=True)
    out = out[out["ticker"].ne("")].drop_duplicates(["ticker", "exchange_source"])
    return out.sort_values(["ticker", "exchange_source"]).reset_index(drop=True)


def parse_ncen_archives(paths: Iterable[str | Path]) -> pd.DataFrame:
    """Return one regulatory ETF observation per N-CEN class/ticker/report."""

    parts: list[pd.DataFrame] = []
    for path_like in paths:
        path = Path(path_like)
        with zipfile.ZipFile(path) as archive:
            fund = pd.read_csv(
                archive.open("FUND_REPORTED_INFO.tsv"),
                sep="\t",
                dtype=str,
                usecols=lambda c: c in {
                    "FUND_ID", "ACCESSION_NUMBER", "FUND_NAME", "SERIES_ID",
                    "IS_ETF", "IS_INDEX", "IS_MULTI_INVERSE_INDEX",
                },
            )
            shares = pd.read_csv(
                archive.open("SHARES_OUTSTANDING.tsv"), sep="\t", dtype=str,
                usecols=lambda c: c in {"FUND_ID", "CLASS_NAME", "CLASS_ID", "TICKER"},
            )
            submission = pd.read_csv(
                archive.open("SUBMISSION.tsv"), sep="\t", dtype=str,
                usecols=lambda c: c in {
                    "ACCESSION_NUMBER", "CIK", "FILING_DATE", "REPORT_ENDING_PERIOD"
                },
            )
            etf_ids: set[str] = set()
            if "ETF.tsv" in archive.namelist():
                etf = pd.read_csv(
                    archive.open("ETF.tsv"), sep="\t", dtype=str,
                    usecols=lambda c: c == "FUND_ID",
                )
                etf_ids = set(etf["FUND_ID"].dropna())
        flag = fund.get("IS_ETF", pd.Series("", index=fund.index)).map(_truthy)
        flag |= fund["FUND_ID"].isin(etf_ids)
        fund = fund[flag].copy()
        if fund.empty:
            continue
        joined = fund.merge(shares, on="FUND_ID", how="left", validate="one_to_many")
        joined = joined.merge(submission, on="ACCESSION_NUMBER", how="left", validate="many_to_one")
        joined["ticker"] = joined["TICKER"].map(normalize_ticker)
        joined["is_ncen_etf"] = True
        joined["is_index_fund"] = joined.get("IS_INDEX", "").map(_truthy)
        joined["is_multi_inverse_index"] = joined.get(
            "IS_MULTI_INVERSE_INDEX", ""
        ).map(_truthy)
        joined["filing_date"] = pd.to_datetime(
            joined["FILING_DATE"], format="%d-%b-%Y", errors="coerce"
        )
        joined["report_end"] = pd.to_datetime(
            joined["REPORT_ENDING_PERIOD"], format="%d-%b-%Y", errors="coerce"
        )
        joined["source_archive"] = path.name
        parts.append(joined[[
            "ticker", "FUND_NAME", "SERIES_ID", "CLASS_NAME", "CLASS_ID", "CIK",
            "is_ncen_etf", "is_index_fund", "is_multi_inverse_index", "filing_date",
            "report_end", "ACCESSION_NUMBER", "source_archive",
        ]])
    if not parts:
        return pd.DataFrame(columns=[
            "ticker", "FUND_NAME", "SERIES_ID", "CLASS_NAME", "CLASS_ID", "CIK",
            "is_ncen_etf", "is_index_fund", "is_multi_inverse_index", "filing_date",
            "report_end", "ACCESSION_NUMBER", "source_archive",
        ])
    out = pd.concat(parts, ignore_index=True)
    out = out[out["ticker"].ne("")]
    return out.drop_duplicates(["ticker", "ACCESSION_NUMBER", "SERIES_ID", "CLASS_ID"])


def _canonical_column(columns: Iterable[str], *needles: str) -> str | None:
    normal = {re.sub(r"[^A-Z0-9]", "", str(c).upper()): str(c) for c in columns}
    for needle in needles:
        key = re.sub(r"[^A-Z0-9]", "", needle.upper())
        if key in normal:
            return normal[key]
    return None


def parse_series_class_files(paths: Iterable[str | Path]) -> pd.DataFrame:
    """Normalize the SEC's changing annual Series/Class CSV schemas."""

    parts: list[pd.DataFrame] = []
    for path_like in paths:
        path = Path(path_like)
        data = pd.read_csv(path, dtype=str, encoding_errors="replace")
        ticker = _canonical_column(data.columns, "Class Ticker", "Class-Contract-Ticker-Symbol")
        series_id = _canonical_column(data.columns, "Series ID", "Series-ID")
        class_id = _canonical_column(data.columns, "Class ID", "Class-Contract-ID")
        series_name = _canonical_column(data.columns, "Series Name")
        class_name = _canonical_column(data.columns, "Class Name", "Class-Contract-Name")
        cik = _canonical_column(data.columns, "CIK")
        registrant = _canonical_column(data.columns, "Name of Investment Company", "Company Name")
        if not ticker:
            continue
        year_match = re.search(r"(20\d{2})", path.name)
        out = pd.DataFrame({
            "ticker": data[ticker].map(normalize_ticker),
            "series_id": data[series_id] if series_id else pd.NA,
            "class_id": data[class_id] if class_id else pd.NA,
            "series_name": data[series_name] if series_name else pd.NA,
            "class_name": data[class_name] if class_name else pd.NA,
            "cik": data[cik] if cik else pd.NA,
            "registrant_name": data[registrant] if registrant else pd.NA,
            "source_year": int(year_match.group(1)) if year_match else pd.NA,
        })
        parts.append(out[out["ticker"].ne("")])
    if not parts:
        return pd.DataFrame(columns=[
            "ticker", "series_id", "class_id", "series_name", "class_name", "cik",
            "registrant_name", "source_year",
        ])
    return pd.concat(parts, ignore_index=True).drop_duplicates(
        ["ticker", "series_id", "class_id", "source_year"]
    )


def load_openfigi_cache(path: str | Path) -> dict[str, dict]:
    path = Path(path)
    cache: dict[str, dict] = {}
    if not path.exists():
        return cache
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            cache[str(record["instrument_id"])] = record
    return cache


def derive_figi_alias_records(
    cache: dict[str, dict], figi_ids: Iterable[str]
) -> dict[str, dict]:
    """Resolve share-class FIGI fallbacks from already mapped US CUSIPs.

    SEC filings may report the CUSIP in one filing and the optional FIGI in
    another.  OpenFIGI's CUSIP response includes ``figi``, ``compositeFIGI``
    and ``shareClassFIGI``.  Reusing that exact identifier relationship avoids
    a second network request and is stronger than a name or ticker match.
    """

    targets = {str(value).upper() for value in figi_ids if valid_figi(value)}
    aliases: dict[str, dict] = {}
    for source_id, record in cache.items():
        response = record.get("response", {})
        data = response.get("data", []) if isinstance(response, dict) else []
        # Only a US composite can safely populate this project's alias map.
        us_items = [item for item in data if str(item.get("exchCode", "")).upper() == "US"]
        for item in us_items:
            item_ids = {
                str(item.get(field, "")).upper()
                for field in ("figi", "compositeFIGI", "shareClassFIGI")
                if item.get(field)
            }
            for alias in (item_ids & targets) - set(aliases) - set(cache):
                aliases[alias] = {
                    "instrument_id": alias,
                    "queried_at": record.get("queried_at"),
                    "derived_from": source_id,
                    "response": {"data": [item]},
                }
    return aliases


def extract_filing_figi_cusip_aliases(
    holdings_path: str | Path,
    *,
    chunksize: int = 1_000_000,
    log: Callable[[str], None] = print,
) -> pd.DataFrame:
    """Extract exact FIGI/CUSIP pairs reported together in native 13F rows."""

    parts: list[pd.DataFrame] = []
    rows = 0
    for chunk in pd.read_csv(
        holdings_path,
        usecols=["instrument_id", "cusip", "id_source"],
        dtype=str,
        chunksize=chunksize,
    ):
        rows += len(chunk)
        native = chunk["id_source"].eq("filing_figi")
        pairs = chunk.loc[native, ["instrument_id", "cusip"]].dropna().drop_duplicates()
        if not pairs.empty:
            parts.append(pairs)
        if rows % 10_000_000 == 0:
            log(f"13F FIGI/CUSIP scan: {rows:,} rows")
    if not parts:
        return pd.DataFrame(columns=["instrument_id", "cusip", "alias_status"])
    out = pd.concat(parts, ignore_index=True).drop_duplicates()
    out["instrument_id"] = out["instrument_id"].str.strip().str.upper()
    out["cusip"] = out["cusip"].str.strip().str.upper()
    out = out[
        out["instrument_id"].map(valid_figi) & out["cusip"].map(valid_cusip)
    ].copy()
    ambiguous = out.groupby("instrument_id")["cusip"].nunique().gt(1)
    out["alias_status"] = np.where(
        out["instrument_id"].isin(ambiguous[ambiguous].index), "ambiguous", "exact_filing_pair"
    )
    log(
        f"13F FIGI/CUSIP aliases: {out['instrument_id'].nunique():,} FIGIs; "
        f"{int(ambiguous.sum()):,} ambiguous"
    )
    return out.sort_values(["alias_status", "instrument_id", "cusip"]).reset_index(drop=True)


def derive_filing_alias_records(
    cache: dict[str, dict], figi_to_cusip: dict[str, str]
) -> dict[str, dict]:
    """Copy a mapped US CUSIP response to its co-reported native FIGI."""

    aliases: dict[str, dict] = {}
    for figi, cusip in figi_to_cusip.items():
        figi, cusip = str(figi).upper(), str(cusip).upper()
        if figi in cache or cusip not in cache:
            continue
        source = cache[cusip]
        response = source.get("response", {})
        data = response.get("data", []) if isinstance(response, dict) else []
        us_items = [item for item in data if str(item.get("exchCode", "")).upper() == "US"]
        if not us_items:
            continue
        aliases[figi] = {
            "instrument_id": figi,
            "queried_at": source.get("queried_at"),
            "derived_from": cusip,
            "relation_source": "13F_NATIVE_FIGI_CUSIP_PAIR",
            "response": {"data": [us_items[0]]},
        }
    return aliases


def map_openfigi(
    cusips: Iterable[str],
    cache_path: str | Path,
    *,
    api_key: str | None = None,
    figi_cusip_aliases: dict[str, str] | None = None,
    request_post: Callable[..., object] | None = None,
    log: Callable[[str], None] = print,
) -> dict[str, dict]:
    """Map CUSIPs/FIGIs in rate-limited batches with exact alias reuse."""

    try:
        import requests
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("requests is required for OpenFIGI mapping") from exc

    cache_path = Path(cache_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache = load_openfigi_cache(cache_path)
    original_ids = [
        str(x).strip().upper()
        for x in cusips
        if valid_cusip(x) or valid_figi(x)
    ]
    original_ids = list(dict.fromkeys(original_ids))
    alias_map = {
        str(figi).upper(): str(cusip).upper()
        for figi, cusip in (figi_cusip_aliases or {}).items()
        if valid_figi(figi) and valid_cusip(cusip)
    }
    required_alias_cusips = [
        alias_map[value] for value in original_ids if value in alias_map
    ]
    ids = list(dict.fromkeys([*original_ids, *required_alias_cusips]))
    pending_cusips = [x for x in ids if x not in cache and valid_cusip(x)]
    pending_figis = [x for x in ids if x not in cache and valid_figi(x)]
    if not pending_cusips and not pending_figis:
        log(f"OpenFIGI cache complete: {len(cache):,} security identifiers")
        return cache

    key = api_key or os.getenv("OPENFIGI_API_KEY")
    batch_size = 100 if key else 10
    min_interval = 0.27 if key else 2.45
    headers = {"Content-Type": "application/json"}
    if key:
        headers["X-OPENFIGI-APIKEY"] = key
    post = request_post or requests.post
    started = time.monotonic()
    api_done = 0
    last_call_started: float | None = None

    with cache_path.open("a", encoding="utf-8") as handle:
        def write_record(record: dict) -> None:
            handle.write(json.dumps(record, separators=(",", ":")) + "\n")
            cache[str(record["instrument_id"])] = record

        def request_phase(pending: list[str], label: str) -> None:
            nonlocal api_done, last_call_started
            for offset in range(0, len(pending), batch_size):
                batch = pending[offset : offset + batch_size]
                # ``ID_CUSIP`` without an exchange returns every global listing
                # of the same share class.  Restricting to the US composite
                # prevents foreign ticker collisions and shrinks responses.
                payload = [_openfigi_job(value) for value in batch]
                response = None
                for attempt in range(7):
                    if last_call_started is not None:
                        wait = min_interval - (time.monotonic() - last_call_started)
                        if wait > 0:
                            time.sleep(wait)
                    last_call_started = time.monotonic()
                    response = post(
                        OPENFIGI_MAPPING_URL, headers=headers, json=payload, timeout=60
                    )
                    status = int(getattr(response, "status_code", 0))
                    if status == 200:
                        break
                    if status == 429 or status >= 500:
                        retry_after = float(getattr(response, "headers", {}).get(
                            "ratelimit-reset",
                            getattr(response, "headers", {}).get("Retry-After", 2**attempt),
                        ))
                        time.sleep(max(retry_after, 1.0))
                        continue
                    body = getattr(response, "text", "")[:500]
                    raise RuntimeError(f"OpenFIGI HTTP {status}: {body}")
                if response is None or int(getattr(response, "status_code", 0)) != 200:
                    raise RuntimeError("OpenFIGI retries exhausted")
                results = response.json()
                if len(results) != len(batch):
                    raise RuntimeError("OpenFIGI response length does not match request")
                queried_at = datetime.now(timezone.utc).isoformat()
                for instrument_id, result in zip(batch, results):
                    write_record({
                        "instrument_id": instrument_id,
                        "queried_at": queried_at,
                        "response": result,
                    })
                handle.flush()
                api_done += len(batch)
                phase_done = min(offset + batch_size, len(pending))
                if phase_done == len(pending) or phase_done % max(batch_size, 100) == 0:
                    elapsed = max(time.monotonic() - started, 1e-9)
                    log(
                        f"OpenFIGI {label}: {phase_done:,}/{len(pending):,} API mappings "
                        f"({api_done / elapsed:.1f}/s overall)"
                    )

        # Mapping CUSIPs first exposes their exact share-class FIGIs.  Most
        # FIGI fallbacks can consequently be filled without spending another
        # public API request.
        request_phase(pending_cusips, "CUSIP")
        filing_aliases = derive_filing_alias_records(
            cache, {figi: alias_map[figi] for figi in pending_figis if figi in alias_map}
        )
        for record in filing_aliases.values():
            write_record(record)
        handle.flush()
        if filing_aliases:
            log(
                f"OpenFIGI filing aliases: resolved {len(filing_aliases):,} FIGIs "
                "from native 13F CUSIP pairs"
            )
        unresolved_figis = [value for value in pending_figis if value not in cache]
        aliases = derive_figi_alias_records(cache, unresolved_figis)
        for record in aliases.values():
            write_record(record)
        handle.flush()
        if aliases:
            log(f"OpenFIGI aliases: resolved {len(aliases):,} FIGIs from mapped CUSIPs")
        remaining_figis = [value for value in pending_figis if value not in cache]
        request_phase(remaining_figis, "FIGI")
    return cache


def flatten_openfigi_cache(cache: dict[str, dict]) -> pd.DataFrame:
    """Flatten all mapping alternatives; ambiguity is preserved for scoring/audit."""

    rows: list[dict[str, object]] = []
    fields = [
        "figi", "securityType", "securityType2", "marketSector", "ticker", "name",
        "exchCode", "compositeFIGI", "shareClassFIGI", "securityDescription",
    ]
    for instrument_id, record in cache.items():
        response = record.get("response", {})
        data = response.get("data", []) if isinstance(response, dict) else []
        if not data:
            rows.append({
                "instrument_id": instrument_id,
                "mapping_rank": np.nan,
                "mapping_error": response.get("error", "No identifier found")
                if isinstance(response, dict) else "invalid response",
                "queried_at": record.get("queried_at"),
            })
            continue
        for rank, item in enumerate(data):
            row = {"instrument_id": instrument_id, "mapping_rank": rank,
                   "mapping_error": "", "queried_at": record.get("queried_at"),
                   "mapping_provenance": "OPENFIGI"}
            row.update({field: item.get(field) for field in fields})
            rows.append(row)
    out = pd.DataFrame(rows)
    if "ticker" not in out:
        out["ticker"] = ""
    out["ticker_norm"] = out["ticker"].map(normalize_ticker)
    return out


def _latest_ncen_by_ticker(ncen: pd.DataFrame) -> pd.DataFrame:
    if ncen.empty:
        return pd.DataFrame(columns=[
            "ticker_norm", "ncen_name", "ncen_is_etf", "ncen_is_index",
            "ncen_is_multi_inverse", "ncen_first_filing", "ncen_last_filing",
            "ncen_series_id", "ncen_class_id",
        ])
    data = ncen.copy()
    data["ticker_norm"] = data["ticker"].map(normalize_ticker)
    data = data[data["ticker_norm"].ne("")].sort_values("filing_date")
    latest = data.groupby("ticker_norm", as_index=False).tail(1).set_index("ticker_norm")
    dates = data.groupby("ticker_norm")["filing_date"].agg(["min", "max"])
    result = pd.DataFrame(index=latest.index)
    result["ncen_name"] = latest["FUND_NAME"]
    result["ncen_is_etf"] = latest["is_ncen_etf"].fillna(False).astype(bool)
    result["ncen_is_index"] = latest["is_index_fund"].fillna(False).astype(bool)
    result["ncen_is_multi_inverse"] = latest["is_multi_inverse_index"].fillna(False).astype(bool)
    result["ncen_first_filing"] = dates["min"]
    result["ncen_last_filing"] = dates["max"]
    result["ncen_series_id"] = latest["SERIES_ID"]
    result["ncen_class_id"] = latest["CLASS_ID"]
    return result.reset_index()


def _classify_asset(name: str) -> str:
    # Equity portfolios exposed to a commodity theme (gold miners, oil
    # producers) must not be confused with funds holding the commodity itself.
    if _EQUITY_OVERRIDE.search(name):
        return "equity"
    if _FIXED_INCOME.search(name):
        return "fixed_income"
    if _COMMODITY.search(name):
        return "commodity"
    if _CRYPTO.search(name):
        return "crypto"
    if _VOLATILITY.search(name):
        return "volatility"
    if _THEMATIC.search(name):
        return "equity"
    if _EQUITY.search(name):
        return "equity"
    return "unknown"


def _identity_name_compatible(left: object, right: object) -> bool:
    """Reject obvious ticker reuse while tolerating vendor abbreviations.

    The rule is deliberately asymmetric with a fuzzy join: ticker remains an
    exact prerequisite.  Names are used only as a veto when both sides have
    meaningful tokens and share none, which catches recycled symbols such as
    the historical Defiance IBIT versus today's iShares Bitcoin trust.
    """

    def tokens(value: object) -> set[str]:
        if value is None or pd.isna(value):
            return set()
        words = re.findall(r"[A-Z0-9]+", str(value).upper())
        return {
            word for word in words
            if word not in _IDENTITY_STOPWORDS and len(word) > 1
        }

    left_tokens = tokens(left)
    right_tokens = tokens(right)
    if not left_tokens or not right_tokens:
        return True
    if left_tokens & right_tokens:
        return True
    compact = lambda value: re.sub(  # noqa: E731 - local normalization rule
        r"[^A-Z0-9]", "", str(value).upper()
    )
    # OpenFIGI commonly compresses every word (``MUN INF REV BD ACT``).
    # Sequence similarity recovers those deterministic abbreviations.  The
    # threshold stays above the observed recycled-IBIT pair (~0.30).
    return SequenceMatcher(None, compact(left), compact(right)).ratio() >= 0.35


def _classify_style(name: str, multi_inverse: bool) -> str:
    duration_short = bool(_DURATION_SHORT.search(name))
    directional = bool(_DIRECTIONAL_SHORT.search(name)) and not duration_short
    if multi_inverse or _LEVERAGED_STRONG.search(name) or directional:
        return "leveraged_inverse"
    if _THEMATIC.search(name):
        return "thematic"
    if _SECTOR.search(name):
        return "sector"
    if _FACTOR.search(name):
        return "factor"
    if _BROAD.search(name):
        return "broad"
    return "other"


def build_etf_flags(
    candidates: pd.DataFrame,
    openfigi: pd.DataFrame,
    exchange: pd.DataFrame,
    ncen: pd.DataFrame,
    seed: pd.DataFrame | None = None,
    series_class: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Classify each candidate CUSIP with explicit evidence and conflicts."""

    required = {"instrument_id"}
    missing = required - set(candidates)
    if missing:
        raise ValueError(f"candidates missing columns: {sorted(missing)}")
    base = candidates.copy()
    base["instrument_id"] = base["instrument_id"].astype(str).str.strip().str.upper()
    base = base.drop_duplicates("instrument_id")
    # The legacy audit contains the handful of seed tickers.  Preserve that
    # diagnostic without allowing it to collide with the OpenFIGI ticker that
    # acts as the bridge to Nasdaq/N-CEN.
    if "ticker" in base:
        base = base.rename(columns={"ticker": "candidate_ticker"})

    ex = exchange.copy()
    ex["ticker_norm"] = ex["ticker"].map(normalize_ticker)
    ex = ex.sort_values("is_exchange_etf", ascending=False).drop_duplicates("ticker_norm")
    ex_lookup = ex.set_index("ticker_norm")
    ncen_latest = _latest_ncen_by_ticker(ncen).set_index("ticker_norm")

    mappings = openfigi.copy()
    if mappings.empty:
        mappings = pd.DataFrame({"instrument_id": base["instrument_id"], "ticker_norm": ""})
    if "ticker_norm" not in mappings:
        mappings["ticker_norm"] = mappings.get("ticker", "").map(normalize_ticker)
    mappings["exchange_match"] = mappings["ticker_norm"].isin(ex_lookup.index)
    mappings["exchange_etf"] = mappings["ticker_norm"].map(
        ex_lookup["is_exchange_etf"] if not ex_lookup.empty else pd.Series(dtype=bool)
    ).fillna(False)
    mappings["exchange_name"] = mappings["ticker_norm"].map(
        ex_lookup["name"] if not ex_lookup.empty else pd.Series(dtype=str)
    )
    mappings["ncen_match"] = mappings["ticker_norm"].isin(ncen_latest.index)
    text = (
        mappings.get("name", pd.Series("", index=mappings.index)).fillna("").astype(str)
        + " "
        + mappings.get("securityType", pd.Series("", index=mappings.index)).fillna("").astype(str)
        + " "
        + mappings.get("securityType2", pd.Series("", index=mappings.index)).fillna("").astype(str)
    )
    mappings["figi_etf_hint"] = text.str.contains(_FIGI_ETF, na=False)
    mappings["us_composite"] = mappings.get(
        "exchCode", pd.Series("", index=mappings.index)
    ).fillna("").astype(str).str.upper().eq("US")
    candidate_ticker = base.get(
        "candidate_ticker", pd.Series("", index=base.index)
    ).map(normalize_ticker)
    ticker_hint = dict(zip(base["instrument_id"], candidate_ticker))
    mappings["seed_ticker_match"] = mappings["ticker_norm"].eq(
        mappings["instrument_id"].map(ticker_hint).fillna("")
    ) & mappings["instrument_id"].map(ticker_hint).fillna("").ne("")
    mappings["mapping_score"] = (
        1000 * mappings["us_composite"].astype(int)
        + 500 * mappings["seed_ticker_match"].astype(int)
        + 100 * mappings["exchange_etf"].astype(int)
        + 50 * mappings["ncen_match"].astype(int)
        + 10 * mappings["figi_etf_hint"].astype(int)
        + 2 * mappings["exchange_match"].astype(int)
        - pd.to_numeric(mappings.get("mapping_rank", 0), errors="coerce").fillna(999) / 1000
    )
    best = mappings.sort_values(
        ["instrument_id", "mapping_score"], ascending=[True, False]
    ).drop_duplicates("instrument_id")
    keep = [
        "instrument_id", "ticker_norm", "figi", "name", "securityType", "securityType2",
        "marketSector", "exchCode", "mapping_error", "queried_at", "exchange_match",
        "exchange_etf", "exchange_name", "ncen_match", "figi_etf_hint",
        "mapping_provenance",
    ]
    for column in keep:
        if column not in best:
            best[column] = pd.NA
    best = best[keep].rename(columns={
        "ticker_norm": "ticker", "name": "openfigi_name",
        "securityType": "openfigi_security_type",
        "securityType2": "openfigi_security_type2", "marketSector": "openfigi_market_sector",
        "exchCode": "openfigi_exchange", "queried_at": "openfigi_queried_at",
    })
    out = base.merge(best, on="instrument_id", how="left", validate="one_to_one")
    out["ticker"] = out["ticker"].fillna("")
    if not ncen_latest.empty:
        out = out.merge(
            ncen_latest.reset_index().rename(columns={"ticker_norm": "ticker"}),
            on="ticker", how="left", validate="many_to_one",
        )
    else:
        for col in [
            "ncen_name", "ncen_is_etf", "ncen_is_index", "ncen_is_multi_inverse",
            "ncen_first_filing", "ncen_last_filing", "ncen_series_id", "ncen_class_id",
        ]:
            out[col] = pd.NA

    if series_class is not None and not series_class.empty:
        series = series_class.copy()
        series["ticker_norm"] = series["ticker"].map(normalize_ticker)
        series["source_year"] = pd.to_numeric(series["source_year"], errors="coerce")
        series_evidence = series.groupby("ticker_norm", as_index=False).agg(
            series_first_year=("source_year", "min"),
            series_last_year=("source_year", "max"),
            series_id=("series_id", "last"),
            series_class_id=("class_id", "last"),
            series_name=("series_name", "last"),
            series_class_name=("class_name", "last"),
        ).rename(columns={"ticker_norm": "ticker"})
        out = out.merge(series_evidence, on="ticker", how="left", validate="many_to_one")
    else:
        out["series_first_year"] = np.nan
        out["series_last_year"] = np.nan
        out["series_id"] = pd.NA
        out["series_class_id"] = pd.NA
        out["series_name"] = pd.NA
        out["series_class_name"] = pd.NA

    if seed is not None and not seed.empty:
        seed_data = seed.copy()
        seed_data["instrument_id"] = seed_data["instrument_id"].astype(str).str.upper()
        seed_cols = [
            c for c in ["instrument_id", "ticker", "name", "asset_class", "etf_style",
                        "specialized_score", "is_etf", "verification_source"] if c in seed_data
        ]
        seed_data = seed_data[seed_cols].drop_duplicates("instrument_id").rename(
            columns={c: f"seed_{c}" for c in seed_cols if c != "instrument_id"}
        )
        out = out.merge(seed_data, on="instrument_id", how="left", validate="one_to_one")
    else:
        out["seed_is_etf"] = False

    out["seed_is_etf"] = out.get("seed_is_etf", False).fillna(False).astype(bool)
    out["ncen_is_etf"] = out.get("ncen_is_etf", False).fillna(False).astype(bool)
    out["ncen_is_index"] = out.get("ncen_is_index", False).fillna(False).astype(bool)
    out["ncen_is_multi_inverse"] = out.get(
        "ncen_is_multi_inverse", False
    ).fillna(False).astype(bool)
    out["exchange_match"] = out["exchange_match"].fillna(False).astype(bool)
    out["exchange_etf"] = out["exchange_etf"].fillna(False).astype(bool)
    out["figi_etf_hint"] = out["figi_etf_hint"].fillna(False).astype(bool)
    out["known_common_stock"] = (
        out.get("mapping_provenance", pd.Series("", index=out.index))
        .fillna("").eq("LOCAL_COMMON_MAP")
    )

    first_date = pd.to_datetime(
        out.get("first_period", pd.Series(pd.NaT, index=out.index)), errors="coerce"
    )
    last_date = pd.to_datetime(
        out.get("last_period", pd.Series(pd.NaT, index=out.index)), errors="coerce"
    )
    first_year = first_date.dt.year
    last_year = last_date.dt.year
    overlap = (
        out["series_first_year"].notna()
        & (last_year.isna() | out["series_first_year"].le(last_year))
        & (first_year.isna() | out["series_last_year"].ge(first_year))
    )
    figi_registered_fund = (
        out.get("openfigi_security_type", pd.Series("", index=out.index))
        .fillna("").astype(str).str.upper().eq("ETP")
        & out.get("openfigi_security_type2", pd.Series("", index=out.index))
        .fillna("").astype(str).str.contains("FUND", case=False, na=False)
    )
    figi_etp = (
        out.get("openfigi_security_type", pd.Series("", index=out.index))
        .fillna("").astype(str).str.upper().eq("ETP")
    )
    figi_common_stock = (
        out.get("openfigi_security_type", pd.Series("", index=out.index))
        .fillna("").astype(str).str.contains("COMMON STOCK", case=False, na=False)
        | out.get("openfigi_security_type2", pd.Series("", index=out.index))
        .fillna("").astype(str).str.contains("COMMON STOCK", case=False, na=False)
    )
    out["figi_common_stock"] = figi_common_stock
    out["known_common_stock"] = out["known_common_stock"] | figi_common_stock
    openfigi_identity_name = out.get(
        "openfigi_name", pd.Series("", index=out.index)
    ).fillna("").astype(str)
    issuer_name = out.get("issuer", pd.Series("", index=out.index)).fillna("").astype(str)
    # The vendor display name can be heavily abbreviated (``VNGRD MRGSTR``),
    # while the 13F issuer usually preserves the sponsor token.  Combining
    # both retains exact-token vetoes without turning this into a fuzzy join.
    instrument_name = (openfigi_identity_name + " " + issuer_name).str.strip()
    ncen_name_raw = out.get("ncen_name", pd.Series("", index=out.index)).fillna("")
    exchange_name_raw = out.get(
        "exchange_name", pd.Series("", index=out.index)
    ).fillna("")
    series_name_raw = out.get("series_name", pd.Series("", index=out.index)).fillna("")
    out["ncen_name_compatible"] = pd.Series([
        _identity_name_compatible(left, right)
        for left, right in zip(instrument_name, ncen_name_raw)
    ], index=out.index)
    out["exchange_name_compatible"] = pd.Series([
        _identity_name_compatible(left, right)
        for left, right in zip(instrument_name, exchange_name_raw)
    ], index=out.index)
    out["series_name_compatible"] = pd.Series([
        _identity_name_compatible(left, right)
        for left, right in zip(instrument_name, series_name_raw)
    ], index=out.index)

    # N-CEN starts in 2018 and is annual, so its latest identity observation
    # can trail a 13F appearance by roughly one reporting cycle.  The name
    # compatibility veto remains mandatory, preventing this allowance from
    # joining a recycled ticker to a different product.
    ncen_first = pd.to_datetime(
        out.get("ncen_first_filing", pd.Series(pd.NaT, index=out.index)), errors="coerce"
    )
    ncen_last = pd.to_datetime(
        out.get("ncen_last_filing", pd.Series(pd.NaT, index=out.index)), errors="coerce"
    )
    lag = pd.Timedelta(days=370)
    out["ncen_temporal_match"] = (
        ncen_first.notna()
        & (last_date.isna() | (ncen_first <= last_date + lag))
        & (first_date.isna() | (ncen_last + lag >= first_date))
    )

    out["historical_series_etf"] = (
        overlap & figi_registered_fund & out["series_name_compatible"]
    )

    # N-CEN and the Nasdaq directory identify share classes by ticker, while
    # 13F positions are keyed by CUSIP/FIGI.  Tickers are occasionally reused
    # or collide (for example, an operating company and an ETF class can both
    # appear as BABA in different source histories).  Therefore ticker-level
    # regulatory evidence may promote an identifier only when OpenFIGI says
    # that the identifier itself is an exchange-traded product.  A curated
    # seed is the only fallback because it was verified at identifier level.
    ticker_identity_compatible = figi_etp
    latest_observation = last_date.max()
    if pd.isna(latest_observation):
        recent_identifier = pd.Series(False, index=out.index)
    else:
        recent_identifier = last_date.ge(latest_observation - pd.Timedelta(days=548))
    out["recent_identifier"] = recent_identifier.fillna(False)
    out["ncen_etf_validated"] = (
        out["ncen_is_etf"] & ticker_identity_compatible
        & out["ncen_name_compatible"] & out["ncen_temporal_match"]
    )
    out["exchange_etf_validated"] = (
        out["exchange_etf"] & ticker_identity_compatible
        & (out["exchange_name_compatible"] | out["recent_identifier"])
    )
    out["ticker_identity_conflict"] = (
        (out["ncen_is_etf"] & ~out["ncen_etf_validated"])
        | (out["exchange_etf"] & ~out["exchange_etf_validated"])
    )

    # A seed ticker is useful when OpenFIGI is temporarily unavailable, but
    # OpenFIGI remains the canonical bridge for newly discovered CUSIPs.
    seed_ticker = out.get("seed_ticker", pd.Series("", index=out.index)).map(normalize_ticker)
    out["ticker"] = out["ticker"].where(out["ticker"].ne(""), seed_ticker)
    ncen_name = ncen_name_raw
    ncen_name = ncen_name.where(out["ncen_etf_validated"], "")
    exchange_name = exchange_name_raw.where(out["exchange_etf_validated"], "")
    series_name = series_name_raw.where(out["historical_series_etf"], "")
    figi_name = out.get("openfigi_name", pd.Series("", index=out.index)).fillna("")
    seed_name = out.get("seed_name", pd.Series("", index=out.index)).fillna("")
    issuer = out.get("issuer", pd.Series("", index=out.index)).fillna("")
    out["name"] = ncen_name.where(ncen_name.ne(""), exchange_name)
    out["name"] = out["name"].where(out["name"].ne(""), series_name)
    out["name"] = out["name"].where(out["name"].ne(""), figi_name)
    out["name"] = out["name"].where(out["name"].ne(""), seed_name)
    out["name"] = out["name"].where(out["name"].ne(""), issuer)

    out["is_etf"] = (
        out["ncen_etf_validated"] | out["exchange_etf_validated"]
        | out["historical_series_etf"] | out["seed_is_etf"]
    )
    out["classification_conflict"] = (
        out["ticker_identity_conflict"]
        | (
            out["ncen_etf_validated"]
            & out["exchange_match"]
            & ~out["exchange_etf"]
        )
    )
    out["confidence"] = np.select(
        [
            out["ncen_etf_validated"] & out["exchange_etf_validated"],
            out["ncen_etf_validated"],
            out["exchange_etf_validated"],
            out["historical_series_etf"],
            out["seed_is_etf"],
            out["known_common_stock"],
            out["figi_etf_hint"],
        ],
        [
            "regulatory_and_exchange", "regulatory", "exchange",
            "historical_regulatory_bridge", "verified_seed", "known_common_stock",
            "openfigi_candidate",
        ],
        default="unconfirmed",
    )
    out["verification_source"] = out.apply(
        lambda row: ";".join([
            source for source, present in [
                ("SEC_NCEN", bool(row["ncen_etf_validated"])),
                ("NASDAQ_DIRECTORY", bool(row["exchange_etf_validated"])),
                ("SEC_SERIES_CLASS+OPENFIGI_ETP", bool(row["historical_series_etf"])),
                ("VERIFIED_SEED", bool(row["seed_is_etf"])),
            ] if present
        ]),
        axis=1,
    )

    inferred_asset = out["name"].fillna("").map(_classify_asset)
    seed_asset = out.get("seed_asset_class", pd.Series(pd.NA, index=out.index))
    out["asset_class"] = seed_asset.where(seed_asset.notna(), inferred_asset)
    inferred_style = pd.Series([
        _classify_style(str(name), bool(multi))
        for name, multi in zip(
            out["name"].fillna(""),
            out["ncen_is_multi_inverse"] & out["ncen_etf_validated"],
        )
    ], index=out.index)
    seed_style = out.get("seed_etf_style", pd.Series(pd.NA, index=out.index))
    out["etf_style"] = seed_style.where(seed_style.notna(), inferred_style)
    style_score = out["etf_style"].map({
        "broad": 0.0, "other": 0.0, "factor": 0.5,
        "sector": 1.0, "industry": 1.0,
        "country": 1.0, "thematic": 1.0, "leveraged_inverse": 1.0,
        "commodity": 1.0,
    }).fillna(0.0)
    seed_score = pd.to_numeric(
        out.get("seed_specialized_score", pd.Series(np.nan, index=out.index)), errors="coerce"
    )
    out["specialized_score"] = seed_score.where(seed_score.notna(), style_score)

    # Carry product traits from the strongest alias to every identifier for
    # that ticker.  This makes a CUSIP and its filing FIGI interchangeable in
    # the holdings join without counting the ETF twice in the cross-section.
    # Seed metadata wins, followed by a non-unknown inferred asset class and
    # then the identifier with the greatest historical disclosed value.
    product_member = out["is_etf"] & out["ticker"].fillna("").ne("")
    product_priority = (
        100 * seed_asset.notna().astype(int)
        + 20 * out["ncen_etf_validated"].astype(int)
        + 10 * out["exchange_etf_validated"].astype(int)
        + 5 * out["asset_class"].ne("unknown").astype(int)
    )
    canonical = out.loc[product_member].assign(
        _product_priority=product_priority.loc[product_member],
        _product_value=pd.to_numeric(
            out.loc[product_member].get(
                "disclosed_value_usd", pd.Series(0.0, index=out.index)
            ),
            errors="coerce",
        ).fillna(0.0),
    ).sort_values(
        ["ticker", "_product_priority", "_product_value"],
        ascending=[True, False, False],
    ).drop_duplicates("ticker").set_index("ticker")
    for column in ["asset_class", "etf_style", "specialized_score"]:
        product_value = out["ticker"].map(canonical[column])
        out.loc[product_member, column] = product_value.loc[product_member]

    out["is_equity_etf"] = out["is_etf"] & out["asset_class"].eq("equity")
    index_name = out["name"].fillna("").str.contains(
        r"\b(?:INDEX|S&P|RUSSELL|MSCI|NASDAQ|DOW[ -]JONES|FTSE|BLOOMBERG)\b",
        case=False, regex=True, na=False,
    )
    seed_index = out["seed_is_etf"] & out["etf_style"].isin(
        ["broad", "sector", "industry", "country", "factor"]
    )
    raw_index = (
        (out["ncen_is_index"] & out["ncen_etf_validated"])
        | index_name | seed_index
    )
    product_index = raw_index.where(product_member).groupby(out["ticker"]).transform("max")
    out["is_index_fund"] = out["is_etf"] & product_index.fillna(False)
    out["index_classification_source"] = np.select(
        [out["is_etf"] & out["ncen_is_index"] & out["ncen_etf_validated"],
         out["is_etf"] & index_name,
         out["is_etf"] & seed_index],
        ["SEC_NCEN", "benchmark_name_rule", "verified_seed_style"],
        default="unclassified",
    )
    out["is_passive_etf"] = out["is_etf"] & out["is_index_fund"]
    out["is_passive_equity_etf"] = out["is_equity_etf"] & out["is_index_fund"]
    out["asset_class_source"] = np.where(
        seed_asset.notna(), "verified_seed", np.where(
            inferred_asset.ne("unknown"), "name_rule", "unknown"
        )
    )
    out["is_specific"] = out["etf_style"].isin(
        ["sector", "industry", "country", "factor", "thematic"]
    )
    return out.sort_values(
        ["is_passive_equity_etf", "is_equity_etf", "is_etf", "disclosed_value_usd"],
        ascending=[False, False, False, False],
        na_position="last",
    ).reset_index(drop=True)


@dataclass(frozen=True)
class BuildPaths:
    raw_dir: Path
    reference_dir: Path
    cache_path: Path
    flags_path: Path
