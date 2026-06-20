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


def _manifest_with(pages) -> VersionManifest:
    return VersionManifest(
        version_id="2026-06-25-AIRAC",
        effective_date=date(2026, 6, 25),
        source_landing_url="https://x",
        pages=pages,
    )


def test_merge_pages_updates_in_place_and_preserves_untouched(make_page):
    prior = _manifest_with(
        [
            make_page("A", ordering_index=0, status=PageStatus.DONE, etag='"a"'),
            make_page("B", ordering_index=1, status=PageStatus.DONE, etag='"b"'),
            make_page("C", ordering_index=2, status=PageStatus.DONE, etag='"c"'),
        ]
    )
    # B is re-processed this run: its record carries new validators/status.
    fresh = [make_page("B", ordering_index=1, status=PageStatus.SKIPPED, etag='"b2"')]

    merged = m.merge_pages(prior, fresh)

    assert [p.page_id for p in merged] == ["A", "B", "C"]  # order preserved
    by_id = {p.page_id: p for p in merged}
    assert by_id["B"].etag == '"b2"'  # fresh data wins
    assert by_id["B"].status == PageStatus.SKIPPED
    assert by_id["A"].etag == '"a"'  # untouched prior records intact
    assert by_id["C"].etag == '"c"'


def test_merge_pages_appends_new_id_in_order(make_page):
    prior = _manifest_with(
        [
            make_page("A", ordering_index=0),
            make_page("C", ordering_index=2),
        ]
    )
    # D is new this run and sorts between A and C by ordering_index.
    fresh = [make_page("D", ordering_index=1, status=PageStatus.DONE)]

    merged = m.merge_pages(prior, fresh)

    assert [p.page_id for p in merged] == ["A", "D", "C"]


def test_merge_pages_no_prior_returns_fresh(make_page):
    fresh = [
        make_page("A", ordering_index=0),
        make_page("B", ordering_index=1),
    ]
    merged = m.merge_pages(None, fresh)
    assert [p.page_id for p in merged] == ["A", "B"]
