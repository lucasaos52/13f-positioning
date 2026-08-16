"""Filer identity and the double-counting problem.

Form 13F is filed by the *institutional investment manager*, not by the fund,
and the mapping between the two is many-to-many. Three distinct hazards:

**Notices.** A manager whose positions are reported by someone else files a
13F-NT. It contains no holdings. Counting it as a filer with a zero book
corrupts every cross-sectional statistic.

**Combination reports.** Manager A may file holdings on behalf of A, B and C,
listing B and C on the cover page. If B independently files its own 13F-HR for
the same positions, naive concatenation double counts them - and double
counting is fatal for a *crowding* factor specifically, because the same
dollars appear as two managers agreeing with each other.

**Firm families.** One firm can hold many CIKs. Automated name matching is
tempting and dangerous: "Capital Management LLC" is not a discriminating
string, and a false merge silently collapses two genuinely independent
decision-makers into one. We therefore default to CIK-level identity, expose
the candidate clusters as a diagnostic, and only merge from an explicit
override file that a human has signed off on.

The economic argument for CIK-level identity is not merely convenience. The
filer is the entity with a single compliance perimeter and, usually, a single
risk system - which is the level at which correlated liquidation actually
happens. A multi-manager platform is the genuine counterexample, and it is
exactly the case the override file exists for.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pandas as pd
import yaml

log = logging.getLogger(__name__)

_SUFFIX = re.compile(
    r"\b(?:LLC|L\.L\.C|LP|L\.P|LTD|LIMITED|INC|INCORPORATED|CORP|CORPORATION|CO|COMPANY|"
    r"PLC|SA|NV|AG|GMBH|TRUST|GROUP|HOLDINGS?|PARTNERS?|PARTNERSHIP|MANAGEMENT|MGMT|"
    r"ADVISORS?|ADVISERS?|CAPITAL|ASSET|ASSETS|INVESTMENTS?|INVESTMENT|FUND|FUNDS|"
    r"INTERNATIONAL|GLOBAL|AMERICAS?|USA?|LLP|SARL|SPA|PTE|AB|AS|OY)\b",
    re.IGNORECASE,
)


def normalise_name(name: str) -> str:
    """Aggressive normalisation, used only to *propose* clusters for review."""
    s = re.sub(r"[^A-Za-z0-9 ]", " ", str(name).upper())
    s = _SUFFIX.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def load_family_overrides(path: Path | None) -> dict[int, str]:
    """Read manual family merges -> ``{cik: family_name}``.

    Two YAML shapes are accepted. The documented one, which carries the
    audit trail that makes a merge defensible::

        families:
          - name: SOME PLATFORM
            ciks: [1000004, 1000011]
            note: why, and who signed off

    and the terse one, ``family_name: [cik, cik, ...]``, kept because it is
    convenient in tests. Accepting only the terse shape while the config file
    documents the structured one was a live bug: a correctly written override
    file raised ``TypeError`` on load, which punishes exactly the user who read
    the documentation.
    """
    if path is None or not Path(path).exists():
        return {}
    blob = yaml.safe_load(Path(path).read_text()) or {}
    if not isinstance(blob, dict):
        raise ValueError(f"{path}: expected a mapping at top level, got {type(blob).__name__}")
    entries = blob.get("families")
    if entries is not None:  # structured, documented shape
        out: dict[int, str] = {}
        for e in entries or []:
            if not isinstance(e, dict) or "name" not in e:
                raise ValueError(f"{path}: each family entry needs a 'name' and 'ciks' list, got {e!r}")
            for cik in e.get("ciks", []):
                out[int(cik)] = str(e["name"])
        return out
    return {int(cik): fam for fam, ciks in blob.items() for cik in ciks}


def assign_filer_id(manifest: pd.DataFrame, overrides: dict[int, str]) -> pd.DataFrame:
    """``filer_id`` is the CIK unless a human has mapped it into a family."""
    out = manifest.copy()
    out["filer_id"] = out["cik"].map(lambda c: overrides.get(int(c), f"CIK{int(c):010d}"))
    out["name_key"] = out["company"].map(normalise_name)
    return out


def propose_family_clusters(manifest: pd.DataFrame, min_size: int = 2) -> pd.DataFrame:
    """Diagnostic only: CIKs sharing a normalised name. Never applied silently."""
    g = (
        manifest.drop_duplicates("cik")
        .groupby("name_key")
        .agg(ciks=("cik", list), names=("company", list), n=("cik", "size"))
        .reset_index()
    )
    return g[(g["n"] >= min_size) & (g["name_key"].str.len() > 3)].sort_values("n", ascending=False)


# --------------------------------------------------------------------------- #
# Reporting groups
# --------------------------------------------------------------------------- #
def build_reporting_groups(covers: pd.DataFrame) -> pd.DataFrame:
    """Resolve who reports for whom, per (period, filing-cohort).

    ``covers`` needs: filer_id, cik, period_end, accession, report_type,
    other_managers (list[int]), n_rows, book_usd.

    Returns the same frame plus ``group_id`` and ``keep``, where ``keep`` marks
    the single filing that should represent the group's holdings.
    """
    df = covers.copy()
    df["is_notice"] = df["report_type"].fillna("").str.upper().str.contains("NOTICE")

    # Union-find over the (filer, other-manager) edges, within a period.
    parent: dict[tuple[str, str], tuple[str, str]] = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    cik_to_filer = dict(zip(df["cik"].astype(int), df["filer_id"]))
    for row in df.itertuples():
        node = (row.period_end, row.filer_id)
        find(node)
        for other in row.other_managers or []:
            other_filer = cik_to_filer.get(int(other))
            if other_filer:
                union(node, (row.period_end, other_filer))

    df["group_id"] = [
        "|".join(map(str, find((r.period_end, r.filer_id)))) for r in df.itertuples()
    ]

    # Within a group: notices never carry holdings; among the rest keep the
    # filing with the largest book, which is the aggregator by construction.
    #
    # Amendments are deliberately excluded from this contest. An amendment is
    # not a competing report, it is a later version of one, and it will almost
    # always carry a slightly different book. Letting it compete means a filer's
    # own 13F-HR/A subsumes its 13F-HR, the original vanishes from the revision
    # log, and ``as_of`` then claims the filer had disclosed nothing at all
    # between the two dates. Versioning is the bitemporal fold's job; this
    # function only decides *which filer* speaks for the group.
    df["is_amendment"] = (
        df["form"].astype(str).str.endswith("/A")
        if "form" in df.columns
        else pd.Series(False, index=df.index)
    )
    df["keep"] = False

    eligible = df[~df["is_notice"] & ~df["is_amendment"] & df["n_rows"].fillna(0).gt(0)]
    winners = eligible.sort_values(
        ["group_id", "book_usd", "n_rows"], ascending=[True, False, False]
    ).drop_duplicates("group_id")
    df.loc[winners.index, "keep"] = True

    # A group whose only filings are amendments (the original was a notice, or
    # predates the sample window) still needs a representative.
    orphan_groups = set(df["group_id"]) - set(winners["group_id"])
    if orphan_groups:
        orphans = df[
            df["group_id"].isin(orphan_groups)
            & df["is_amendment"]
            & df["n_rows"].fillna(0).gt(0)
        ]
        orphan_winners = orphans.sort_values(
            ["group_id", "book_usd", "n_rows"], ascending=[True, False, False]
        ).drop_duplicates("group_id")
        df.loc[orphan_winners.index, "keep"] = True

    # Amendments ride along with the filer that won the group, so that an
    # amendment to a subsumed filing is dropped with its parent.
    speaks_for_group = set(zip(df.loc[df["keep"], "period_end"], df.loc[df["keep"], "filer_id"]))
    rider = df["is_amendment"] & pd.Series(
        [(p, f) in speaks_for_group for p, f in zip(df["period_end"], df["filer_id"])],
        index=df.index,
    )
    df.loc[rider, "keep"] = True

    dropped = int((~df["keep"]).sum())
    log.info(
        "reporting groups: %d filings -> %d kept (%d notices, %d subsumed)",
        len(df),
        int(df["keep"].sum()),
        int(df["is_notice"].sum()),
        dropped - int(df["is_notice"].sum()),
    )
    return df


def detect_residual_duplication(holdings: pd.DataFrame, tol: float = 1e-9) -> pd.DataFrame:
    """Rows identical in (period, cusip, shares) across different filers.

    After group resolution this should be rare; a spike is a signal that the
    cover-page ``otherManagers`` graph missed a relationship, which happens when
    a filer lists managers by name only. Reported, not auto-corrected.
    """
    key = ["period_end", "cusip", "shares"]
    dup = holdings[holdings["shares"].fillna(0) > 0]
    counts = dup.groupby(key)["filer_id"].nunique()
    suspects = counts[counts > 1].reset_index(name="n_filers")
    return suspects.merge(dup, on=key, how="left")


# --------------------------------------------------------------------------- #
# Succession
# --------------------------------------------------------------------------- #
def detect_cik_succession(
    manifest: pd.DataFrame,
    max_gap_quarters: int = 2,
    min_name_similarity: float = 0.50,
) -> pd.DataFrame:
    """Propose cases where one CIK took over another's filing obligation.

    ``otherManagers`` resolves who reports for whom *within* a quarter. It says
    nothing about a manager that re-registers under a new CIK and simply stops
    filing under the old one. Those are invisible to the union-find and they
    matter twice over:

    * the manager's history is truncated at the handover, so the eligibility
      screen (minimum quarters of history) rejects a manager that has in fact
      been filing for a decade;
    * the universe sees a spurious exit and a spurious entry in the middle of
      the sample, which inflates measured turnover and corrupts the hysteresis
      band that is supposed to be suppressing exactly that noise.

    The signature is a clean handoff: CIK A's last period is adjacent to CIK B's
    first, with no overlap, and the names are similar after suffix stripping.
    Adjacency alone is far too weak - hundreds of unrelated filers start and
    stop every quarter - so both conditions must hold, and even then this
    function only *proposes*. Nothing is merged until a human copies the pair
    into ``config/families.yaml``, because a wrong merge splices two unrelated
    books into one track record and there is no way to detect that downstream.

    Two details are calibrated against the best-documented real handoff on
    EDGAR (Citadel's 2009Q3->2009Q4 re-registration), which an earlier version
    of this function missed twice over:

    * **Spans count holdings reports only.** A successor entity often files
      13F-NT notices for several quarters before its first 13F-HR - the
      predecessor is still reporting the positions. Counting notices makes the
      lives appear to overlap and the overlap veto kills the true handoff.
      Notices are not evidence of an independent book, so they do not define
      the span.
    * **The similarity floor is 0.50, not higher.** Real handoffs keep the
      distinctive token and swap everything else, and with two or three tokens
      per normalised name the Jaccard of a true pair sits exactly at one half
      (one shared token, one differing). A floor above that silently rejects
      the canonical case while looking safely conservative.

    Candidate pairs are generated by indexing spans on their first quarter and
    probing only the ``max_gap_quarters`` quarters after each span ends, rather
    than crossing every filer with every other. Same result, and it keeps the
    scan linear-ish in the number of filers - a full EDGAR quarter has around
    ten thousand CIKs, where an all-pairs loop is a hundred million iterations.

    Returns one row per candidate with the evidence that produced it.
    """
    m = manifest.copy()
    if "form" in m.columns:  # keep 13F-HR / 13F-HR/A; drop notices and misc
        m = m[m["form"].astype(str).str.upper().str.startswith("13F-HR")]
    m["period"] = pd.to_datetime(m["period"])
    m["q"] = m["period"].dt.to_period("Q")

    span = (
        m.groupby(["cik", "company"], as_index=False)
        .agg(first_q=("q", "min"), last_q=("q", "max"), n_filings=("accession", "size"))
        .sort_values("first_q")
    )
    span["norm"] = span["company"].map(_succession_key)

    starts_by_q: dict = {}
    for b in span.itertuples():
        starts_by_q.setdefault(b.first_q, []).append(b)

    rows = []
    for a in span.itertuples():
        for gap in range(1, max_gap_quarters + 1):
            for b in starts_by_q.get(a.last_q + gap, []):
                if a.cik == b.cik:
                    continue
                sim = _name_similarity(a.norm, b.norm)
                if sim < min_name_similarity:
                    continue
                # The overlap must include a *distinctive* token. Measured on a
                # real six-window ingest (9.7k filers), Jaccard-with-adjacency
                # alone proposed 2,540 "clean handoffs", and the top of the
                # queue was pairs like "Sutton Wealth Advisors" -> "Muirfield
                # Wealth Advisors": the shared words are the generic trade
                # words, the distinctive ones differ - the exact inverse of a
                # real re-registration, which keeps the distinctive token and
                # swaps the wrapper.
                if not ((set(a.norm.split()) & set(b.norm.split())) - _GENERIC_TOKENS):
                    continue
                rows.append(
                    {
                        "predecessor_cik": a.cik,
                        "predecessor_name": a.company,
                        "predecessor_last_q": str(a.last_q),
                        "successor_cik": b.cik,
                        "successor_name": b.company,
                        "successor_first_q": str(b.first_q),
                        "gap_quarters": gap,
                        "name_similarity": round(sim, 3),
                        "clean_handoff": gap == 1,
                        "n_filings_before": a.n_filings,
                        "n_filings_after": b.n_filings,
                    }
                )

    # Always the full schema, even with zero rows: this frame is written to
    # disk as an audit artefact, and a column-less empty CSV cannot even be
    # reopened - "no candidates" and "broken output" must not look alike.
    cols = [
        "predecessor_cik", "predecessor_name", "predecessor_last_q",
        "successor_cik", "successor_name", "successor_first_q",
        "gap_quarters", "name_similarity", "clean_handoff",
        "n_filings_before", "n_filings_after",
    ]
    out = pd.DataFrame(rows, columns=cols)
    if not out.empty:
        out = out.sort_values(
            ["clean_handoff", "name_similarity"], ascending=[False, False]
        ).reset_index(drop=True)
        log.info(
            "succession: %d candidate pairs (%d clean handoffs). Review before merging.",
            len(out),
            int(out["clean_handoff"].sum()),
        )
    return out


_LEGAL_FORM = {
    "LP", "L", "P", "LLC", "LLP", "INC", "INCORPORATED", "CORP", "CORPORATION",
    "LTD", "LIMITED", "CO", "COMPANY", "PLC", "SA", "NV", "AG", "GMBH", "PTE",
    "THE", "AND", "OF",
}

# Trade words that appear in thousands of adviser names. Kept by
# ``_succession_key`` because they carry *weight* in the Jaccard (dropping
# them entirely would collapse "Example Capital" and "Example Advisors" to the
# same key), but an overlap consisting only of these is not evidence of shared
# identity - see the gate in ``detect_cik_succession``.
_GENERIC_TOKENS = {
    "WEALTH", "ADVISORS", "ADVISERS", "ADVISORY", "CAPITAL", "MANAGEMENT",
    "MGMT", "ASSET", "ASSETS", "INVESTMENT", "INVESTMENTS", "INVESTORS",
    "PARTNERS", "PARTNERSHIP", "FUND", "FUNDS", "GROUP", "FINANCIAL",
    "SECURITIES", "HOLDINGS", "TRUST", "COUNSEL", "ASSOCIATES", "STRATEGIES",
    "PLANNING", "PRIVATE", "GLOBAL", "INTERNATIONAL", "NATIONAL", "AMERICAN",
    "US", "USA",
    # Added after reviewing the full-history queue: pairs like "Meritage
    # Portfolio Management -> Vanguard Portfolio Management" and "Pathstone
    # Family Office -> Fortitude Family Office" cleared the gate on exactly
    # these words. They name what the firm does, not who it is.
    "PORTFOLIO", "STREET", "OFFICE", "FAMILY", "VALUE", "EQUITY", "RESEARCH",
}


def _succession_key(name: str) -> str:
    """Normalisation tuned for succession, deliberately lighter than
    ``normalise_name``.

    ``normalise_name`` strips business words as well as legal forms, which is
    right when the goal is to *propose* that two filers are the same house. Here
    it destroys the signal: "Example Capital L P" and "Example Capital Advisors
    LLC" both collapse to "Example", and so does every other filer whose name
    starts with the same word. Only legal-form tokens are removed, so the
    distinctive words - Capital, Advisors, Partners - still carry weight.
    """
    tokens = re.sub(r"[^A-Z0-9 ]+", " ", str(name).upper()).split()
    kept = [t for t in tokens if t not in _LEGAL_FORM]
    return " ".join(kept or tokens)


def _name_similarity(a: str, b: str) -> float:
    """Token Jaccard on normalised names.

    Token-based rather than character-based: in a real re-registration the
    firm keeps its distinctive token and swaps the corporate wrapper around
    it, so the shared tokens are the whole signal while the edit distance is
    large. Measured on the canonical case, "CITADEL L P" against "CITADEL
    ADVISORS LLC" normalises to {CITADEL} vs {CITADEL, ADVISORS} and scores
    exactly 0.50 - which is why the caller's floor sits at 0.50 and not at a
    rounder-looking 0.55 that would reject it.
    """
    ta, tb = set(a.split()), set(b.split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)
