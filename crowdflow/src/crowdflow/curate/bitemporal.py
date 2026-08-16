"""The bitemporal holdings store.

Every 13F fact has two dates and conflating them is the single most common way
a 13F backtest acquires lookahead bias:

* **valid time** - the quarter the positions describe (``period_end``);
* **transaction time** - the instant the fact became public
  (``knowledge_ts``, derived from EDGAR's ``acceptanceDateTime``).

A naive pipeline keys on ``period_end`` alone and, for each quarter, uses the
latest available version of each filer's book. That is wrong in three ways at
once:

1. **The 45-day rule is a floor, not a schedule.** Filings are due 45 days after
   quarter end but arrive across a long tail; some filers are chronically late.
   Assuming the deadline overstates what was knowable.
2. **Amendments restate history.** A 13F-HR/A can land a year later and rewrite
   the quarter. Using the restated numbers at the original date is pure
   lookahead - and it is invisible, because the row looks perfectly ordinary.
3. **Confidential treatment.** A filer may obtain permission to omit positions
   from the original filing and disclose them only when the order expires,
   often four quarters later. Those positions genuinely did not exist in the
   public record at the time. A bitemporal store reproduces that ignorance; a
   period-keyed one cannot.

The store answers exactly one question, and answers it exactly:

    ``as_of(period_end, knowledge_ts)`` -> the holdings that a researcher
    sitting at ``knowledge_ts`` could have read for that quarter.

Amendment semantics follow the cover page's ``amendmentType``:

* ``RESTATEMENT`` - the amendment's table *replaces* everything previously on
  file for that (filer, period).
* ``NEW HOLDINGS`` - the table is *additive*; it carries only rows omitted from
  the original, which is the shape a lapsed confidential-treatment order takes.
* missing/unparseable - treated as a restatement, which is the conservative
  choice because it never invents holdings that were not in the amendment.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

REVISION_COLS = [
    "filer_id",
    "cik",
    "period_end",
    "accession",
    "form",
    "amendment_type",
    "amendment_no",
    "knowledge_ts",
    "acceptance_dt",
    "confidential_omitted",
    "n_rows",
    "book_usd",
]


def derive_knowledge_ts(acceptance_dt: pd.Series, cutoff_hour_et: int = 16) -> pd.Series:
    """Timestamp from which a filing may be acted upon.

    EDGAR stamps ``acceptanceDateTime`` with a ``Z`` suffix and it means what it
    says: the value is **UTC, not Eastern**. This is worth stating because the
    field is often assumed to be ET, and assuming wrongly shifts the tradeable
    date by a day for roughly half of all filings - EDGAR's daily receipt peak
    sits at 20-21h UTC, which is 16-17h ET, side of the close that decides
    whether the filing is actionable today or tomorrow.

    The check is empirical, not a reading of the docs: a filing stamped 22h that
    keeps the same ``filingDate`` can only be pre-cutoff if the stamp is UTC,
    because EDGAR closes same-day acceptance at 17:30 ET. See
    ``verify_acceptance_timezone`` below, which runs that test against whatever
    data is loaded rather than trusting this comment.

    We parse as UTC, convert to Eastern, and roll anything at or after the
    equity close to the next session, since a filing published after the close
    cannot be traded into that day. That is one day of conservatism at zero cost
    and it removes any need for the backtest to reason about intraday timing.
    """
    ts = pd.to_datetime(acceptance_dt, errors="coerce", utc=True).dt.tz_convert("America/New_York")
    rolled = ts.dt.normalize()
    late = ts.dt.hour >= cutoff_hour_et
    rolled = rolled.where(~late, rolled + pd.Timedelta(days=1))
    return rolled.dt.tz_localize(None)


@dataclass
class HoldingsStore:
    """Append-only holdings versions plus the revision log that orders them."""

    holdings: pd.DataFrame  # one row per (accession, instrument)
    revisions: pd.DataFrame  # one row per accession

    # Lazily built lookup tables. ``as_of`` is called once per quarter per
    # rebalance and many hundreds of times by the audits, and a boolean scan of
    # the full holdings frame on each call dominates the runtime once the panel
    # reaches a few hundred thousand rows. Positional indices per accession turn
    # that scan into a concatenate-and-take.
    _row_index: dict[str, np.ndarray] | None = None
    _seq_map: pd.Series | None = None

    def _index(self) -> dict[str, np.ndarray]:
        if self._row_index is None:
            groups = self.holdings.groupby("accession", sort=False).indices
            self._row_index = {k: np.asarray(v) for k, v in groups.items()}
        return self._row_index

    def _seq(self) -> pd.Series:
        if self._seq_map is None:
            self._seq_map = self.revisions.set_index("accession")["seq"]
        return self._seq_map

    # ------------------------------------------------------------------ #
    @classmethod
    def build(cls, holdings: pd.DataFrame, revisions: pd.DataFrame) -> HoldingsStore:
        rev = revisions.copy()
        rev["period_end"] = pd.to_datetime(rev["period_end"])
        rev["knowledge_ts"] = pd.to_datetime(rev["knowledge_ts"])
        rev["amendment_type"] = (
            rev["amendment_type"].fillna("").astype(str).str.upper().str.strip()
        )
        rev["is_amendment"] = rev["form"].str.endswith("/A")

        # The unit of *versioning* is the registrant (the CIK), never the
        # economic identity. ``filer_id`` may merge several CIKs into one
        # family via config/families.yaml, and family members file distinct,
        # co-valid books: sibling A's 13F-HR does not supersede sibling B's.
        # Folding on filer_id made exactly that mistake - the family's later
        # original silently replaced the earlier one and half the family book
        # vanished with no error. Amendment chains, by contrast, are always
        # within one registrant, which is what makes the CIK the correct key.
        # ``filer_id`` remains the aggregation label everywhere downstream.
        rev["_vkey"] = rev["cik"] if "cik" in rev.columns else rev["filer_id"]

        # Deterministic fold order. Ties on knowledge_ts (same-day amendments)
        # break on amendment number, then on accession, so the materialised
        # view never depends on row order in the input.
        rev = rev.sort_values(
            ["_vkey", "period_end", "knowledge_ts", "amendment_no", "accession"],
            na_position="first",
        ).reset_index(drop=True)
        rev["seq"] = rev.groupby(["_vkey", "period_end"]).cumcount()

        hold = holdings.copy()
        hold["period_end"] = pd.to_datetime(hold["period_end"])
        return cls(hold, rev)

    # ------------------------------------------------------------------ #
    def _applicable(
        self,
        period_end: pd.Timestamp,
        asof: pd.Timestamp,
        filers: set[str] | None = None,
    ) -> pd.DataFrame:
        r = self.revisions
        mask = (r["period_end"] == period_end) & (r["knowledge_ts"] <= asof)
        if filers is not None:
            mask &= r["filer_id"].isin(filers)
        return r[mask]

    def as_of(
        self,
        period_end: str | pd.Timestamp,
        asof: str | pd.Timestamp,
        *,
        return_provenance: bool = False,
        filers: set[str] | None = None,
    ) -> pd.DataFrame:
        """Materialise one quarter's holdings as known at ``asof``.

        ``filers`` narrows the fold to a subset of managers. The result is
        identical to filtering the full view afterwards - filers never share
        accessions - but it avoids materialising a whole quarter to inspect one
        manager, which is what the audits do hundreds of times.
        """
        period_end = pd.Timestamp(period_end)
        asof = pd.Timestamp(asof)
        applicable = self._applicable(period_end, asof, filers)
        if applicable.empty:
            return self.holdings.iloc[:0].copy()

        # Fold per registrant: an original supersedes only within its own CIK.
        chosen: list[str] = []
        for _, grp in applicable.groupby("_vkey", sort=False):
            grp = grp.sort_values("seq")
            stack: list[str] = []
            for row in grp.itertuples():
                if not row.is_amendment:
                    stack = [row.accession]  # a fresh original supersedes
                elif row.amendment_type == "NEW HOLDINGS":
                    stack.append(row.accession)
                else:  # RESTATEMENT, or unflagged -> conservative replace
                    stack = [row.accession]
            chosen.extend(stack)

        idx = self._index()
        parts = [idx[a] for a in chosen if a in idx]
        if not parts:
            return self.holdings.iloc[:0].copy()
        view = self.holdings.take(np.concatenate(parts)).copy()

        # An additive amendment can still repeat a line already on file. Keep
        # the latest version of each (registrant, instrument) by fold order.
        # Keyed on the registrant, not the family: two merged siblings holding
        # the same name are two real positions whose sum is the family's
        # position, and deduplicating across them would delete one.
        dedup_entity = "cik" if "cik" in view.columns else "filer_id"
        view["_seq"] = view["accession"].map(self._seq())
        view = (
            view.sort_values("_seq")
            .drop_duplicates(subset=[dedup_entity, "instrument_id", "put_call"], keep="last")
            .drop(columns="_seq")
        )
        view["knowledge_asof"] = asof
        if return_provenance:
            view = view.merge(
                self.revisions[["accession", "form", "amendment_type", "knowledge_ts"]],
                on="accession",
                how="left",
            )
        return view.reset_index(drop=True)

    # ------------------------------------------------------------------ #
    def panel_as_of(
        self,
        periods: list[str | pd.Timestamp],
        asof: str | pd.Timestamp,
    ) -> pd.DataFrame:
        """Several quarters, all seen from the same vantage point."""
        frames = [self.as_of(p, asof) for p in periods]
        frames = [f for f in frames if not f.empty]
        return pd.concat(frames, ignore_index=True) if frames else self.holdings.iloc[:0].copy()

    # ------------------------------------------------------------------ #
    def restatement_audit(self) -> pd.DataFrame:
        """How much a naive period-keyed pipeline would have leaked.

        For each amended (filer, period) we compare the first public book with
        the final one. The dollar delta is the size of the lookahead an
        as-reported-latest pipeline would have quietly enjoyed.
        """
        amended = self.revisions[self.revisions["is_amendment"]]
        rows = []
        for (filer, period), grp in amended.groupby(["filer_id", "period_end"]):
            first_ts = self.revisions[
                (self.revisions["filer_id"] == filer) & (self.revisions["period_end"] == period)
            ]["knowledge_ts"].min()
            last_ts = grp["knowledge_ts"].max()
            v0 = self.as_of(period, first_ts, filers={filer})
            v1 = self.as_of(period, last_ts, filers={filer})
            rows.append(
                {
                    "filer_id": filer,
                    "period_end": period,
                    "first_knowledge": first_ts,
                    "final_knowledge": last_ts,
                    "lag_days": (last_ts - first_ts).days,
                    "n_rows_first": len(v0),
                    "n_rows_final": len(v1),
                    "book_first": v0["value_usd"].sum(),
                    "book_final": v1["value_usd"].sum(),
                    "amendment_types": "|".join(sorted(set(grp["amendment_type"]))),
                }
            )
        out = pd.DataFrame(rows)
        if not out.empty:
            out["book_delta_pct"] = np.where(
                out["book_first"] > 0, out["book_final"] / out["book_first"] - 1.0, np.nan
            )
        return out

    def verify_acceptance_timezone(self) -> pd.DataFrame:
        """Test the UTC assumption against the data instead of asserting it.

        For each raw hour in ``acceptance_dt``, the share of filings whose
        *EDGAR-assigned* ``filing_date`` equals the stamp's own date. EDGAR
        rolls anything accepted after 17:30 ET to the next business day, so the
        two readings make opposite predictions:

        * stamps are **ET**: same-day share collapses from raw hour 18 onward;
        * stamps are **UTC**: the collapse appears around raw hour 22
          (= 18h ET), and hours 18-21 raw stay overwhelmingly same-day.

        A collapse at raw 18h means ``derive_knowledge_ts`` is off by four or
        five hours and every knowledge date built from it is suspect.

        An earlier version of this method compared the acceptance date against
        itself - tautologically 100% same-day, a diagnostic that could not
        fail. The comparison must be against ``filing_date``, which EDGAR
        assigns independently of how we parse the timestamp.
        """
        r = self.revisions.copy()
        if "filing_date" not in r.columns:
            raise ValueError(
                "revisions carry no filing_date column; rebuild the store from a "
                "curate run that includes it. Without the independently assigned "
                "filing date this check has nothing to compare against."
            )
        ts = pd.to_datetime(r["acceptance_dt"], errors="coerce", utc=True).dt.tz_localize(None)
        fd = pd.to_datetime(r["filing_date"], errors="coerce")
        ok = ts.notna() & fd.notna()
        r, ts, fd = r[ok], ts[ok], fd[ok]
        r["raw_hour"] = ts.dt.hour
        r["same_day"] = ts.dt.normalize().eq(fd.dt.normalize())
        out = (
            r.groupby("raw_hour")
            .agg(n=("accession", "size"), same_day_share=("same_day", "mean"))
            .reset_index()
        )
        out["hour_et"] = (out["raw_hour"] - 4) % 24  # EDT; EST differs by one
        out["past_edgar_cutoff_if_utc"] = out["hour_et"] >= 18
        return out

    def filing_lag_profile(self) -> pd.DataFrame:
        """Empirical distribution of the reporting lag - the 45-day rule tested.

        Used to set the rebalance calendar from data instead of from the
        regulation, and to show how heavy the right tail actually is.
        """
        r = self.revisions.copy()
        r["lag_days"] = (r["knowledge_ts"] - r["period_end"]).dt.days
        originals = r[~r["is_amendment"]]
        return (
            originals.groupby(originals["period_end"].dt.to_period("Q"))["lag_days"]
            .agg(
                n="size",
                p05=lambda s: s.quantile(0.05),
                median="median",
                p90=lambda s: s.quantile(0.90),
                p99=lambda s: s.quantile(0.99),
                worst="max",
                pct_by_day_45=lambda s: (s <= 45).mean(),
            )
            .reset_index()
        )
