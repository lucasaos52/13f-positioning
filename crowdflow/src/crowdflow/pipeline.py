"""End-to-end orchestration.

Every stage writes its output to a numbered layer under ``data/`` and every
stage can be run independently from the layer below it. The point of the
numbering is that a reviewer can stop after any stage and inspect exactly what
went in and what came out, rather than having to trust a single opaque
``run_everything()``.

    00_raw       cached EDGAR bytes (immutable, content-addressed)
    10_parsed    filing manifest and per-filing quality ledger
    20_curated   bitemporal holdings store, revision log, market panel
    30_features  manager footprints, universe, stock factors
    40_results   backtest panels, statistics, diagnostics

The one invariant enforced across stages: the signal for a report period is
always materialised from the bitemporal store at that period's *activation
date*, never at "now". Every call into ``store.as_of`` in this module passes an
activation date that came from the calendar, and there is a test that asserts
no other vantage is used.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from .config import Config
from .curate.assemble import assemble
from .curate.bitemporal import HoldingsStore
from .curate.filers import detect_cik_succession, load_family_overrides
from .curate.identifiers import SecurityMaster
from .evaluate.attribution import attribution_table, build_benchmarks, load_external_benchmarks
from .evaluate.calendar import assign_signal_periods, build_activation_schedule, rebalance_dates
from .evaluate.engine import horizon_ic, run_backtest
from .evaluate.metrics import factor_table, yearly_breakdown
from .ingest.client import EdgarClient
from .ingest.discovery import build_manifest, crawl_form_index, quarter_range
from .market.reference import monthly_returns, quarterly_reference
from .signal.factors import build_quarter_factors, manager_flow_rates, standardise
from .signal.footprint import compute_footprint, stack_footprints
from .signal.selection import score_managers, select_universe, universe_stability

log = logging.getLogger(__name__)


def _save(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, compression="gzip" if path.suffix == ".gz" else None)


# --------------------------------------------------------------------------- #
def stage_ingest(
    cfg: Config, client: EdgarClient, max_filers: int | None = None
) -> pd.DataFrame:
    """Discover filings. Padded on both ends because index quarter != period.

    ``max_filers`` truncates the CIK list. It is a smoke-test lever, not a
    research one. Filers are ranked by the number of distinct index quarters
    in which they filed a 13F-HR - i.e. sustained ordinary reporting - which
    is a longevity bias and is stamped as such. Ranking by raw index row
    count, the obvious choice, selects pathologies instead: measured on a
    real nine-quarter crawl, the top of that ranking was serial amenders
    (85 of one filer's 94 rows were 13F-HR/A) and late registrants
    backfilling a decade of old periods in one quarter, while household-name
    managers with one filing per quarter sat hundreds of places down. A
    smoke-test sample of pathologies fails the RUNBOOK's own health checks
    and sends whoever runs it debugging the wrong layer.
    """
    quarters = quarter_range(cfg.edgar.first_quarter, cfg.edgar.last_quarter, pad_back=1, pad_fwd=6)
    ciks = None
    if max_filers:
        idx = crawl_form_index(client, quarters)
        hr = idx[idx["form"] == "13F-HR"]
        regular = hr.groupby("cik")["index_quarter"].nunique().sort_values(ascending=False)
        ciks = regular.head(max_filers).index.tolist()
        log.warning(
            "--max-filers=%d: crawling the %d filers with the most sustained 13F-HR "
            "history only. This is a smoke test. Do not report numbers from it.",
            max_filers, len(ciks),
        )
    manifest = build_manifest(client, quarters, ciks=ciks)
    _save(manifest, cfg.paths.parsed / "manifest.csv.gz")
    log.info("manifest: %d filings, %d filers", len(manifest), manifest["cik"].nunique())
    return manifest


def _save_curated_layer(
    cfg: Config,
    store: HoldingsStore,
    ledger: pd.DataFrame,
    filings_frame: pd.DataFrame,
    families: Path | None,
) -> None:
    """Write the 20_curated artefacts - shared by both ingestion paths.

    ``filings_frame`` is whatever carries one row per filing with cik,
    company, period and form: the crawl manifest on the raw path, the DERA
    covers on the bulk path. Succession detection runs on it either way, so
    the review queue exists no matter which source produced the store.
    """
    _save(store.holdings, cfg.paths.curated / "holdings.csv.gz")
    _save(store.revisions, cfg.paths.curated / "revisions.csv.gz")
    _save(ledger.drop(columns=["other_managers"], errors="ignore"), cfg.paths.curated / "ledger.csv.gz")
    _save(store.filing_lag_profile(), cfg.paths.curated / "lag_profile.csv")
    _save(store.restatement_audit(), cfg.paths.curated / "restatement_audit.csv")
    # The rejection counter lives in ledger.attrs, which to_csv silently
    # drops; without this file a report built from disk shows zero rejections
    # and looks like a pipeline that never dropped a row.
    if ledger.attrs.get("rejections"):
        import json
        (cfg.paths.curated / "rejections.json").write_text(
            json.dumps(ledger.attrs["rejections"], indent=2)
        )

    # Succession candidates are produced on every curate run, not only when
    # someone remembers to build the data report. Detection without a reader
    # is how a decade-long track record quietly splits in two: the successor
    # CIK re-serves its eligibility probation while the family file stays
    # empty because nobody was ever shown the proposal.
    succession = detect_cik_succession(filings_frame)
    _save(succession, cfg.paths.curated / "succession_candidates.csv")
    clean = succession[succession["clean_handoff"]] if not succession.empty else succession
    if not clean.empty:
        overridden = set(load_family_overrides(families))
        pending = clean[
            ~clean["predecessor_cik"].isin(overridden) | ~clean["successor_cik"].isin(overridden)
        ]
        if not pending.empty:
            log.warning(
                "%d clean CIK handoff(s) not covered by config/families.yaml - review "
                "succession_candidates.csv. Unmerged, each splits one manager's history "
                "in two: the successor re-serves the eligibility minimum and the "
                "universe records a spurious exit and entry.",
                len(pending),
            )


def stage_curate(
    cfg: Config,
    client: EdgarClient,
    manifest: pd.DataFrame,
    crosswalk: Path | pd.DataFrame | None = None,
    families: Path | None = None,
) -> tuple[HoldingsStore, pd.DataFrame]:
    sm = SecurityMaster.from_files(crosswalk)
    store, ledger = assemble(cfg, client, manifest, sm, families)
    _save_curated_layer(cfg, store, ledger, manifest, families)
    return store, ledger


def stage_curate_dera(
    cfg: Config,
    client: EdgarClient,
    crosswalk: Path | pd.DataFrame | None = None,
    families: Path | None = None,
    with_acceptance: bool = True,
    cross_validate_n: int = 25,
    strict: bool = False,
) -> tuple[HoldingsStore, pd.DataFrame]:
    """Download every dataset window and curate into the 20_curated layer.

    Streaming by construction: each window's raw rows (~3M) are reduced to
    their aggregated positions by ``curate_rows`` and released before the
    next window downloads. A full 13-year ingest is ~140M raw rows; holding
    them all before curating - the obvious implementation - needs tens of GB
    and one allocation failure voids an overnight run. Only the aggregated
    table (about a sixth of the rows) accumulates.

    ``with_acceptance`` fetches acceptanceDateTime per CIK from the
    submissions API - the one point-in-time field DERA lacks. Roughly one
    request per filer; skipping it costs a day of conservatism on every
    knowledge date (end-of-filing-day fallback), never lookahead.
    """
    from .curate.assemble import assemble_curated, curate_rows
    from .curate.filers import load_family_overrides as _load_overrides
    from .ingest.datasets import (
        cross_validate,
        fetch_acceptance_times,
        load_window,
        to_pipeline_frames,
        windows_between,
    )

    sm = SecurityMaster.from_files(crosswalk)
    overrides = _load_overrides(families)
    windows = windows_between(cfg.edgar.first_quarter, cfg.edgar.last_quarter)
    log.info("%d dataset windows to fetch and curate", len(windows))

    from collections import Counter

    agg_parts: list[pd.DataFrame] = []
    ledger_parts: list[pd.DataFrame] = []
    stats_parts: list[pd.DataFrame] = []
    reasons: Counter = Counter()
    for w in windows:
        try:
            tables = load_window(client, w)
        except Exception as exc:
            log.error("%s FAILED: %s", w.label, exc)
            if strict:
                raise
            continue
        holdings_raw, covers = to_pipeline_frames(tables)
        del tables
        # Raw per-accession row counts and value totals, kept for the
        # cross-validation against re-parsed submissions. Computed on the
        # unfiltered table: the comparison is about *parsing*, and the raw
        # parser's counts are also pre-filter.
        stats_parts.append(
            holdings_raw.groupby("accession")
            .agg(rows_dera=("cusip", "size"), value_dera=("value_reported", "sum"))
            .reset_index()
        )
        agg, ledger, r = curate_rows(cfg, holdings_raw, covers, sm, overrides)
        del holdings_raw, covers
        reasons.update(r)
        agg_parts.append(agg)
        ledger_parts.append(ledger)
        log.info("%s curated: %d aggregated positions, %d filings", w.label, len(agg), len(ledger))

    if not agg_parts:
        raise RuntimeError("no dataset windows loaded; nothing to curate")
    agg = pd.concat(agg_parts, ignore_index=True)
    agg_parts.clear()
    ledger = pd.concat(ledger_parts, ignore_index=True)
    ledger_parts.clear()
    acc_stats = pd.concat(stats_parts, ignore_index=True)
    stats_parts.clear()
    _save(acc_stats, cfg.paths.parsed / "dera_accession_stats.csv.gz")

    acceptance = None
    if with_acceptance:
        ciks = sorted(set(ledger["cik"].astype(int)))
        log.info(
            "fetching acceptance timestamps for %d CIKs (~%.0f min at the rate limit)",
            len(ciks), len(ciks) / cfg.edgar.max_rps / 60,
        )
        acceptance = fetch_acceptance_times(client, ciks)
        log.info("acceptance timestamps for %d accessions", len(acceptance))

    store, ledger = assemble_curated(agg, ledger, reasons, acceptance)
    filings_frame = ledger.rename(columns={"period_end": "period"})[
        ["cik", "company", "period", "accession", "form"]
    ]
    _save_curated_layer(cfg, store, ledger, filings_frame, families)

    if cross_validate_n:
        xv = cross_validate(client, acc_stats, ledger, sample=cross_validate_n)
        _save(xv, cfg.paths.parsed / "cross_validation.csv")

    return store, ledger


# --------------------------------------------------------------------------- #
def stage_universe(
    cfg: Config, store: HoldingsStore, reference: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Footprints and the dynamic universe.

    Vantage discipline: footprints for quarter ``p`` are computed from the store
    as it stood a fixed number of days after ``p``, using a provisional vantage
    equal to the regulatory deadline plus the observed median late tail. The
    universe is then lagged one further quarter before use, so the compounded
    lag is generous. Using the *final* restated book to rank managers would be
    a subtle lookahead - the manager's own footprint would be measured with
    information published after the selection date.
    """
    periods = sorted(pd.to_datetime(store.revisions["period_end"].unique()))
    lag_profile = store.filing_lag_profile()
    vantage_lag = int(np.nanmax([60, lag_profile["p90"].median() if not lag_profile.empty else 60]))
    log.info("footprint vantage: period_end + %d days", vantage_lag)

    frames, flows = [], []
    prev_period: pd.Timestamp | None = None
    coverage: list[float] = []

    for p in periods:
        vantage = p + pd.Timedelta(days=vantage_lag)
        cur = store.as_of(p, vantage)
        if cur.empty:
            continue
        ref_p = reference[reference["period_end"] == p]
        if ref_p.empty:
            continue
        matched = cur["instrument_id"].isin(set(ref_p["instrument_id"]))
        coverage.append(float(cur.loc[matched, "value_usd"].sum() / max(cur["value_usd"].sum(), 1.0)))
        prev = store.as_of(prev_period, vantage) if prev_period is not None else None
        ref_prev = (
            reference[reference["period_end"] == prev_period] if prev_period is not None else None
        )
        fp = compute_footprint(cur, ref_p, prev, cfg.universe, prev_reference=ref_prev)
        if not fp.empty:
            frames.append(fp)
        if prev is not None and not prev.empty:
            flows.append(manager_flow_rates(cur, prev, ref_p, prev_reference=ref_prev))
        prev_period = p

    # Fail at the boundary, with the diagnosis, rather than four layers down.
    # An identifier mismatch between holdings and the price panel produces zero
    # footprints, and the symptom without this guard is a bare pandas
    # "No objects to concatenate" from inside the scoring code - which points at
    # the wrong file and says nothing about the cause.
    mean_cov = float(np.mean(coverage)) if coverage else 0.0
    if not frames:
        raise RuntimeError(
            "no manager footprints could be computed.\n"
            f"  quarters attempted      : {len(coverage)}\n"
            f"  mean value coverage     : {mean_cov:.1%} of holdings matched the price panel\n"
            "This is almost always an identifier mismatch: 13F holdings are keyed by "
            "CUSIP, the price panel by its own instrument id, and without a crosswalk "
            "the CUSIP is passed through unchanged and matches nothing. Supply "
            "--crosswalk with columns cusip,instrument_id (dated start/end if you have "
            "them), or check that the panel's instrument_id column uses the same "
            "identifier the crosswalk resolves to."
        )
    if mean_cov < 0.5:
        log.warning(
            "price panel covers only %.1f%% of holdings value. Footprint and factor "
            "estimates below that level are dominated by whichever names happen to "
            "match, which is not a random subset - it skews to large, liquid, "
            "still-listed issuers.", 100 * mean_cov,
        )

    footprints = stack_footprints(frames, cfg.universe)
    flow_history = pd.concat(flows, ignore_index=True) if flows else pd.DataFrame(
        columns=["filer_id", "period_end", "flow_rate"]
    )
    scored = score_managers(footprints, cfg.universe)
    universe = select_universe(scored, cfg.universe)

    _save(footprints, cfg.paths.features / "footprints.csv.gz")
    _save(scored, cfg.paths.features / "manager_scores.csv.gz")
    _save(universe, cfg.paths.features / "universe.csv")
    _save(universe_stability(universe), cfg.paths.features / "universe_stability.csv")
    _save(flow_history, cfg.paths.features / "flow_history.csv.gz")
    return footprints, universe, flow_history


# --------------------------------------------------------------------------- #
def stage_factors(
    cfg: Config,
    store: HoldingsStore,
    universe: pd.DataFrame,
    reference: pd.DataFrame,
    flow_history: pd.DataFrame,
    schedule: pd.DataFrame,
) -> pd.DataFrame:
    """Stock-level factors, each built at its period's activation date.

    This is the single most important loop in the repository for point-in-time
    correctness. ``store.as_of(period, activation_date)`` is the only way
    holdings enter the factor, and both the current and prior quarter are
    materialised at the *same* activation date - so a restatement of the prior
    quarter that arrived after activation is invisible to both, exactly as it
    was to a researcher at the time.
    """
    periods = sorted(universe["period_end"].unique())
    act = schedule.set_index("period_end")["activation_date"].to_dict()

    frames = []
    for i, p in enumerate(periods):
        if i == 0 or p not in act:
            continue
        vantage = pd.Timestamp(act[p])
        prev_p = periods[i - 1]
        cur = store.as_of(p, vantage)
        prev = store.as_of(prev_p, vantage)
        if cur.empty or prev.empty:
            continue
        ref_p = reference[reference["period_end"] == p]
        if ref_p.empty:
            continue
        ref_prev = reference[reference["period_end"] == prev_p]
        members = universe.loc[universe["period_end"] == p, "filer_id"].tolist()
        f = build_quarter_factors(
            cur, prev, members, ref_p, flow_history, cfg.factor, prev_reference=ref_prev
        )
        if not f.empty:
            frames.append(f)

    if not frames:
        raise RuntimeError("no factors built; check universe and reference coverage")
    raw = pd.concat(frames, ignore_index=True)
    std = standardise(raw, reference, cfg.factor)
    _save(std, cfg.paths.features / "factors.csv.gz")
    return std


# --------------------------------------------------------------------------- #
def stage_backtest(
    cfg: Config,
    factors: pd.DataFrame,
    schedule: pd.DataFrame,
    reference: pd.DataFrame,
    returns: pd.DataFrame,
    signal_cols: list[str],
    capital_usd: float = 5e8,
    benchmarks: pd.DataFrame | None = None,
) -> dict:
    months = rebalance_dates(
        schedule["trade_date"].min(), pd.Timestamp(returns["month"].max().end_time), cfg.backtest.rebalance
    )
    mapping = assign_signal_periods(months, schedule, cfg.backtest.signal_staleness_cap_days)
    panel = mapping.merge(factors, on="period_end", how="left")

    results, horizons = {}, []
    for col in signal_cols:
        if col not in panel.columns:
            log.warning("signal column %s missing; skipped", col)
            continue
        res = run_backtest(panel, returns, reference, cfg.backtest, col, capital_usd)
        if res["panel"].empty:
            continue
        results[col] = res
        h = horizon_ic(panel, returns, col, cfg.backtest.horizons_months)
        if not h.empty:
            horizons.append(h.assign(factor=col))
        _save(res["panel"], cfg.paths.results / f"panel_{col}.csv")

    table = factor_table(results, cfg.backtest.newey_west_lags)
    _save(table, cfg.paths.results / "factor_table.csv")

    # Benchmark attribution. A raw spread that vanishes once size, momentum,
    # reversal and illiquidity are controlled for is not a positioning factor,
    # it is one of those four wearing a 13F costume.
    if benchmarks is None:
        benchmarks = build_benchmarks(returns, reference)
    _save(benchmarks, cfg.paths.results / "benchmarks.csv")
    attribution = attribution_table(results, benchmarks, nw_lags=cfg.backtest.newey_west_lags)
    _save(attribution, cfg.paths.results / "attribution.csv")
    if horizons:
        hz = pd.concat(horizons, ignore_index=True)
        summary = (
            hz.groupby(["factor", "horizon_m"])["ic"]
            .agg(ic_mean="mean", ic_std="std", n="size")
            .reset_index()
        )
        summary["ic_t"] = summary["ic_mean"] / (summary["ic_std"] / np.sqrt(summary["n"]))
        _save(summary, cfg.paths.results / "horizon_ic.csv")
    else:
        summary = pd.DataFrame()

    yearly = {k: yearly_breakdown(v["panel"]) for k, v in results.items()}
    for k, v in yearly.items():
        _save(v, cfg.paths.results / f"yearly_{k}.csv")

    _save(mapping, cfg.paths.results / "signal_calendar.csv")
    return {
        "results": results,
        "table": table,
        "attribution": attribution,
        "benchmarks": benchmarks,
        "horizon": summary,
        "yearly": yearly,
        "mapping": mapping,
    }


# --------------------------------------------------------------------------- #
def run_all(
    cfg: Config,
    client: EdgarClient,
    price_panel: pd.DataFrame,
    crosswalk: Path | pd.DataFrame | None = None,
    families: Path | None = None,
    signal_cols: list[str] | None = None,
    benchmarks_path: str | None = None,
    store: HoldingsStore | None = None,
    ledger: pd.DataFrame | None = None,
) -> dict:
    """End to end. Pass a prebuilt ``store`` (e.g. loaded from a
    ``crowdflow datasets`` run) to skip the raw crawl entirely."""
    if store is None:
        manifest = stage_ingest(cfg, client)
        store, ledger = stage_curate(cfg, client, manifest, crosswalk, families)
    else:
        manifest = pd.DataFrame()
        ledger = ledger if ledger is not None else pd.DataFrame()

    reference = quarterly_reference(price_panel)
    returns = monthly_returns(price_panel)
    _save(reference, cfg.paths.curated / "reference.csv.gz")

    footprints, universe, flows = stage_universe(cfg, store, reference)

    months = rebalance_dates(price_panel["date"].min(), price_panel["date"].max(), cfg.backtest.rebalance)
    schedule = build_activation_schedule(store.revisions, universe, months)
    _save(schedule, cfg.paths.features / "activation_schedule.csv")

    factors = stage_factors(cfg, store, universe, reference, flows, schedule)
    cols = signal_cols or ["caf_zn", "caf_x_fragility_zn", "consensus_zn", "own_share_zn", "fragility_zn"]
    bench = load_external_benchmarks(benchmarks_path) if benchmarks_path else None
    bt = stage_backtest(cfg, factors, schedule, reference, returns, cols, benchmarks=bench)

    return {
        "manifest": manifest,
        "ledger": ledger,
        "store": store,
        "reference": reference,
        "returns": returns,
        "footprints": footprints,
        "universe": universe,
        "schedule": schedule,
        "factors": factors,
        "config_fingerprint": cfg.fingerprint(),
        **bt,
    }
