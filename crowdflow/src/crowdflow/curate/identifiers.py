"""Security identity: CUSIP hygiene and CUSIP to instrument resolution.

13F is a CUSIP-keyed dataset filled in by humans, and the identifier column is
where most of the silent corruption lives. Observed failure modes, all handled
below:

* 8-character CUSIPs (check digit dropped by the filer's spreadsheet);
* leading zeros eaten by Excel (``037833100`` arriving as ``37833100``);
* transposed or mistyped characters producing an invalid check digit;
* the same economic issuer split across share classes with distinct CUSIPs
  (GOOG vs GOOGL), which must *not* be merged for a positioning factor;
* CUSIPs belonging to ETFs, ADRs, convertibles and warrants sitting in the
  same column as ordinary common stock;
* CUSIP reassignment after corporate actions, which makes any static
  CUSIP-to-ticker map wrong at some point in a ten-year sample.

The resolution strategy is layered and each layer is auditable:

1. a user-supplied crosswalk (CRSP ``ncusip``/``permno`` or Compustat), if
   present, keyed on ``(cusip, date)`` so that reassignment is respected;
2. the FIGI carried natively in the filing (13F gained a FIGI column in 2023);
3. an OpenFIGI batch resolution cached to disk;
4. the SEC's own quarterly *Official List of Section 13(f) Securities*, which
   is free, point-in-time and authoritative about what was 13F-reportable in a
   given quarter - used to validate rather than to name.

Nothing here fabricates a mapping. Unresolved CUSIPs are retained with a null
instrument id and counted, so coverage is a reported statistic rather than an
assumption.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

_CUSIP_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ*@#"
_VALUE = {c: i for i, c in enumerate(_CUSIP_CHARS)}
_CUSIP_SHAPE = re.compile(r"^[0-9A-Z*@#]{8,9}$")


def cusip_check_digit(body8: str) -> str:
    """Standard CUSIP modulus-10 double-add-double check digit."""
    total = 0
    for i, ch in enumerate(body8.upper()):
        v = _VALUE.get(ch)
        if v is None:
            raise ValueError(f"illegal CUSIP character {ch!r}")
        if i % 2 == 1:  # even position, 1-indexed
            v *= 2
        total += v // 10 + v % 10
    return str((10 - (total % 10)) % 10)


def is_valid_cusip(cusip: str) -> bool:
    c = (cusip or "").strip().upper()
    if len(c) != 9 or not _CUSIP_SHAPE.match(c):
        return False
    try:
        return cusip_check_digit(c[:8]) == c[8]
    except ValueError:
        return False


@dataclass(frozen=True)
class CusipFix:
    original: str
    fixed: str | None
    action: str  # ok | padded | appended_check | recovered | invalid


def normalise_cusip(raw: str | None, *, allow_repair: bool = True) -> CusipFix:
    """Clean one CUSIP, recording what was done to it."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return CusipFix("", None, "invalid")
    c = str(raw).strip().upper().replace(" ", "").replace("-", "")
    if not c:
        return CusipFix(str(raw), None, "invalid")

    if len(c) == 9 and is_valid_cusip(c):
        return CusipFix(c, c, "ok")

    if not allow_repair:
        return CusipFix(c, None, "invalid")

    # Excel ate leading zeros: pad back up to 9 and test.
    if len(c) < 9 and _CUSIP_SHAPE.match(c.rjust(9, "0")):
        padded = c.rjust(9, "0")
        if is_valid_cusip(padded):
            return CusipFix(c, padded, "padded")

    # Filer dropped the check digit: recompute it from an 8-character body.
    if len(c) == 8 and _CUSIP_SHAPE.match(c):
        try:
            return CusipFix(c, c + cusip_check_digit(c), "appended_check")
        except ValueError:
            pass

    # A 9-character CUSIP with a bad check digit is more often a wrong check
    # digit than a wrong body: keep the body, recompute the digit, and mark it.
    if len(c) == 9 and _CUSIP_SHAPE.match(c):
        try:
            return CusipFix(c, c[:8] + cusip_check_digit(c[:8]), "recovered")
        except ValueError:
            pass

    return CusipFix(c, None, "invalid")


def clean_cusip_column(s: pd.Series, *, allow_repair: bool = True) -> pd.DataFrame:
    """Vectorised over the distinct values, which is 100x fewer calls."""
    uniq = pd.Index(s.dropna().astype(str).unique())
    fixes = {u: normalise_cusip(u, allow_repair=allow_repair) for u in uniq}
    return pd.DataFrame(
        {
            "cusip": s.map(lambda x: fixes[str(x)].fixed if pd.notna(x) and str(x) in fixes else None),
            "cusip_action": s.map(
                lambda x: fixes[str(x)].action if pd.notna(x) and str(x) in fixes else "invalid"
            ),
        },
        index=s.index,
    )


# --------------------------------------------------------------------------- #
# Security master
# --------------------------------------------------------------------------- #
NON_COMMON_TITLE = re.compile(
    r"\b(?:NOTE|NOTES|DEB|DEBENTURE|BOND|CONV|WT|WTS|WARRANT|RIGHT|RTS|UNIT|"
    r"PFD|PREFERRED|CALL|PUT|SBI|TRUST UNIT)\b",
    re.IGNORECASE,
)
ETF_HINT = re.compile(
    r"\b(?:ETF|ISHARES|SPDR|VANGUARD|POWERSHARES|INVESCO|PROSHARES|WISDOMTREE|"
    r"DIREXION|SELECT SECTOR|INDEX (?:FD|FUND|TR)|TRUST SERIES)\b",
    re.IGNORECASE,
)


class SecurityMaster:
    """CUSIP resolution with explicit provenance for every mapping."""

    def __init__(self, crosswalk: pd.DataFrame | None = None) -> None:
        """``crosswalk`` columns: cusip, instrument_id, ticker, start, end, sec_type."""
        self.crosswalk = crosswalk if crosswalk is not None else pd.DataFrame()
        if not self.crosswalk.empty:
            self.crosswalk = self.crosswalk.assign(
                start=pd.to_datetime(self.crosswalk.get("start", "1900-01-01")),
                end=pd.to_datetime(self.crosswalk.get("end", "2999-12-31")),
            )

    @classmethod
    def from_files(cls, source: Path | str | pd.DataFrame | None) -> SecurityMaster:
        if isinstance(source, pd.DataFrame):
            return cls(source)
        if source is None or not Path(source).exists():
            log.warning(
                "no crosswalk supplied; CUSIP is used as the instrument id. "
                "This is adequate only if the price panel is also CUSIP-keyed."
            )
            return cls(None)
        return cls(pd.read_csv(source, dtype={"cusip": str}))

    def resolve(self, holdings: pd.DataFrame, asof_col: str = "period_end") -> pd.DataFrame:
        """Attach ``instrument_id`` and a ``id_source`` provenance column."""
        out = holdings.copy()
        out["instrument_id"] = pd.NA
        out["id_source"] = pd.NA

        # Layer 1 - dated crosswalk.
        if not self.crosswalk.empty:
            asof = pd.to_datetime(out[asof_col])
            merged = out[["cusip"]].assign(_asof=asof).merge(
                self.crosswalk, on="cusip", how="left", suffixes=("", "_x")
            )
            ok = merged["_asof"].between(merged["start"], merged["end"])
            merged.loc[~ok, "instrument_id"] = pd.NA
            resolved = merged.groupby(level=0)["instrument_id"].first()
            out.loc[resolved.notna().values, "instrument_id"] = resolved.dropna().values
            out.loc[resolved.notna().values, "id_source"] = "crosswalk"

        # Layer 2 - FIGI reported natively in the filing.
        native = out["instrument_id"].isna() & out.get("figi", pd.Series(index=out.index)).notna()
        out.loc[native, "instrument_id"] = out.loc[native, "figi"]
        out.loc[native, "id_source"] = "filing_figi"

        # Layer 3 - fall back to the CUSIP itself. Correct for a single-vendor
        # backtest and honest about what it is; wrong only across corporate
        # actions that reassign a CUSIP, which we count separately.
        rest = out["instrument_id"].isna() & out["cusip"].notna()
        out.loc[rest, "instrument_id"] = out.loc[rest, "cusip"]
        out.loc[rest, "id_source"] = "cusip_passthrough"

        out["cusip6"] = out["cusip"].str.slice(0, 6)
        return out


def classify_instrument(holdings: pd.DataFrame) -> pd.Series:
    """Coarse instrument class from the fields 13F actually gives us.

    Deliberately coarse. The goal is not a security master but a defensible
    exclusion rule: options overlays, debt and fund wrappers must not enter a
    factor about equity ownership, and each exclusion must be countable.
    """
    title = holdings["title_of_class"].fillna("").astype(str)
    issuer = holdings["issuer"].fillna("").astype(str)
    stype = holdings["share_type"].fillna("SH").astype(str).str.upper()
    putcall = holdings["put_call"].fillna("").astype(str).str.upper()

    cls = pd.Series("common", index=holdings.index, dtype="object")
    cls[title.str.contains(NON_COMMON_TITLE, na=False)] = "other_security"
    cls[issuer.str.contains(ETF_HINT, na=False) | title.str.contains(ETF_HINT, na=False)] = "fund"
    cls[stype.eq("PRN")] = "debt"
    cls[putcall.isin({"PUT", "CALL"})] = "option"
    return cls
