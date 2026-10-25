"""
github_client.py
~~~~~~~~~~~~~~~~
Centralised async GitHub REST API client.

Responsibilities:
- Inject GITHUB_TOKEN authentication header on every request.
- Enforce a hard 10-second timeout on every outbound call.
- Detect rate-limit (403 / 429) responses and return a structured error dict
  instead of raising — callers never see a raw exception from quota exhaustion.
- Return structured error dicts for all other non-2xx responses.
- Log every request: method, URL, status, latency.
"""

import logging
import os
import time
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

_GITHUB_API_BASE = "https://api.github.com"
_TIMEOUT = 10.0  # seconds — applied to every outbound call


def _build_headers() -> dict[str, str]:
    token = os.getenv("GITHUB_TOKEN", "")
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _parse_rate_limit_retry(response: httpx.Response) -> int | None:
    """Return retry-after seconds if available, else None."""
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            return int(retry_after)
        except ValueError:
            pass
    reset_epoch = response.headers.get("X-RateLimit-Reset")
    if reset_epoch:
        try:
            return max(0, int(reset_epoch) - int(time.time()))
        except ValueError:
            pass
    return None


async def github_get(
    path: str,
    *,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Perform an authenticated GET against the GitHub REST API.

    Always returns a dict. On error the dict contains an ``"error"`` key:
      - rate_limited  → {"error": "rate_limited", "retry_after": <int>}
      - not_found     → {"error": "not_found", "message": <str>}
      - api_error     → {"error": "api_error",  "status": <int>, "message": <str>}
      - timeout       → {"error": "timeout", "message": <str>}
    """
    url = f"{_GITHUB_API_BASE}{path}"
    t0 = time.monotonic()

    try:
        async with httpx.AsyncClient(
            headers=_build_headers(), timeout=_TIMEOUT
        ) as client:
            response = await client.get(url, params=params)

        latency_ms = int((time.monotonic() - t0) * 1000)
        log.info(
            "github_get url=%s status=%s latency_ms=%d",
            url,
            response.status_code,
            latency_ms,
        )

        # ── Rate limit ─────────────────────────────────────────────────────────
        if response.status_code in (403, 429):
            retry_after = _parse_rate_limit_retry(response)
            log.warning("GitHub rate-limited: %s retry_after=%s", url, retry_after)
            return {"error": "rate_limited", "retry_after": retry_after}

        # ── Not found ──────────────────────────────────────────────────────────
        if response.status_code == 404:
            return {"error": "not_found", "message": f"Resource not found: {path}"}

        # ── Other non-2xx ──────────────────────────────────────────────────────
        if response.status_code >= 400:
            try:
                detail = response.json().get("message", response.text[:200])
            except Exception:
                detail = response.text[:200]
            return {
                "error": "api_error",
                "status": response.status_code,
                "message": detail,
            }

        return response.json()

    except httpx.TimeoutException:
        latency_ms = int((time.monotonic() - t0) * 1000)
        log.error("github_get timeout url=%s latency_ms=%d", url, latency_ms)
        return {"error": "timeout", "message": f"GitHub API timed out after {_TIMEOUT}s"}

    except httpx.RequestError as exc:
        log.error("github_get request_error url=%s error=%s", url, exc)
        return {"error": "request_error", "message": str(exc)}


async def github_get_raw(path: str, *, params: dict[str, Any] | None = None) -> bytes | dict:
    """
    Like github_get but returns raw bytes (used for file content endpoints).
    Returns an error dict on failure.
    """
    url = f"{_GITHUB_API_BASE}{path}"
    t0 = time.monotonic()

    raw_headers = _build_headers()
    raw_headers["Accept"] = "application/vnd.github.raw+json"

    try:
        async with httpx.AsyncClient(headers=raw_headers, timeout=_TIMEOUT) as client:
            response = await client.get(url, params=params)

        latency_ms = int((time.monotonic() - t0) * 1000)
        log.info(
            "github_get_raw url=%s status=%s latency_ms=%d size_bytes=%d",
            url,
            response.status_code,
            latency_ms,
            len(response.content),
        )

        if response.status_code in (403, 429):
            retry_after = _parse_rate_limit_retry(response)
            return {"error": "rate_limited", "retry_after": retry_after}

        if response.status_code == 404:
            return {"error": "not_found", "message": f"Resource not found: {path}"}

        if response.status_code >= 400:
            try:
                detail = response.json().get("message", response.text[:200])
            except Exception:
                detail = response.text[:200]
            return {"error": "api_error", "status": response.status_code, "message": detail}

        return response.content

    except httpx.TimeoutException:
        return {"error": "timeout", "message": f"GitHub API timed out after {_TIMEOUT}s"}

    except httpx.RequestError as exc:
        return {"error": "request_error", "message": str(exc)}
