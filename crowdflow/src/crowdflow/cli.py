"""Command line interface.

Each stage is a separate subcommand so that a reviewer can run them one at a
time and inspect the layer between. ``crowdflow demo`` runs the whole thing
against generated fixtures and needs no network and no vendor data.
"""

from __future__ import annotations

import argparse
import dataclasses
import logging
import sys
from pathlib import Path

import pandas as pd

from .config import Config
from .ingest.client import EdgarClient
from .market.reference import CsvPanelLoader
from .pipeline import (
    run_all,
    stage_curate,
    stage_curate_dera,
    stage_ingest,
)

log = logging.getLogger("crowdflow")

DEFAULT_SIGNALS = ["caf_zn", "caf_x_fragility_zn", "consensus_zn", "own_share_zn", "fragility_zn"]


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )


def _client(cfg: Config) -> EdgarClient:
    if "example.com" in cfg.edgar.user_agent:
        log.warning(
            "EDGAR user agent is still the placeholder. SEC returns 403 without a real "
            "contact address. Set CROWDFLOW_USER_AGENT='Your Name your@email' before ingesting."
        )
    return EdgarClient(cfg.edgar, cfg.paths.raw, offline=cfg.offline)


def _load_panel(cfg: Config, path: str | None) -> pd.DataFrame:
    if path:
        return CsvPanelLoader(path).load("1900-01-01", "2100-01-01")
    cached = cfg.paths.curated / "price_panel.csv.gz"
    if cached.exists():
        return pd.read_csv(cached, parse_dates=["date"])
    raise SystemExit(
        "no price panel. Pass --prices PATH with columns "
        "instrument_id,date,price,volume,shares_outstanding,cum_split_factor,ret "
        "or run `crowdflow demo` to generate one."
    )


# --------------------------------------------------------------------------- #
def cmd_ingest(args, cfg: Config) -> None:
    manifest = stage_ingest(cfg, _client(cfg), max_filers=args.max_filers)
    by_form = manifest["form"].value_counts().to_dict()
    print(f"\n{len(manifest):,} filings from {manifest['cik'].nunique():,} filers")
    print(f"forms: {by_form}")
    print(f"periods: {manifest['period'].min()} to {manifest['period'].max()}")
    print(f"\nmanifest written to {cfg.paths.parsed / 'manifest.csv.gz'}")


def cmd_curate(args, cfg: Config) -> None:
    client = _client(cfg)
    manifest = pd.read_csv(cfg.paths.parsed / "manifest.csv.gz")
    store, ledger = stage_curate(cfg, client, manifest, args.crosswalk, args.families)
    print(ledger["status"].value_counts().to_string())
    print("\nrejections:", ledger.attrs.get("rejections"))


def cmd_run(args, cfg: Config) -> None:
    client = _client(cfg)
    panel = _load_panel(cfg, args.prices)
    store = ledger = None
    if args.source == "dera":
        store, ledger = _load_curated_store(cfg)
        log.info(
            "using curated store from disk: %d holdings rows, %d filings",
            len(store.holdings), len(store.revisions),
        )
    out = run_all(
        cfg, client, panel, args.crosswalk, args.families,
        args.signals or DEFAULT_SIGNALS, store=store, ledger=ledger,
    )
    print("\n" + out["table"].to_string(index=False))
    print(f"\nconfig fingerprint: {out['config_fingerprint']}")
    print(f"artefacts under: {cfg.paths.root}")


def cmd_demo(args, cfg: Config) -> None:
    """Generate fixtures and run the full pipeline offline.

    The numbers this produces describe the simulator, not markets. It exists to
    prove the pipeline runs end to end and to exercise the parsing and
    point-in-time layers against data whose ground truth is known.
    """
    from .market.simulate import SimSpec, generate_world

    cfg = dataclasses.replace(cfg, offline=True)
    client = EdgarClient(cfg.edgar, cfg.paths.raw, offline=False)
    spec = SimSpec(
        n_stocks=args.n_stocks,
        n_managers=args.n_managers,
        start=args.start,
        end=args.end,
    )
    log.info("generating fixtures (%d stocks, %d managers)", spec.n_stocks, spec.n_managers)
    world = generate_world(client, spec)
    world["panel"].to_csv(cfg.paths.curated / "price_panel.csv.gz", index=False)

    cfg = dataclasses.replace(
        cfg,
        edgar=dataclasses.replace(
            cfg.edgar,
            first_quarter=f"{pd.Timestamp(spec.start).year}Q1",
            last_quarter=f"{pd.Timestamp(spec.end).year}Q4",
        ),
        offline=True,
    )
    client.offline = True
    out = run_all(cfg, client, world["panel"], world["crosswalk"], None, args.signals or DEFAULT_SIGNALS)
    print("\n" + "=" * 78)
    print("SIMULATED DATA - these numbers describe the generator, not markets")
    print("=" * 78)
    print(out["table"].to_string(index=False))
    print(f"\nartefacts under: {cfg.paths.root}")


def cmd_datasets(args, cfg: Config) -> None:
    """Bulk-ingest via the SEC's structured 13F datasets, then curate.

    This is the cheap path to a complete 2013Q2+ store: ~50 zip downloads
    plus one submissions request per filer for acceptance timestamps,
    against the several hundred thousand per-filing requests of the raw
    crawl. Windows are curated one at a time (bounded memory) and end in the
    same 20_curated artefacts `crowdflow run` consumes via `--source dera`.
    """
    client = _client(cfg)
    store, ledger = stage_curate_dera(
        cfg, client,
        crosswalk=args.crosswalk, families=args.families,
        with_acceptance=not args.no_acceptance,
        cross_validate_n=args.cross_validate,
        strict=args.strict,
    )
    print("\n" + ledger["status"].value_counts().to_string())
    print(f"\n{len(ledger):,} filings, {len(store.holdings):,} curated positions, "
          f"{ledger['cik'].nunique():,} filers")
    xv_path = cfg.paths.parsed / "cross_validation.csv"
    if args.cross_validate and xv_path.exists():
        xv = pd.read_csv(xv_path)
        print("\ncross-validation:\n" + xv["status"].value_counts().to_string())
        bad = xv[xv["status"] == "MISMATCH"]
        if not bad.empty:
            print(bad[["accession", "rows_raw", "rows_dera", "value_rel_diff"]].to_string(index=False))
    print(f"\ncurated store written under {cfg.paths.curated}")
    print("next: crowdflow run --source dera --prices PANEL.csv --crosswalk XWALK.csv")


def _load_curated_store(cfg: Config):
    from .curate.bitemporal import HoldingsStore

    hpath = cfg.paths.curated / "holdings.csv.gz"
    rpath = cfg.paths.curated / "revisions.csv.gz"
    if not (hpath.exists() and rpath.exists()):
        raise SystemExit(
            "no curated store on disk. Run `crowdflow datasets` (bulk, 2013Q2+) or "
            "`crowdflow ingest` + `crowdflow curate` (raw path) first."
        )
    holdings = pd.read_csv(hpath)
    revisions = pd.read_csv(rpath)
    lpath = cfg.paths.curated / "ledger.csv.gz"
    ledger = pd.read_csv(lpath) if lpath.exists() else pd.DataFrame()
    return HoldingsStore.build(holdings, revisions), ledger


def cmd_report(args, cfg: Config) -> None:
    from .report.memo import build_memo

    path = build_memo(cfg, Path(args.out), simulated=not args.real_data)
    print(f"wrote {path}")


# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser("crowdflow", description="13F dynamic-crowding positioning factor")
    p.add_argument("-c", "--config", default=None)
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    # Also accepted after the subcommand (`crowdflow ingest -v`), which is how
    # every README example writes it. SUPPRESS, not False: a subparser default
    # overwrites the value the top-level parser already set, so a plain
    # store_true here would silently disable `crowdflow -v ingest`.
    common.add_argument(
        "-v", "--verbose", action="store_true", default=argparse.SUPPRESS,
        help="verbose logging (same as the global -v)",
    )
    common.add_argument("--crosswalk", default=None, help="CUSIP -> instrument crosswalk CSV")
    common.add_argument("--families", default=None, help="YAML of manual filer-family merges")
    common.add_argument("--signals", nargs="*", default=None)
    common.add_argument("--first-quarter", default=None, help="override, e.g. 2022Q1")
    common.add_argument("--last-quarter", default=None, help="override, e.g. 2023Q4")
    common.add_argument(
        "--max-filers",
        type=int,
        default=None,
        help="cap the number of CIKs crawled. A full history is tens of thousands of "
             "filings; use this for a cheap first pass that proves the credentials, "
             "the cache and the parser before committing to hours of crawling.",
    )

    sub.add_parser("ingest", parents=[common]).set_defaults(fn=cmd_ingest)
    sub.add_parser("curate", parents=[common]).set_defaults(fn=cmd_curate)

    r = sub.add_parser("run", parents=[common])
    r.add_argument("--prices", default=None)
    r.add_argument(
        "--source", choices=["raw", "dera"], default="raw",
        help="raw: crawl EDGAR per filing (whole archive, slow). "
             "dera: use the curated store a `crowdflow datasets` run left on disk "
             "(2013Q2+, ~50 downloads).",
    )
    r.set_defaults(fn=cmd_run)

    d = sub.add_parser("demo", parents=[common])
    d.add_argument("--n-stocks", type=int, default=400)
    d.add_argument("--n-managers", type=int, default=140)
    d.add_argument("--start", default="2015-01-01")
    d.add_argument("--end", default="2024-12-31")
    d.set_defaults(fn=cmd_demo)

    ds = sub.add_parser("datasets", parents=[common])
    ds.add_argument("--cross-validate", type=int, default=25,
                    help="re-parse N raw filings and compare against the datasets; 0 to skip")
    ds.add_argument("--strict", action="store_true", help="abort on the first failed window")
    ds.add_argument("--no-acceptance", action="store_true",
                    help="skip the per-CIK acceptance-timestamp crawl; knowledge dates fall "
                         "back to end of filing day (one day conservative, never lookahead)")
    ds.set_defaults(fn=cmd_datasets)

    rep = sub.add_parser("report")
    rep.add_argument(
        "-v", "--verbose", action="store_true", default=argparse.SUPPRESS,
        help="verbose logging (same as the global -v)",
    )
    rep.add_argument("--out", default="memo/crowdflow_memo.pdf")
    rep.add_argument(
        "--real-data",
        action="store_true",
        help="drop the simulated-data warnings; only pass this after a real EDGAR run",
    )
    rep.set_defaults(fn=cmd_report)

    args = p.parse_args(argv)
    _setup_logging(args.verbose)
    cfg = Config.load(args.config)
    if getattr(args, "first_quarter", None) or getattr(args, "last_quarter", None):
        cfg = dataclasses.replace(
            cfg,
            edgar=dataclasses.replace(
                cfg.edgar,
                first_quarter=args.first_quarter or cfg.edgar.first_quarter,
                last_quarter=args.last_quarter or cfg.edgar.last_quarter,
            ),
        )
    args.fn(args, cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
