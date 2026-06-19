"""End-to-end orchestration with faked auth/version/discover and mocked HTTP."""

from __future__ import annotations

from datetime import UTC, date, datetime

import httpx
import respx

from aip_downloader import pipeline
from aip_downloader.config import Settings
from aip_downloader.models import (
    AipSection,
    PageRecord,
    PageStatus,
    SessionContext,
    VersionInfo,
)
from aip_downloader.politeness import PolitenessPolicy


class FakeAuth:
    async def get_session(self, settings: Settings) -> SessionContext:
        return SessionContext(cookies={})


class FakeVersionProvider:
    async def get_active_version(self, client, settings) -> VersionInfo:
        return VersionInfo(
            version_id="2026-06-25-AIRAC",
            effective_date=date(2026, 6, 25),
            landing_url="https://onlineservices.test/landing",
            is_active=True,
            airac_cycle="2026-07",
        )


class FakeDiscoverer:
    def __init__(self, pages: list[PageRecord]) -> None:
        self._pages = pages

    async def discover(self, client, version) -> list[PageRecord]:
        return list(self._pages)


def _settings(tmp_path) -> Settings:
    return Settings(
        base_url="https://example.test",
        output_dir=tmp_path,
        user="u",
        password="p",
        politeness=PolitenessPolicy(
            max_concurrency=4, delay_seconds=0.0, jitter_seconds=0.0, max_attempts=1
        ),
    )


def _make_pages() -> list[PageRecord]:
    def page(section: AipSection, page_id: str) -> PageRecord:
        return PageRecord(
            ordering_index=0,
            section=section,
            page_id=page_id,
            source_url=f"https://example.test/{page_id}.pdf",
            output_filename="",
        )

    # Deliberately out of order to prove the pipeline sorts them.
    return [
        page(AipSection.ENR, "ENR-1.10"),
        page(AipSection.ENR, "ENR-1.2"),
        page(AipSection.GEN, "GEN-0.4"),
    ]


def _now() -> datetime:
    return datetime(2026, 6, 20, 12, tzinfo=UTC)


def _mock_pdf(page_id: str) -> None:
    respx.get(f"https://example.test/{page_id}.pdf").mock(
        return_value=httpx.Response(
            200, content=f"pdf-{page_id}".encode(), headers={"ETag": f'"{page_id}"'}
        )
    )


@respx.mock
async def test_pipeline_downloads_in_publication_order(tmp_path):
    for pid in ("ENR-1.10", "ENR-1.2", "GEN-0.4"):
        _mock_pdf(pid)

    manifest = await pipeline.run(
        _settings(tmp_path),
        auth=FakeAuth(),
        version_provider=FakeVersionProvider(),
        discoverer=FakeDiscoverer(_make_pages()),
        now=_now,
    )

    version_dir = tmp_path / "2026-06-25-AIRAC"
    assert [p.page_id for p in manifest.pages] == ["GEN-0.4", "ENR-1.2", "ENR-1.10"]
    assert (version_dir / "0001_GEN-0.4.pdf").exists()
    assert (version_dir / "0002_ENR-1.2.pdf").exists()
    assert (version_dir / "0003_ENR-1.10.pdf").exists()
    assert (version_dir / "manifest.json").exists()
    assert all(p.status == PageStatus.DONE for p in manifest.pages)


@respx.mock
async def test_dry_run_downloads_nothing(tmp_path):
    route = respx.get("https://example.test/GEN-0.4.pdf")
    pages = [
        PageRecord(0, AipSection.GEN, "GEN-0.4", "https://example.test/GEN-0.4.pdf", "")
    ]

    manifest = await pipeline.run(
        _settings(tmp_path),
        auth=FakeAuth(),
        version_provider=FakeVersionProvider(),
        discoverer=FakeDiscoverer(pages),
        dry_run=True,
        now=_now,
    )

    assert manifest.pages[0].status == PageStatus.PENDING
    assert not (tmp_path / "2026-06-25-AIRAC").exists()
    assert route.call_count == 0


@respx.mock
async def test_second_run_resumes_and_skips(tmp_path):
    for pid in ("GEN-0.4", "ENR-1.1"):
        _mock_pdf(pid)
    pages = [
        PageRecord(
            0, AipSection.GEN, "GEN-0.4", "https://example.test/GEN-0.4.pdf", ""
        ),
        PageRecord(
            0, AipSection.ENR, "ENR-1.1", "https://example.test/ENR-1.1.pdf", ""
        ),
    ]

    await pipeline.run(
        _settings(tmp_path),
        auth=FakeAuth(),
        version_provider=FakeVersionProvider(),
        discoverer=FakeDiscoverer(pages),
        now=_now,
    )
    counts_after_first = {
        pid: respx.get(f"https://example.test/{pid}.pdf").call_count
        for pid in ("GEN-0.4", "ENR-1.1")
    }

    fresh_pages = [
        PageRecord(
            0, AipSection.GEN, "GEN-0.4", "https://example.test/GEN-0.4.pdf", ""
        ),
        PageRecord(
            0, AipSection.ENR, "ENR-1.1", "https://example.test/ENR-1.1.pdf", ""
        ),
    ]
    manifest = await pipeline.run(
        _settings(tmp_path),
        auth=FakeAuth(),
        version_provider=FakeVersionProvider(),
        discoverer=FakeDiscoverer(fresh_pages),
        now=_now,
    )

    for pid in ("GEN-0.4", "ENR-1.1"):
        assert (
            respx.get(f"https://example.test/{pid}.pdf").call_count
            == counts_after_first[pid]
        )
    assert all(p.status == PageStatus.SKIPPED for p in manifest.pages)
