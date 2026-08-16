"""The large ETF market-data download must be resumable and schema-stable."""

from __future__ import annotations

from pathlib import Path
import shutil

import pandas as pd

from fetch_etf_prices import (
    _cache_name,
    _direct_yahoo_frame,
    _ticker_frame,
    assemble_panels,
    cache_downloads,
)
from etf_strategies.market import _read_panel


def _fake_download(tickers, *, start, end, threads):
    dates = pd.date_range("2024-01-02", periods=3, freq="B")
    present = [ticker for ticker in tickers if ticker != "MISS"]
    columns = pd.MultiIndex.from_product(
        [["Adj Close", "Close", "Volume", "Stock Splits"], present],
        names=["Price", "Ticker"],
    )
    values = []
    for _ in dates:
        row = []
        for field in ["Adj Close", "Close", "Volume", "Stock Splits"]:
            for number, _ticker in enumerate(present, start=1):
                row.append(0.0 if field == "Stock Splits" else float(number))
        values.append(row)
    return pd.DataFrame(values, index=dates, columns=columns)


def test_ticker_frame_extracts_yfinance_multiindex():
    raw = _fake_download(["AAA", "BBB"], start="2024-01-01", end="2024-02-01", threads=False)
    out = _ticker_frame(raw, "BBB")
    assert list(out.columns) == [
        "Adj Close", "Close", "Volume", "Stock Splits", "adj_close_fallback"
    ]
    assert len(out) == 3
    assert out["Close"].eq(2.0).all()


def test_direct_yahoo_parser_rejects_stub_and_parses_prices():
    stub = {"chart": {"result": [{"meta": {"symbol": "AAA"}}], "error": None}}
    assert _direct_yahoo_frame(stub, "AAA").empty

    payload = {
        "chart": {
            "error": None,
            "result": [{
                "meta": {"symbol": "AAA"},
                "timestamp": [1704153600, 1704240000],
                "indicators": {
                    "quote": [{"close": [10.0, 11.0], "volume": [100, 200]}],
                    "adjclose": [{"adjclose": [9.5, 10.5]}],
                },
            }],
        }
    }
    out = _direct_yahoo_frame(payload, "AAA")
    assert len(out) == 2
    assert (out.index.hour == 0).all()
    assert out["Adj Close"].tolist() == [9.5, 10.5]
    assert out["download_source"].eq("yahoo_chart_direct").all()


def test_cache_is_resumable_and_panel_projection_is_exact():
    # pytest's Windows tmp_path ACL is not readable in this workspace.  A
    # narrow, test-owned directory exercises the same filesystem behavior.
    runtime = Path(__file__).parent / "_runtime_price_cache"
    if runtime.exists():
        shutil.rmtree(runtime)
    runtime.mkdir()
    try:
        cache = runtime / "cache"
        available, missing = cache_downloads(
            ["AAA", "BBB", "MISS"], cache,
            start="2024-01-01", end="2024-02-01", batch_size=3,
            retry_rounds=1, pause_seconds=0.0, refresh=False, threads=False,
            downloader=_fake_download,
        )
        assert available == ["AAA", "BBB"]
        assert missing == ["MISS"]
        assert (cache / _cache_name("AAA")).exists()

        second_available, second_missing = cache_downloads(
            ["AAA", "BBB", "MISS"], cache,
            start="2024-01-01", end="2024-02-01", batch_size=3,
            retry_rounds=0, pause_seconds=0.0, refresh=False, threads=False,
            downloader=_fake_download,
        )
        assert second_available == available
        assert second_missing == missing

        manifest = assemble_panels(available, cache, runtime)
        assert set(manifest["ticker"]) == {"AAA", "BBB"}
        projected = _read_panel(runtime / "etf_prices_adjusted.csv.gz", ["BBB"])
        assert list(projected.columns) == ["BBB"]
        assert len(projected) == 3
    finally:
        if runtime.exists():
            shutil.rmtree(runtime)
