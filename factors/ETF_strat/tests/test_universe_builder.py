"""Pins ETF identity rules so text candidates cannot leak into production."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from etf_strategies.universe_builder import (
    _classify_asset,
    _classify_style,
    _openfigi_job,
    build_etf_flags,
    derive_figi_alias_records,
    derive_filing_alias_records,
    parse_nasdaq_directory,
    valid_cusip,
    valid_figi,
)


def test_asset_and_style_rules_separate_duration_from_leverage():
    assert _classify_asset("SPDR Bloomberg 1-3 Month T-Bill ETF") == "fixed_income"
    assert _classify_asset("iShares Biotechnology ETF") == "equity"
    assert _classify_asset("ARK Genomic Revolution ETF") == "equity"
    assert _classify_asset("Invesco DB Commodity Index ETF") == "commodity"
    assert _classify_style("PIMCO Enhanced Short Maturity ETF", False) != "leveraged_inverse"
    assert _classify_style("Vanguard Short-Term TIPS ETF", False) != "leveraged_inverse"
    assert _classify_style("ProShares Short QQQ", False) == "leveraged_inverse"
    assert _classify_style("ProShares UltraPro QQQ", False) == "leveraged_inverse"


def test_nasdaq_parser_reads_explicit_etf_flag():
    fixture = Path(__file__).parent / "fixtures" / "nasdaq_directory"
    out = parse_nasdaq_directory(fixture).set_index("ticker")
    assert bool(out.loc["AAA", "is_exchange_etf"])
    assert not bool(out.loc["BBB", "is_exchange_etf"])
    assert bool(out.loc["CCC", "is_exchange_etf"])


def test_regulatory_join_confirms_passive_equity_and_rejects_name_only():
    candidates = pd.DataFrame({
        "instrument_id": ["111111111", "222222222"],
        "issuer": ["Alpha Trust", "Not Really ETF Corporation"],
        "disclosed_value_usd": [100.0, 50.0],
    })
    figi = pd.DataFrame({
        "instrument_id": ["111111111", "222222222"],
        "ticker_norm": ["AAA", "BBB"],
        "ticker": ["AAA", "BBB"],
        "figi": ["F1", "F2"],
        "name": ["Alpha S&P 500 ETF", "Not Really ETF Corporation"],
        "securityType": ["ETP", "Common Stock"],
        "securityType2": ["Mutual Fund", "Common Stock"],
        "marketSector": ["Equity", "Equity"],
        "exchCode": ["US", "US"],
        "mapping_error": ["", ""],
        "queried_at": ["now", "now"],
        "mapping_rank": [0, 0],
    })
    exchange = pd.DataFrame({
        "ticker": ["AAA", "BBB"],
        "name": ["Alpha S&P 500 ETF", "Not Really ETF Corporation"],
        "is_exchange_etf": [True, False],
        "exchange": ["P", "N"],
        "exchange_source": ["otherlisted.txt", "otherlisted.txt"],
    })
    ncen = pd.DataFrame({
        "ticker": ["AAA"], "FUND_NAME": ["Alpha S&P 500 ETF"],
        "SERIES_ID": ["S1"], "CLASS_NAME": ["ETF Shares"], "CLASS_ID": ["C1"],
        "CIK": ["1"], "is_ncen_etf": [True], "is_index_fund": [True],
        "is_multi_inverse_index": [False],
        "filing_date": pd.to_datetime(["2025-03-01"]),
        "report_end": pd.to_datetime(["2024-12-31"]),
        "ACCESSION_NUMBER": ["A1"], "source_archive": ["2025q1_ncen.zip"],
    })
    out = build_etf_flags(candidates, figi, exchange, ncen).set_index("instrument_id")
    assert bool(out.loc["111111111", "is_etf"])
    assert bool(out.loc["111111111", "is_passive_equity_etf"])
    assert out.loc["111111111", "confidence"] == "regulatory_and_exchange"
    assert not bool(out.loc["222222222", "is_etf"])
    assert out.loc["222222222", "confidence"] == "known_common_stock"


def test_us_composite_wins_over_foreign_ticker_collision():
    candidates = pd.DataFrame({
        "instrument_id": ["46090E103"], "ticker": ["QQQ"],
        "issuer": ["INVESCO QQQ TRUST"], "disclosed_value_usd": [1.0],
    })
    figi = pd.DataFrame({
        "instrument_id": ["46090E103", "46090E103"],
        "ticker_norm": ["QQQ", "QQQN"], "ticker": ["QQQ", "QQQN"],
        "figi": ["US_FIGI", "FOREIGN_FIGI"],
        "name": ["INVESCO QQQ TRUST SERIES 1", "INVESCO QQQ TRUST SERIES 1"],
        "securityType": ["ETP", "ETP"], "securityType2": ["Mutual Fund", "Mutual Fund"],
        "marketSector": ["Equity", "Equity"], "exchCode": ["US", "GR"],
        "mapping_error": ["", ""], "queried_at": ["now", "now"],
        "mapping_rank": [1, 0],
    })
    exchange = pd.DataFrame({
        "ticker": ["QQQ", "QQQN"], "name": ["Invesco QQQ", "Other ETF"],
        "is_exchange_etf": [True, True], "exchange": ["Q", "Q"],
        "exchange_source": ["nasdaqlisted.txt", "nasdaqlisted.txt"],
    })
    ncen = pd.DataFrame({
        "ticker": ["QQQN"], "FUND_NAME": ["Other ETF"], "SERIES_ID": ["S1"],
        "CLASS_NAME": ["ETF"], "CLASS_ID": ["C1"], "CIK": ["1"],
        "is_ncen_etf": [True], "is_index_fund": [True],
        "is_multi_inverse_index": [False],
        "filing_date": pd.to_datetime(["2025-01-01"]),
        "report_end": pd.to_datetime(["2024-12-31"]),
        "ACCESSION_NUMBER": ["A"], "source_archive": ["x.zip"],
    })
    out = build_etf_flags(candidates, figi, exchange, ncen)
    assert out.loc[0, "ticker"] == "QQQ"
    assert out.loc[0, "figi"] == "US_FIGI"


def test_delisted_etp_can_be_confirmed_by_historical_sec_class():
    candidates = pd.DataFrame({
        "instrument_id": ["333333333"], "issuer": ["OLD ETF TRUST"],
        "first_period": ["2014-03-31"], "last_period": ["2016-12-31"],
        "disclosed_value_usd": [1.0],
    })
    figi = pd.DataFrame({
        "instrument_id": ["333333333"], "ticker_norm": ["OLDX"], "ticker": ["OLDX"],
        "figi": ["F3"], "name": ["OLD EQUITY ETF"], "securityType": ["ETP"],
        "securityType2": ["Mutual Fund"], "marketSector": ["Equity"],
        "exchCode": ["US"], "mapping_error": [""], "queried_at": ["now"],
        "mapping_rank": [0],
    })
    exchange = pd.DataFrame(columns=[
        "ticker", "name", "is_exchange_etf", "exchange", "exchange_source"
    ])
    ncen = pd.DataFrame()
    series = pd.DataFrame({
        "ticker": ["OLDX"], "series_id": ["SOLD"], "class_id": ["COLD"],
        "series_name": ["Old Equity ETF"], "class_name": ["ETF Shares"],
        "cik": ["1"], "registrant_name": ["Old Trust"], "source_year": [2015],
    })
    out = build_etf_flags(
        candidates, figi, exchange, ncen, series_class=series
    )
    assert bool(out.loc[0, "is_etf"])
    assert out.loc[0, "confidence"] == "historical_regulatory_bridge"


def test_ticker_collision_cannot_promote_common_stock_identifier():
    candidates = pd.DataFrame({
        "instrument_id": ["01609W102"], "issuer": ["ALIBABA GROUP HOLDING LTD"],
        "disclosed_value_usd": [1.0],
    })
    figi = pd.DataFrame({
        "instrument_id": ["01609W102"], "ticker_norm": ["BABA"],
        "ticker": ["BABA"], "figi": ["F_BABA"],
        "name": ["ALIBABA GROUP HOLDING LTD"], "securityType": ["Common Stock"],
        "securityType2": ["Common Stock"], "marketSector": ["Equity"],
        "exchCode": ["US"], "mapping_error": [""], "queried_at": ["now"],
        "mapping_rank": [0],
    })
    exchange = pd.DataFrame({
        "ticker": ["BABA"], "name": ["Ticker-collision ETF"],
        "is_exchange_etf": [True], "exchange": ["Q"],
        "exchange_source": ["nasdaqlisted.txt"],
    })
    ncen = pd.DataFrame({
        "ticker": ["BABA"], "FUND_NAME": ["GraniteShares BABA Daily ETF"],
        "SERIES_ID": ["S1"], "CLASS_NAME": ["ETF"], "CLASS_ID": ["C1"],
        "CIK": ["1"], "is_ncen_etf": [True], "is_index_fund": [True],
        "is_multi_inverse_index": [False],
        "filing_date": pd.to_datetime(["2025-01-01"]),
        "report_end": pd.to_datetime(["2024-12-31"]),
        "ACCESSION_NUMBER": ["A"], "source_archive": ["x.zip"],
    })
    out = build_etf_flags(candidates, figi, exchange, ncen)
    assert not bool(out.loc[0, "is_etf"])
    assert bool(out.loc[0, "ticker_identity_conflict"])
    assert bool(out.loc[0, "classification_conflict"])
    assert bool(out.loc[0, "known_common_stock"])
    assert out.loc[0, "name"] == "ALIBABA GROUP HOLDING LTD"


def test_product_metadata_is_shared_across_cusip_and_figi_aliases():
    candidates = pd.DataFrame({
        "instrument_id": ["46090E103", "BBG000BSWKH7"],
        "issuer": ["INVESCO QQQ TRUST", "INVESCO QQQ TRUST"],
        "disclosed_value_usd": [2.0, 1.0],
    })
    figi = pd.DataFrame({
        "instrument_id": ["46090E103", "BBG000BSWKH7"],
        "ticker_norm": ["QQQ", "QQQ"], "ticker": ["QQQ", "QQQ"],
        "figi": ["F1", "F2"],
        "name": ["INVESCO QQQ TRUST SERIES 1", "INVESCO QQQ TRUST SERIES 1"],
        "securityType": ["ETP", "ETP"],
        "securityType2": ["Mutual Fund", "Mutual Fund"],
        "marketSector": ["Equity", "Equity"], "exchCode": ["US", "US"],
        "mapping_error": ["", ""], "queried_at": ["now", "now"],
        "mapping_rank": [0, 0],
    })
    exchange = pd.DataFrame({
        "ticker": ["QQQ"], "name": ["Invesco QQQ Trust"],
        "is_exchange_etf": [True], "exchange": ["Q"],
        "exchange_source": ["nasdaqlisted.txt"],
    })
    seed = pd.DataFrame({
        "instrument_id": ["46090E103"], "ticker": ["QQQ"],
        "name": ["Invesco QQQ Trust"], "asset_class": ["equity"],
        "etf_style": ["broad"], "specialized_score": [0.0],
        "is_etf": [True], "verification_source": ["manual"],
    })
    out = build_etf_flags(candidates, figi, exchange, pd.DataFrame(), seed=seed)
    assert out["is_etf"].all()
    assert out["asset_class"].eq("equity").all()
    assert out["etf_style"].eq("broad").all()
    assert out["is_passive_equity_etf"].all()


def test_recycled_etf_ticker_does_not_import_old_ncen_identity():
    candidates = pd.DataFrame({
        "instrument_id": ["46438F101"], "issuer": ["ISHARES BITCOIN TRUST ETF"],
        "first_period": ["2024-03-31"], "last_period": ["2026-03-31"],
        "disclosed_value_usd": [1.0],
    })
    figi = pd.DataFrame({
        "instrument_id": ["46438F101"], "ticker_norm": ["IBIT"],
        "ticker": ["IBIT"], "figi": ["F_IBIT"],
        "name": ["ISHARES BITCOIN TRUST ETF"], "securityType": ["ETP"],
        "securityType2": ["Mutual Fund"], "marketSector": ["Equity"],
        "exchCode": ["US"], "mapping_error": [""], "queried_at": ["now"],
        "mapping_rank": [0],
    })
    exchange = pd.DataFrame({
        "ticker": ["IBIT"], "name": ["iShares Bitcoin Trust ETF"],
        "is_exchange_etf": [True], "exchange": ["Q"],
        "exchange_source": ["nasdaqlisted.txt"],
    })
    ncen = pd.DataFrame({
        "ticker": ["IBIT"],
        "FUND_NAME": ["Defiance Daily Short Digitizing the Economy ETF"],
        "SERIES_ID": ["S_OLD"], "CLASS_NAME": ["ETF"], "CLASS_ID": ["C_OLD"],
        "CIK": ["1"], "is_ncen_etf": [True], "is_index_fund": [False],
        "is_multi_inverse_index": [True],
        "filing_date": pd.to_datetime(["2023-03-16"]),
        "report_end": pd.to_datetime(["2022-12-31"]),
        "ACCESSION_NUMBER": ["A"], "source_archive": ["x.zip"],
    })
    series = pd.DataFrame({
        "ticker": ["IBIT"], "series_id": ["S_OLD"], "class_id": ["C_OLD"],
        "series_name": ["Defiance Daily Short Digitizing the Economy ETF"],
        "class_name": ["ETF Shares"], "cik": ["1"],
        "registrant_name": ["Defiance"], "source_year": [2024],
    })
    out = build_etf_flags(
        candidates, figi, exchange, ncen, series_class=series
    )
    assert bool(out.loc[0, "is_etf"])
    assert bool(out.loc[0, "exchange_etf_validated"])
    assert not bool(out.loc[0, "ncen_etf_validated"])
    assert not bool(out.loc[0, "historical_series_etf"])
    assert out.loc[0, "name"] == "iShares Bitcoin Trust ETF"
    assert out.loc[0, "asset_class"] == "crypto"
    assert out.loc[0, "etf_style"] == "other"


def test_openfigi_jobs_support_both_13f_identifier_sources():
    assert valid_cusip("78462F103")
    assert valid_figi("BBG001S72SM3")
    assert _openfigi_job("78462F103") == {
        "idType": "ID_CUSIP", "idValue": "78462F103", "exchCode": "US"
    }
    assert _openfigi_job("BBG001S72SM3") == {
        "idType": "ID_BB_GLOBAL", "idValue": "BBG001S72SM3", "exchCode": "US"
    }


def test_figi_alias_is_reused_from_exact_cusip_response():
    cache = {
        "78462F103": {
            "instrument_id": "78462F103", "queried_at": "now",
            "response": {"data": [{
                "figi": "BBG000BDTBL9", "compositeFIGI": "BBG000BDTBL9",
                "shareClassFIGI": "BBG001S72SM3", "ticker": "SPY", "exchCode": "US",
                "securityType": "ETP", "securityType2": "Mutual Fund",
            }]},
        }
    }
    aliases = derive_figi_alias_records(cache, ["BBG001S72SM3"])
    assert aliases["BBG001S72SM3"]["derived_from"] == "78462F103"
    assert aliases["BBG001S72SM3"]["response"]["data"][0]["ticker"] == "SPY"


def test_native_filing_pair_can_copy_cusip_mapping_to_figi():
    cache = {
        "78462F103": {
            "instrument_id": "78462F103", "queried_at": "now",
            "response": {"data": [{
                "figi": "BBG000BDTBL9", "shareClassFIGI": "BBG001S72SM3",
                "ticker": "SPY", "exchCode": "US", "securityType": "ETP",
                "securityType2": "Mutual Fund",
            }]},
        }
    }
    aliases = derive_filing_alias_records(
        cache, {"BBG009999999": "78462F103"}
    )
    assert aliases["BBG009999999"]["derived_from"] == "78462F103"
    assert aliases["BBG009999999"]["relation_source"] == "13F_NATIVE_FIGI_CUSIP_PAIR"
