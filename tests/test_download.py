"""Download mechanics: write, skip, conditional 304, atomicity, failure."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
import respx

from aip_downloader import download
from aip_downloader.models import PageStatus
from aip_downloader.politeness import PolitenessPolicy, Throttle


def _now() -> datetime:
    return datetime(2026, 6, 20, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def dl_policy() -> PolitenessPolicy:
    return PolitenessPolicy(
        max_concurrency=2, delay_seconds=0.0, jitter_seconds=0.0, max_attempts=1
    )


@respx.mock
async def test_download_writes_file_and_metadata(tmp_path, make_page, dl_policy):
    page = make_page("ENR-1.1", output_filename="0001_ENR-1.1.pdf")
    route = respx.get(page.source_url).mock(
        return_value=httpx.Response(
            200,
            content=b"%PDF data",
            headers={"ETag": '"e1"', "Last-Modified": "Wed, 04 Jun 2026 00:00:00 GMT"},
        )
    )
    throttle = Throttle(dl_policy, rng=lambda: 0.0)

    async with httpx.AsyncClient() as client:
        result = await download.download_page(
            client, page, tmp_path, throttle=throttle, policy=dl_policy, now=_now
        )

    assert result.status == PageStatus.DONE
    assert (tmp_path / "0001_ENR-1.1.pdf").read_bytes() == b"%PDF data"
    assert result.content_hash == download.sha256_bytes(b"%PDF data")
    assert result.byte_size == 9
    assert result.etag == '"e1"'
    assert result.fetched_at == _now()
    assert not list(tmp_path.glob("*.part"))  # atomic: no leftover temp file
    assert route.call_count == 1


@respx.mock
async def test_skip_when_already_present(tmp_path, make_page, dl_policy):
    page = make_page("ENR-1.1", output_filename="0001_ENR-1.1.pdf")
    (tmp_path / "0001_ENR-1.1.pdf").write_bytes(b"existing")
    prior = make_page(
        "ENR-1.1",
        output_filename="0001_ENR-1.1.pdf",
        status=PageStatus.DONE,
        content_hash="sha256:x",
        etag='"e1"',
    )
    route = respx.get(page.source_url)
    throttle = Throttle(dl_policy, rng=lambda: 0.0)

    async with httpx.AsyncClient() as client:
        result = await download.download_page(
            client,
            page,
            tmp_path,
            throttle=throttle,
            policy=dl_policy,
            prior=prior,
            now=_now,
        )

    assert result.status == PageStatus.SKIPPED
    assert route.call_count == 0  # never hit the network


@respx.mock
async def test_conditional_304_carries_forward(tmp_path, make_page, dl_policy):
    page = make_page("ENR-1.1", output_filename="0001_ENR-1.1.pdf")
    (tmp_path / "0001_ENR-1.1.pdf").write_bytes(b"cached")
    # prior not DONE so the outright-skip is bypassed and a conditional GET runs.
    prior = make_page(
        "ENR-1.1",
        output_filename="0001_ENR-1.1.pdf",
        status=PageStatus.FAILED,
        etag='"e1"',
        content_hash="sha256:cached",
    )
    route = respx.get(page.source_url).mock(return_value=httpx.Response(304))
    throttle = Throttle(dl_policy, rng=lambda: 0.0)

    async with httpx.AsyncClient() as client:
        result = await download.download_page(
            client,
            page,
            tmp_path,
            throttle=throttle,
            policy=dl_policy,
            prior=prior,
            now=_now,
        )

    assert result.status == PageStatus.SKIPPED
    assert result.content_hash == "sha256:cached"
    assert route.call_count == 1
    request = route.calls.last.request
    assert request.headers["If-None-Match"] == '"e1"'


@respx.mock
async def test_server_error_marks_failed(tmp_path, make_page, dl_policy):
    page = make_page("ENR-1.1", output_filename="0001_ENR-1.1.pdf")
    respx.get(page.source_url).mock(return_value=httpx.Response(500))
    throttle = Throttle(dl_policy, rng=lambda: 0.0)

    async with httpx.AsyncClient() as client:
        result = await download.download_page(
            client, page, tmp_path, throttle=throttle, policy=dl_policy, now=_now
        )

    assert result.status == PageStatus.FAILED
    assert not (tmp_path / "0001_ENR-1.1.pdf").exists()
