"""Manifest serialization, load/save round-trip, and cross-version diff."""

from __future__ import annotations

from datetime import UTC, date, datetime

from aip_downloader import manifest as m
from aip_downloader.models import (
    AipSection,
    DeltaInfo,
    DeltaSignal,
    PageStatus,
    VersionManifest,
)


def _sample_manifest(make_page) -> VersionManifest:
    page = make_page(
        "ENR-1.1",
        ordering_index=1,
        output_filename="0001_ENR-1.1.pdf",
        content_hash="sha256:abc",
        byte_size=10,
        etag='"e1"',
        status=PageStatus.DONE,
        fetched_at=datetime(2026, 6, 20, 10, tzinfo=UTC),
    )
    return VersionManifest(
        version_id="2026-06-25-AIRAC",
        effective_date=date(2026, 6, 25),
        source_landing_url="https://onlineservices.test/landing",
        pages=[page],
        airac_cycle="2026-07",
        delta=DeltaInfo(DeltaSignal.NONE),
        generated_at=datetime(2026, 6, 20, 10, tzinfo=UTC),
    )


def test_round_trip(tmp_path, make_page):
    original = _sample_manifest(make_page)
    m.save(original, tmp_path)
    loaded = m.load(tmp_path)

    assert loaded is not None
    assert loaded.version_id == original.version_id
    assert loaded.effective_date == original.effective_date
    assert loaded.airac_cycle == "2026-07"
    assert len(loaded.pages) == 1
    page = loaded.pages[0]
    assert page.page_id == "ENR-1.1"
    assert page.section == AipSection.ENR
    assert page.status == PageStatus.DONE
    assert page.fetched_at == original.pages[0].fetched_at


def test_load_missing_returns_none(tmp_path):
    assert m.load(tmp_path) is None


def test_diff_against(make_page):
    current = [make_page("ENR-1.1"), make_page("ENR-1.2")]
    previous = VersionManifest(
        version_id="2026-05-28-AIRAC",
        effective_date=date(2026, 5, 28),
        source_landing_url="https://x",
        pages=[make_page("ENR-1.1"), make_page("GEN-0.4", AipSection.GEN)],
    )
    diff = m.diff_against(current, previous)
    assert diff.added == ["ENR-1.2"]
    assert diff.removed == ["GEN-0.4"]
    assert diff.common == ["ENR-1.1"]


def test_diff_against_no_previous(make_page):
    diff = m.diff_against([make_page("ENR-1.1")], None)
    assert diff.added == ["ENR-1.1"]
    assert diff.removed == []
    assert diff.common == []
