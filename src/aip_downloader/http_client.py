"""Factory for a configured httpx.AsyncClient, plus Playwright cookie bridging.

Once login is solved with a browser, we persist a Playwright storage_state and
seed a plain httpx client with its cookies — so the bulk of the crawl/download
can run over fast async HTTP rather than a heavyweight browser.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from .politeness import PolitenessPolicy

# Generous read timeout for large AIP PDFs; short connect to fail fast.
_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=60.0, pool=10.0)


def build_async_client(
    policy: PolitenessPolicy,
    *,
    base_url: str = "",
    cookies: httpx.Cookies | dict[str, str] | None = None,
) -> httpx.AsyncClient:
    """Construct an AsyncClient with our User-Agent, timeouts, and redirects on."""
    return httpx.AsyncClient(
        base_url=base_url,
        headers={"User-Agent": policy.user_agent},
        timeout=_TIMEOUT,
        cookies=cookies,
        follow_redirects=True,
    )


def cookies_from_storage_state(path: str | Path) -> httpx.Cookies:
    """Build an httpx cookie jar from a Playwright storage_state.json file."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    jar = httpx.Cookies()
    for cookie in data.get("cookies", []):
        jar.set(
            name=cookie["name"],
            value=cookie["value"],
            domain=cookie.get("domain", ""),
            path=cookie.get("path", "/"),
        )
    return jar
