"""Polite, cached HTTP client for SEC EDGAR.

Three properties matter and each is a place where naive scrapers break:

1. **Identification.** EDGAR returns 403 to any request without a descriptive
   ``User-Agent`` carrying a contact address. This is a hard requirement.
2. **Rate limiting.** SEC's published ceiling is 10 requests/second per IP,
   enforced by a temporary block on the whole IP. We use a token bucket
   defaulted below the ceiling.
3. **Immutability caching.** Accepted EDGAR documents never change: once a
   filing is on the wire it is a permanent artefact. Everything is therefore
   cached to disk keyed on the URL path, which makes reruns free and makes the
   whole pipeline reproducible offline after one crawl.
"""

from __future__ import annotations

import gzip
import hashlib
import logging
import threading
import time
from pathlib import Path

import requests

from ..config import EdgarCfg

log = logging.getLogger(__name__)

EDGAR_BASE = "https://www.sec.gov"
EDGAR_DATA = "https://data.sec.gov"


class OfflineFetchError(RuntimeError):
    """Raised when a URL is not in the cache and the network is disabled."""


class TokenBucket:
    """Thread-safe token bucket. Blocks the caller until a token is available."""

    def __init__(self, rate_per_s: float, burst: int | None = None) -> None:
        self.rate = float(rate_per_s)
        self.capacity = float(burst if burst is not None else max(1.0, rate_per_s))
        self._tokens = self.capacity
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def take(self, n: float = 1.0) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                self._tokens = min(self.capacity, self._tokens + (now - self._last) * self.rate)
                self._last = now
                if self._tokens >= n:
                    self._tokens -= n
                    return
                deficit = (n - self._tokens) / self.rate
            time.sleep(deficit)


class EdgarClient:
    """Fetches EDGAR bytes with retry, throttling and a content-addressed cache."""

    def __init__(self, cfg: EdgarCfg, cache_dir: Path, offline: bool = False) -> None:
        self.cfg = cfg
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.offline = offline
        self._bucket = TokenBucket(cfg.max_rps)
        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": cfg.user_agent,
                "Accept-Encoding": "gzip, deflate",
                "Host": "www.sec.gov",
            }
        )
        self.stats = {"hit": 0, "miss": 0, "retry": 0}

    # ------------------------------------------------------------------ #
    def _cache_path(self, url: str) -> Path:
        digest = hashlib.sha256(url.encode()).hexdigest()
        # Two-level fan-out: EDGAR crawls produce >100k files and flat
        # directories degrade badly on most filesystems.
        return self.cache_dir / digest[:2] / digest[2:4] / f"{digest}.gz"

    def cache_put(self, url: str, payload: bytes) -> Path:
        """Insert bytes into the cache directly (used to seed offline fixtures)."""
        path = self._cache_path(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(gzip.compress(payload))
        tmp.replace(path)
        return path

    def is_cached(self, url: str) -> bool:
        return self._cache_path(url).exists()

    # ------------------------------------------------------------------ #
    def get(self, url: str, *, force: bool = False) -> bytes:
        path = self._cache_path(url)
        if path.exists() and not force:
            self.stats["hit"] += 1
            return gzip.decompress(path.read_bytes())

        if self.offline:
            raise OfflineFetchError(
                f"offline mode and {url} is not cached. "
                "Run `crowdflow ingest` with network access first, "
                "or use `crowdflow simulate` to generate fixtures."
            )

        headers = {"Host": "data.sec.gov"} if url.startswith(EDGAR_DATA) else {"Host": "www.sec.gov"}
        last_exc: Exception | None = None
        for attempt in range(self.cfg.max_retries):
            self._bucket.take()
            try:
                resp = self._session.get(url, headers=headers, timeout=self.cfg.timeout_s)
                if resp.status_code == 200:
                    self.stats["miss"] += 1
                    self.cache_put(url, resp.content)
                    return resp.content
                if resp.status_code == 404:
                    raise FileNotFoundError(url)
                # 403 => throttled or bad UA; 5xx => transient.
                last_exc = RuntimeError(f"HTTP {resp.status_code} for {url}")
            except (requests.RequestException, RuntimeError) as exc:
                last_exc = exc
            self.stats["retry"] += 1
            sleep = self.cfg.backoff_base_s ** (attempt + 1)
            log.warning("retry %d/%d in %.1fs: %s", attempt + 1, self.cfg.max_retries, sleep, last_exc)
            time.sleep(sleep)
        raise RuntimeError(f"exhausted retries for {url}") from last_exc

    def get_text(self, url: str, *, force: bool = False) -> str:
        return self.get(url, force=force).decode("utf-8", errors="replace")
