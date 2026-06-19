"""Fetch individual PDFs: polite, idempotent, resumable, atomic.

Skip rules, in order:
  1. already on disk + manifest says DONE  -> skip without any request
  2. conditional GET returns 304 (ETag/Last-Modified) -> skip the body
Otherwise download to a ``*.part`` file and atomically rename, so an interrupted
run never leaves a truncated PDF that a later run would mistake for complete.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import httpx

from .logging_setup import get_logger
from .models import PageRecord, PageStatus
from .politeness import PolitenessPolicy, Throttle, retry

logger = get_logger(__name__)

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class TransientHTTPError(Exception):
    """A retryable server-side condition (429 / 5xx)."""


def _utcnow() -> datetime:
    return datetime.now(UTC)


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _is_retryable(exc: Exception) -> bool:
    return isinstance(exc, TransientHTTPError | httpx.TransportError)


def _carry_forward(record: PageRecord, prior: PageRecord) -> PageRecord:
    """Reuse a prior download's metadata when the page is unchanged."""
    record.content_hash = prior.content_hash
    record.byte_size = prior.byte_size
    record.etag = prior.etag
    record.last_modified = prior.last_modified
    record.fetched_at = prior.fetched_at
    record.status = PageStatus.SKIPPED
    return record


async def download_page(
    client: httpx.AsyncClient,
    record: PageRecord,
    version_dir: Path,
    *,
    throttle: Throttle,
    policy: PolitenessPolicy,
    prior: PageRecord | None = None,
    force_full: bool = False,
    now: Callable[[], datetime] = _utcnow,
) -> PageRecord:
    """Download one page into ``version_dir``, honouring skip/resume rules."""
    target = version_dir / record.output_filename

    if (
        not force_full
        and prior is not None
        and prior.status
        in (
            PageStatus.DONE,
            PageStatus.SKIPPED,
        )
        and target.exists()
    ):
        logger.debug("skip (present): %s", record.page_id)
        return _carry_forward(record, prior)

    headers: dict[str, str] = {}
    if not force_full and prior is not None and target.exists():
        if prior.etag:
            headers["If-None-Match"] = prior.etag
        if prior.last_modified:
            headers["If-Modified-Since"] = prior.last_modified

    async def _get() -> httpx.Response:
        async with throttle.slot():
            response = await client.get(record.source_url, headers=headers)
        if response.status_code in _RETRYABLE_STATUS:
            raise TransientHTTPError(f"{response.status_code} for {record.page_id}")
        return response

    try:
        response = await retry(_get, policy=policy, is_retryable=_is_retryable)
    except Exception:
        logger.exception("failed to fetch %s", record.page_id)
        record.status = PageStatus.FAILED
        return record

    if response.status_code == 304:
        logger.debug("skip (304 unchanged): %s", record.page_id)
        if prior is not None:
            return _carry_forward(record, prior)
        record.status = PageStatus.DONE
        return record

    if response.status_code != 200:
        logger.error("unexpected %s for %s", response.status_code, record.page_id)
        record.status = PageStatus.FAILED
        return record

    content = response.content
    version_dir.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".part")
    tmp.write_bytes(content)
    tmp.replace(target)  # atomic on the same filesystem

    record.content_hash = sha256_bytes(content)
    record.byte_size = len(content)
    record.etag = response.headers.get("ETag")
    record.last_modified = response.headers.get("Last-Modified")
    record.fetched_at = now()
    record.status = PageStatus.DONE
    logger.info("downloaded %s (%d bytes)", record.output_filename, len(content))
    return record


async def download_all(
    client: httpx.AsyncClient,
    records: list[PageRecord],
    version_dir: Path,
    *,
    throttle: Throttle,
    policy: PolitenessPolicy,
    prior_by_id: dict[str, PageRecord] | None = None,
    force_full: bool = False,
    now: Callable[[], datetime] = _utcnow,
) -> list[PageRecord]:
    """Download all pages concurrently; the throttle bounds real parallelism."""
    prior_by_id = prior_by_id or {}
    tasks = [
        download_page(
            client,
            record,
            version_dir,
            throttle=throttle,
            policy=policy,
            prior=prior_by_id.get(record.page_id),
            force_full=force_full,
            now=now,
        )
        for record in records
    ]
    return await asyncio.gather(*tasks)
