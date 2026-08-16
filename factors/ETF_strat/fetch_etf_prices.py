"""Download and pin Yahoo ETF market data for the reconstructed 13F universe.

The original research downloader read the 51-name hand-curated seed and then
kept only its 41 equity ETFs.  This replacement reads the official universe
built by :mod:`build_etf_universe`, caches one ticker at a time, retries failed
symbols in smaller batches, and assembles deterministic wide panels.  The
per-ticker cache makes a multi-thousand-symbol download safely resumable.

Yahoo is a market-data bridge, not the ETF identity source.  Delisted symbols
and recycled tickers are therefore recorded as missing rather than silently
substituted.  ETF identity continues to come from the SEC/Nasdaq/OpenFIGI
pipeline in ``etf_universe_products.csv``.
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta
import gc
from hashlib import sha1
import json
from pathlib import Path
import re
import time
from typing import Callable, Iterable

import pandas as pd
import requests
import yfinance as yf


HERE = Path(__file__).resolve().parent
DEFAULT_START = "2012-06-01"
FIELDS = {
    "Adj Close": "etf_prices_adjusted.csv.gz",
    "Close": "etf_prices_raw.csv.gz",
    "Volume": "etf_volume.csv.gz",
    "Stock Splits": "etf_splits.csv.gz",
}


def log(message: str) -> None:
    print(f"{time.strftime('%H:%M:%S')} - {message}", flush=True)


def _cache_name(ticker: str) -> str:
    """Return a collision-resistant Windows-safe filename for a ticker."""

    safe = re.sub(r"[^A-Z0-9._-]+", "_", ticker.upper()).strip("._") or "ticker"
    digest = sha1(ticker.encode("utf-8")).hexdigest()[:10]
    return f"{safe[:40]}__{digest}.csv.gz"


def _ticker_frame(download: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """Extract one symbol from yfinance's single- or multi-ticker schema."""

    if download.empty:
        return pd.DataFrame()
    frame: pd.DataFrame
    if isinstance(download.columns, pd.MultiIndex):
        ticker_level = None
        for level in range(download.columns.nlevels):
            values = {str(value).upper() for value in download.columns.get_level_values(level)}
            if ticker.upper() in values:
                ticker_level = level
                break
        if ticker_level is None:
            return pd.DataFrame()
        matching = [
            value for value in download.columns.get_level_values(ticker_level).unique()
            if str(value).upper() == ticker.upper()
        ]
        if not matching:
            return pd.DataFrame()
        frame = download.xs(matching[0], axis=1, level=ticker_level).copy()
    else:
        frame = download.copy()
    frame.columns = [str(column) for column in frame.columns]
    if "Close" not in frame:
        return pd.DataFrame()
    if "Adj Close" not in frame:
        # yfinance occasionally omits Adj Close for instruments without any
        # corporate actions. With auto_adjust=False, Close is the conservative
        # fallback and the manifest exposes this condition.
        frame["Adj Close"] = frame["Close"]
        frame["adj_close_fallback"] = True
    else:
        frame["adj_close_fallback"] = False
    for field in FIELDS:
        if field not in frame:
            frame[field] = 0.0 if field == "Stock Splits" else pd.NA
    frame = frame[[*FIELDS, "adj_close_fallback"]]
    frame.index = pd.DatetimeIndex(frame.index).tz_localize(None)
    frame.index.name = "date"
    frame = frame[~frame.index.duplicated(keep="last")].sort_index()
    useful = frame["Adj Close"].notna() | frame["Close"].notna()
    return frame.loc[useful]


def _download_batch(
    tickers: list[str],
    *,
    start: str,
    end: str,
    threads: bool,
) -> pd.DataFrame:
    """One Yahoo request with settings pinned for reproducibility."""

    return yf.download(
        tickers,
        start=start,
        end=end,
        auto_adjust=False,
        actions=True,
        repair=False,
        progress=False,
        threads=threads,
        group_by="column",
        timeout=30,
        multi_level_index=True,
    )


def _direct_yahoo_frame(payload: dict, ticker: str) -> pd.DataFrame:
    """Parse Yahoo's chart JSON while rejecting metadata-only responses."""

    chart = payload.get("chart", {})
    results = chart.get("result") or []
    if chart.get("error") or not results:
        return pd.DataFrame()
    result = results[0]
    if str(result.get("meta", {}).get("symbol", "")).upper() != ticker.upper():
        return pd.DataFrame()
    timestamps = result.get("timestamp") or []
    indicators = result.get("indicators", {})
    quotes = indicators.get("quote") or []
    if not timestamps or not quotes:
        # Yahoo preserves a metadata stub for some liquidated/recycled symbols.
        # It must not be mistaken for a historical series.
        return pd.DataFrame()
    quote = quotes[0]
    adjusted_blocks = indicators.get("adjclose") or []
    adjusted = adjusted_blocks[0].get("adjclose", []) if adjusted_blocks else []
    # Yahoo timestamps daily bars at the market session instant in UTC while
    # yfinance's CSV cache uses a date-only midnight index.  Normalize before
    # assembly or the same session appears as two distinct rows.
    index = pd.to_datetime(timestamps, unit="s", utc=True).tz_localize(None).normalize()
    frame = pd.DataFrame(index=index)
    frame["Close"] = pd.to_numeric(pd.Series(quote.get("close", [])), errors="coerce").to_numpy()
    if len(adjusted) == len(frame):
        frame["Adj Close"] = pd.to_numeric(pd.Series(adjusted), errors="coerce").to_numpy()
        frame["adj_close_fallback"] = False
    else:
        frame["Adj Close"] = frame["Close"]
        frame["adj_close_fallback"] = True
    volume = quote.get("volume", [])
    frame["Volume"] = (
        pd.to_numeric(pd.Series(volume), errors="coerce").to_numpy()
        if len(volume) == len(frame) else pd.NA
    )
    frame["Stock Splits"] = 0.0
    for event in (result.get("events", {}).get("splits") or {}).values():
        event_date = pd.to_datetime(event.get("date"), unit="s", utc=True).tz_localize(None)
        if event_date not in frame.index:
            continue
        numerator = event.get("numerator")
        denominator = event.get("denominator")
        if numerator is not None and denominator:
            frame.loc[event_date, "Stock Splits"] = float(numerator) / float(denominator)
    frame["download_source"] = "yahoo_chart_direct"
    frame.index.name = "date"
    useful = frame["Adj Close"].notna() | frame["Close"].notna()
    return frame.loc[useful, [*FIELDS, "adj_close_fallback", "download_source"]]


def _download_direct_yahoo(ticker: str, *, start: str, end: str) -> pd.DataFrame:
    """Fallback for valid symbols lost by yfinance batch/cookie handling."""

    period1 = int(pd.Timestamp(start, tz="UTC").timestamp())
    period2 = int(pd.Timestamp(end, tz="UTC").timestamp())
    response = requests.get(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}",
        params={
            "period1": period1,
            "period2": period2,
            "interval": "1d",
            "events": "div,splits",
        },
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
    )
    response.raise_for_status()
    return _direct_yahoo_frame(response.json(), ticker)


def cache_downloads(
    tickers: Iterable[str],
    cache_dir: Path,
    *,
    start: str,
    end: str,
    batch_size: int,
    retry_rounds: int,
    pause_seconds: float,
    refresh: bool,
    threads: bool,
    downloader: Callable[..., pd.DataFrame] = _download_batch,
    direct_downloader: Callable[..., pd.DataFrame] | None = None,
) -> tuple[list[str], list[str]]:
    """Populate the ticker cache and return available and missing symbols."""

    cache_dir.mkdir(parents=True, exist_ok=True)
    requested = sorted({str(ticker).strip().upper() for ticker in tickers if str(ticker).strip()})
    if refresh:
        pending = requested
    else:
        pending = [ticker for ticker in requested if not (cache_dir / _cache_name(ticker)).exists()]
    cached_before = len(requested) - len(pending)
    log(f"Yahoo cache: {cached_before:,} ready; {len(pending):,} pending")

    for round_number in range(retry_rounds + 1):
        if not pending:
            break
        size = max(5, batch_size // (2 ** round_number))
        next_pending: list[str] = []
        for offset in range(0, len(pending), size):
            batch = pending[offset : offset + size]
            try:
                raw = downloader(
                    batch, start=start, end=end, threads=threads and len(batch) > 1
                )
            except Exception as exc:  # network/vendor failures are retried
                log(f"Yahoo batch error ({len(batch)} tickers): {type(exc).__name__}: {exc}")
                next_pending.extend(batch)
                time.sleep(max(1.0, pause_seconds))
                continue
            saved = 0
            for ticker in batch:
                frame = _ticker_frame(raw, ticker)
                if frame.empty:
                    next_pending.append(ticker)
                    continue
                frame.to_csv(cache_dir / _cache_name(ticker))
                saved += 1
            completed = min(offset + len(batch), len(pending))
            log(
                f"Yahoo round {round_number + 1}: {completed:,}/{len(pending):,}; "
                f"saved {saved}/{len(batch)}"
            )
            if pause_seconds:
                time.sleep(pause_seconds)
        pending = sorted(set(next_pending))
        if pending and round_number < retry_rounds:
            log(f"Yahoo retry: {len(pending):,} symbols, batch size {max(5, size // 2)}")
            time.sleep(max(2.0, pause_seconds * 4))

    if pending and direct_downloader is not None:
        still_missing: list[str] = []
        log(f"Yahoo direct fallback: {len(pending):,} symbols")
        for ticker in pending:
            try:
                frame = direct_downloader(ticker, start=start, end=end)
            except Exception as exc:
                log(f"Yahoo direct error ({ticker}): {type(exc).__name__}: {exc}")
                still_missing.append(ticker)
                continue
            if frame.empty:
                still_missing.append(ticker)
                continue
            frame.to_csv(cache_dir / _cache_name(ticker))
            log(f"Yahoo direct saved {ticker}: {len(frame):,} days")
        pending = still_missing

    available = [
        ticker for ticker in requested if (cache_dir / _cache_name(ticker)).exists()
    ]
    missing = sorted(set(requested) - set(available))
    return available, missing


def assemble_panels(
    tickers: Iterable[str], cache_dir: Path, out_dir: Path
) -> pd.DataFrame:
    """Assemble wide market panels and return a per-ticker coverage manifest."""

    out_dir.mkdir(parents=True, exist_ok=True)
    available = [
        ticker for ticker in sorted(set(tickers))
        if (cache_dir / _cache_name(ticker)).exists()
    ]
    manifest_rows: list[dict[str, object]] = []
    for ticker in available:
        path = cache_dir / _cache_name(ticker)
        frame = pd.read_csv(path, index_col=0, parse_dates=True)
        observed = frame["Adj Close"].notna() | frame["Close"].notna()
        dates = frame.index[observed]
        manifest_rows.append({
            "ticker": ticker,
            "status": "downloaded",
            "first_price_date": dates.min() if len(dates) else pd.NaT,
            "last_price_date": dates.max() if len(dates) else pd.NaT,
            "n_price_days": int(observed.sum()),
            "adj_close_fallback": bool(frame.get("adj_close_fallback", False).astype(bool).any())
            if len(frame) else False,
            "download_source": (
                str(frame["download_source"].dropna().iloc[-1])
                if "download_source" in frame and frame["download_source"].notna().any()
                else "yahoo_yfinance"
            ),
            "cache_file": path.name,
        })

    for field, filename in FIELDS.items():
        series: dict[str, pd.Series] = {}
        for number, ticker in enumerate(available, start=1):
            path = cache_dir / _cache_name(ticker)
            frame = pd.read_csv(
                path, usecols=["date", field], index_col="date", parse_dates=["date"]
            )
            series[ticker] = pd.to_numeric(frame[field], errors="coerce")
            if number % 500 == 0:
                log(f"Assembling {field}: {number:,}/{len(available):,}")
        panel = (
            pd.concat(series, axis=1, sort=False).sort_index()
            if series else pd.DataFrame()
        )
        panel.index.name = "date"
        panel.to_csv(out_dir / filename)
        log(f"Wrote {filename}: {panel.shape[0]:,} dates x {panel.shape[1]:,} tickers")
        del panel, series
        gc.collect()
    return pd.DataFrame(manifest_rows)


def main(
    *,
    scope: str,
    start: str,
    end: str,
    batch_size: int,
    retry_rounds: int,
    pause_seconds: float,
    refresh: bool,
    no_threads: bool,
    max_tickers: int | None,
    no_assemble: bool,
) -> None:
    # yfinance persists cookies/timezones in SQLite.  Its default user cache
    # is not writable in the project runtime, so pin that state beside the
    # downloaded data before the first network request.
    yfinance_cache = HERE / "data" / "yfinance_internal_cache"
    yfinance_cache.mkdir(parents=True, exist_ok=True)
    yf.set_tz_cache_location(str(yfinance_cache))
    products_path = HERE / "data" / "etf_universe_products.csv"
    if not products_path.exists():
        raise FileNotFoundError(
            f"{products_path} is missing; run build_etf_universe.py first"
        )
    products = pd.read_csv(products_path, dtype={"ticker": str})
    products = products[products["is_etf"].astype(bool)].copy()
    if scope == "equity":
        products = products[products["is_equity_etf"].astype(bool)].copy()
    products["ticker"] = products["ticker"].fillna("").str.strip().str.upper()
    products = products[products["ticker"].str.fullmatch(r"[A-Z0-9^=._-]+", na=False)]
    products = products.drop_duplicates("ticker")
    if max_tickers is not None:
        products = products.sort_values(
            "disclosed_value_usd", ascending=False
        ).head(max_tickers)
    tickers = products["ticker"].tolist()
    required_factors = [ticker for ticker in ["SPY", "IWM", "QQQ"] if ticker not in tickers]
    tickers.extend(required_factors)
    cache_dir = HERE / "data" / "yahoo_etf_cache"
    available, missing = cache_downloads(
        tickers,
        cache_dir,
        start=start,
        end=end,
        batch_size=batch_size,
        retry_rounds=retry_rounds,
        pause_seconds=pause_seconds,
        refresh=refresh,
        threads=not no_threads,
        direct_downloader=_download_direct_yahoo,
    )
    if not no_assemble:
        manifest = assemble_panels(available, cache_dir, HERE / "data")
        missing_rows = pd.DataFrame({"ticker": missing, "status": "missing_from_yahoo"})
        manifest = pd.concat([manifest, missing_rows], ignore_index=True)
        manifest = products[[
            "ticker", "name", "asset_class", "etf_style", "first_period", "last_period",
            "disclosed_value_usd", "confidence",
        ]].merge(manifest, on="ticker", how="left", validate="one_to_one")
        manifest["status"] = manifest["status"].fillna("not_requested")
        manifest.to_csv(HERE / "data" / "etf_price_manifest.csv", index=False)
    else:
        log("Skipped wide-panel assembly; existing manifest and panels were preserved")
    summary = {
        "scope": scope,
        "start": start,
        "end_exclusive": end,
        "requested_products": len(tickers),
        "downloaded_products": len(available),
        "missing_products": len(missing),
        "coverage": len(available) / len(tickers) if tickers else 0.0,
        "yfinance_version": yf.__version__,
        "cache_dir": str(cache_dir),
    }
    (HERE / "data" / "etf_price_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    log(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", choices=["all", "equity"], default="all")
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument(
        "--end", default=(date.today() + timedelta(days=1)).isoformat(),
        help="exclusive Yahoo end date",
    )
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--retry-rounds", type=int, default=2)
    parser.add_argument("--pause-seconds", type=float, default=0.5)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--no-threads", action="store_true")
    parser.add_argument("--max-tickers", type=int)
    parser.add_argument("--no-assemble", action="store_true")
    main(**vars(parser.parse_args()))
