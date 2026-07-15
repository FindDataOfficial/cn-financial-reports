"""Shared HTTP + caching utilities for official-website datasource clients.

The new datasource clients (``sse_client``, ``szse_client``, ``bse_client``,
``csrc_client``, ``ministry_stats_client``) share this module so they all:

  * bypass proxy environment variables by default (``trust_env=False``) -
    direct exchange/government calls break behind a corporate proxy, the
    same class of issue as the akshare/eastmoney gotcha in the workspace
    CLAUDE.md;
  * pace requests and retry ``429``/``5xx`` with exponential backoff;
  * cache low-frequency statistic queries on disk under ``.cache/stats/``
    with a per-key TTL (report PDFs continue to flow through ``report_cache``).

Mock-friendly: each client builds its ``httpx.Client`` via :func:`make_client`
inside its own ``_client()`` factory, so tests patch the client's ``_client``
(not this module) to inject a mock - mirroring how ``cninfo_client._client`` is
patched today. This module is pure and needs no mocking itself.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Callable, Optional

import httpx

# Default politeness sleep between consecutive calls (seconds). Individual
# clients may override via their own module-level ``SLEEP`` constant.
SLEEP = 0.3
_DEFAULT_TIMEOUT = 30.0
# Statuses that warrant a retry (rate-limit + transient server errors).
_RETRY_STATUS = {429, 500, 502, 503, 504}
_STAT_CACHE_DIR = Path(__file__).resolve().parent / ".cache" / "stats"


def make_client(
    base_url: str = "",
    *,
    headers: Optional[dict[str, str]] = None,
    timeout: float = _DEFAULT_TIMEOUT,
    follow_redirects: bool = True,
    trust_env: bool = False,
) -> httpx.Client:
    """Build a per-call httpx client.

    ``trust_env`` defaults to ``False`` so ``HTTP_PROXY``/``HTTPS_PROXY``/
    ``NO_PROXY`` environment variables are ignored - direct exchange and
    government endpoints must not be routed through a proxy (they reject or
    break). Callers pass ``trust_env=True`` only when a proxy is intentional.
    """
    return httpx.Client(
        base_url=base_url,
        timeout=timeout,
        headers=headers or {},
        follow_redirects=follow_redirects,
        trust_env=trust_env,
    )


def pace(sleep: float = SLEEP) -> None:
    """Sleep briefly between consecutive calls to be polite to gov/exchange sites."""
    if sleep > 0:
        time.sleep(sleep)


def request_retry(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    retries: int = 3,
    backoff_base: float = 0.5,
    **kwargs: Any,
) -> httpx.Response:
    """Issue an HTTP request, retrying ``429``/``5xx`` with exponential backoff.

    Transient statuses in :data:`_RETRY_STATUS` are retried up to ``retries``
    times. Non-retryable ``4xx`` raise immediately via the caller's
    ``raise_for_status``. Network errors (``httpx.RequestError``) are retried
    too. Raises the last error if all retries are exhausted.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            resp = client.request(method, url, **kwargs)
            if resp.status_code in _RETRY_STATUS and attempt < retries:
                time.sleep(backoff_base * (2 ** attempt))
                continue
            return resp
        except httpx.RequestError as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(backoff_base * (2 ** attempt))
                continue
            raise
    # Exhausted retries on a retryable status without a clean return.
    if last_exc is not None:
        raise last_exc
    # Unreachable: the loop either returns or raises.
    raise RuntimeError("request_retry exhausted retries unexpectedly")


def get_json(
    client: httpx.Client,
    url: str,
    *,
    retries: int = 3,
    **kwargs: Any,
) -> Any:
    """GET ``url`` and return parsed JSON. Retries 429/5xx; raises on other errors."""
    resp = request_retry(client, "GET", url, retries=retries, **kwargs)
    resp.raise_for_status()
    return resp.json()


def post_json(
    client: httpx.Client,
    url: str,
    *,
    data: Optional[dict] = None,
    retries: int = 3,
    **kwargs: Any,
) -> Any:
    """POST ``data`` (form-encoded by default) and return parsed JSON.

    Pass ``json=...`` via ``**kwargs`` to send a JSON body instead.
    """
    resp = request_retry(client, "POST", url, retries=retries, data=data, **kwargs)
    resp.raise_for_status()
    return resp.json()


# ── stat cache (TTL-keyed, miss/corruption-tolerant) ───────────────


def stat_cache_dir() -> Path:
    """Return the stat-cache directory, creating it on first use."""
    raw = os.environ.get("CNREPORT_STAT_CACHE_DIR", "").strip()
    d = Path(raw) if raw else _STAT_CACHE_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def stat_cache_key(*parts: Any) -> str:
    """Build a stable cache key from arbitrary parts (endpoint + query args)."""
    joined = "|".join(str(p) for p in parts)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()[:24]


def stat_cache_get(key: str, ttl: float) -> tuple[bool, Any]:
    """Return ``(hit, value)`` for a cached stat query within its TTL.

    A missing, expired, or corrupt entry is treated as a miss - this function
    never raises.
    """
    path = stat_cache_dir() / f"{key}.json"
    if not path.exists():
        return False, None
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - float(blob.get("ts", 0)) > ttl:
            return False, None
        return True, blob.get("value")
    except Exception:
        return False, None


def stat_cache_set(key: str, value: Any) -> None:
    """Store a stat query result. Never raises on write failure."""
    path = stat_cache_dir() / f"{key}.json"
    try:
        path.write_text(
            json.dumps({"ts": time.time(), "value": value}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


def cached_stat(key: str, ttl: float, fetcher: Callable[[], Any]) -> Any:
    """Memoize a stat fetch behind the TTL stat cache.

    ``fetcher`` is called only on a miss; its return value is cached and
    returned. Cache read/write errors are treated as a miss, so a corrupt
    cache entry simply triggers a re-fetch.
    """
    hit, value = stat_cache_get(key, ttl)
    if hit:
        return value
    value = fetcher()
    stat_cache_set(key, value)
    return value
