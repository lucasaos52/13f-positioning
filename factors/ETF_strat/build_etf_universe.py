"""Download official reference data and construct CUSIP-level ETF flags."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

from etf_strategies.universe_builder import (  # noqa: E402
    DEFAULT_USER_AGENT,
    build_etf_flags,
    download_reference_sources,
    flatten_openfigi_cache,
    extract_filing_figi_cusip_aliases,
    load_openfigi_cache,
    map_openfigi,
    parse_nasdaq_directory,
    parse_ncen_archives,
    parse_series_class_files,
)


def log(message: str) -> None:
    print(f"{time.strftime('%H:%M:%S')} - {message}", flush=True)


def main(
    *,
    through: str,
    download: bool,
    map_figi: bool,
    refresh: bool,
    max_candidates: int | None,
    skip_series_class: bool,
) -> None:
    legacy = ROOT / "factors" / "etf-positioninig-strats-codex"
    candidate_path = legacy / "data" / "fund_candidate_audit.csv"
    seed_path = legacy / "reference" / "etf_master_seed.csv"
    raw_dir = HERE / "data" / "reference_raw"
    reference_dir = HERE / "data" / "reference"
    reference_dir.mkdir(parents=True, exist_ok=True)
    cache_path = reference_dir / "openfigi_cusip_responses.jsonl"
    alias_path = reference_dir / "filing_figi_cusip_aliases.csv.gz"

    user_agent = os.getenv("SEC_USER_AGENT", DEFAULT_USER_AGENT)
    if download:
        download_reference_sources(
            raw_dir,
            through=through,
            user_agent=user_agent,
            refresh=refresh,
            include_series_class=not skip_series_class,
            log=log,
        )

    exchange = parse_nasdaq_directory(raw_dir)
    exchange.to_csv(reference_dir / "nasdaq_symbol_directory.csv", index=False)
    log(f"Nasdaq directory: {exchange['is_exchange_etf'].sum():,} live ETF tickers")

    period_match = through.lower().replace("q", "")
    through_value = int(period_match[:4]) * 4 + int(period_match[4:])
    ncen_paths = []
    for path in raw_dir.glob("*_ncen.zip"):
        found = path.stem.lower().replace("_ncen", "").replace("q", "")
        if len(found) == 5 and int(found[:4]) * 4 + int(found[4:]) <= through_value:
            ncen_paths.append(path)
    ncen = parse_ncen_archives(sorted(ncen_paths))
    ncen.to_csv(reference_dir / "ncen_etf_class_history.csv.gz", index=False)
    log(f"N-CEN: {ncen['ticker'].nunique():,} regulatory ETF tickers")

    series_paths = sorted(raw_dir.glob("series_class_*.csv"))
    series = parse_series_class_files(series_paths)
    series.to_csv(reference_dir / "sec_series_class_history.csv.gz", index=False)
    log(f"SEC series/class: {series['ticker'].nunique():,} tickers (ETF and non-ETF)")

    candidates = pd.read_csv(candidate_path, dtype={"instrument_id": str})
    candidates = candidates.sort_values("disclosed_value_usd", ascending=False)
    if max_candidates is not None:
        candidates = candidates.head(max_candidates).copy()
    common_map = pd.read_csv(
        ROOT / "notebooks" / "data" / "cm_map_wide.csv", dtype=str
    ).dropna(subset=["instrument_id", "ticker"]).drop_duplicates("instrument_id")
    known_common_ids = set(common_map["instrument_id"])
    ids = candidates.loc[
        ~candidates["instrument_id"].isin(known_common_ids), "instrument_id"
    ].dropna().astype(str).tolist()
    if refresh or not alias_path.exists():
        aliases = extract_filing_figi_cusip_aliases(
            ROOT / "crowdflow" / "data" / "20_curated" / "holdings.csv.gz", log=log
        )
        aliases.to_csv(alias_path, index=False)
    else:
        aliases = pd.read_csv(alias_path, dtype=str)
    exact_aliases = aliases[aliases["alias_status"].eq("exact_filing_pair")]
    figi_to_cusip = exact_aliases.drop_duplicates("instrument_id").set_index(
        "instrument_id"
    )["cusip"].to_dict()
    if map_figi:
        cache = map_openfigi(
            ids, cache_path, figi_cusip_aliases=figi_to_cusip, log=log
        )
    else:
        cache = load_openfigi_cache(cache_path)
    openfigi = flatten_openfigi_cache(cache)
    local_common = candidates[["instrument_id", "issuer"]].merge(
        common_map, on="instrument_id", how="inner", validate="one_to_one"
    )
    if not local_common.empty:
        local_rows = pd.DataFrame({
            "instrument_id": local_common["instrument_id"],
            "mapping_rank": 0,
            "mapping_error": "",
            "queried_at": pd.NA,
            "mapping_provenance": "LOCAL_COMMON_MAP",
            "figi": pd.NA,
            "securityType": "Common Stock",
            "securityType2": "Common Stock",
            "marketSector": "Equity",
            "ticker": local_common["ticker"],
            "name": local_common["issuer"],
            "exchCode": "LOCAL",
            "compositeFIGI": pd.NA,
            "shareClassFIGI": pd.NA,
            "securityDescription": local_common["ticker"],
            "ticker_norm": local_common["ticker"].str.upper(),
        })
        openfigi = pd.concat([openfigi, local_rows], ignore_index=True)
    openfigi.to_csv(reference_dir / "openfigi_cusip_map.csv.gz", index=False)

    seed = pd.read_csv(seed_path, dtype={"instrument_id": str})
    flags = build_etf_flags(
        candidates, openfigi, exchange, ncen, seed, series_class=series
    )
    flags_path = HERE / "data" / "etf_universe_flags.csv"
    flags.to_csv(flags_path, index=False)
    confirmed = flags[flags["is_etf"]].copy()
    confirmed.to_csv(HERE / "data" / "etf_universe_confirmed.csv", index=False)
    product_rows = confirmed.sort_values(
        ["ticker", "disclosed_value_usd"], ascending=[True, False]
    ).drop_duplicates("ticker")
    alias_counts = confirmed.groupby("ticker")["instrument_id"].nunique()
    product_rows["instrument_alias_count"] = product_rows["ticker"].map(alias_counts)
    product_rows.to_csv(HERE / "data" / "etf_universe_products.csv", index=False)
    conflicts = flags[flags["classification_conflict"]].copy()
    conflicts.to_csv(HERE / "data" / "etf_universe_conflicts.csv", index=False)
    flag_history = flags[[
        "instrument_id", "ticker", "confidence", "verification_source",
        "first_period", "last_period", "ncen_etf_validated",
        "ncen_name_compatible", "ncen_temporal_match",
    ]].merge(
        ncen[[
            "ticker", "is_ncen_etf", "is_index_fund", "is_multi_inverse_index",
            "filing_date", "report_end", "ACCESSION_NUMBER", "SERIES_ID", "CLASS_ID",
        ]],
        on="ticker", how="left", validate="many_to_many",
    )
    flag_history.to_csv(
        HERE / "data" / "etf_universe_flag_history.csv.gz", index=False
    )

    summary = {
        "through": through,
        "candidate_identifiers": int(len(flags)),
        "mapped_identifiers": int(flags["ticker"].ne("").sum()),
        "confirmed_etf_identifiers": int(flags["is_etf"].sum()),
        "confirmed_etfs": int(flags.loc[flags["is_etf"], "ticker"].replace("", pd.NA).nunique()),
        "confirmed_equity_etf_identifiers": int(flags["is_equity_etf"].sum()),
        "confirmed_equity_etfs": int(flags.loc[
            flags["is_equity_etf"], "ticker"
        ].replace("", pd.NA).nunique()),
        "confirmed_passive_etf_identifiers": int(flags["is_passive_etf"].sum()),
        "confirmed_passive_etfs": int(flags.loc[
            flags["is_passive_etf"], "ticker"
        ].replace("", pd.NA).nunique()),
        "confirmed_passive_equity_etf_identifiers": int(
            flags["is_passive_equity_etf"].sum()
        ),
        "confirmed_passive_equity_etfs": int(flags.loc[
            flags["is_passive_equity_etf"], "ticker"
        ].replace("", pd.NA).nunique()),
        "source_conflicts": int(flags["classification_conflict"].sum()),
        "blocked_source_conflicts": int(
            (flags["classification_conflict"] & ~flags["is_etf"]).sum()
        ),
        "confirmed_with_source_conflict": int(
            (flags["classification_conflict"] & flags["is_etf"]).sum()
        ),
        "known_common_stock_identifiers": int(flags["known_common_stock"].sum()),
        "blocked_common_stock_ticker_collisions": int((
            flags["known_common_stock"] & flags["ticker_identity_conflict"]
            & ~flags["is_etf"]
        ).sum()),
        "blocked_open_end_fund_classes": int((
            flags["openfigi_security_type"].eq("Open-End Fund")
            & flags["ticker_identity_conflict"] & ~flags["is_etf"]
        ).sum()),
        "blocked_closed_end_fund_classes": int((
            flags["openfigi_security_type"].eq("Closed-End Fund")
            & flags["ticker_identity_conflict"] & ~flags["is_etf"]
        ).sum()),
        "blocked_depositary_receipt_ticker_collisions": int((
            flags["openfigi_security_type"].eq("ADR")
            & flags["ticker_identity_conflict"] & ~flags["is_etf"]
        ).sum()),
        "historical_series_bridge_identifiers": int(
            flags["historical_series_etf"].sum()
        ),
        "openfigi_api_key_used": bool(os.getenv("OPENFIGI_API_KEY")),
        "sources": {
            "nasdaq": "nasdaqlisted.txt + otherlisted.txt",
            "sec_ncen_archives": len(ncen_paths),
            "sec_series_class_files": len(series_paths),
            "openfigi_cache": str(cache_path),
            "native_13f_figi_cusip_aliases": int(len(figi_to_cusip)),
        },
    }
    (HERE / "data" / "etf_universe_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    log(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--through", default="2026q1")
    parser.add_argument("--no-download", dest="download", action="store_false")
    parser.add_argument("--no-openfigi", dest="map_figi", action="store_false")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--max-candidates", type=int)
    parser.add_argument("--skip-series-class", action="store_true")
    parser.set_defaults(download=True, map_figi=True)
    main(**vars(parser.parse_args()))
