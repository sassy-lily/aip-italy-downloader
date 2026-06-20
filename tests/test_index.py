"""Rendering and writing the per-version index.html table of contents."""

from __future__ import annotations

from datetime import date

from aip_downloader import index
from aip_downloader.models import (
    AipSection,
    PageStatus,
    VersionManifest,
)


def _manifest(pages) -> VersionManifest:
    return VersionManifest(
        version_id="2026-06-25-AIRAC",
        effective_date=date(2026, 6, 25),
        source_landing_url="https://onlineservices.test/landing",
        pages=pages,
        airac_cycle="2026-07",
    )


def _build_manifest(make_page) -> VersionManifest:
    # Deliberately out of section order on input, to prove the renderer reorders.
    pages = [
        make_page(
            "AD-2.LIRF",
            AipSection.AD,
            ordering_index=3,
            output_filename="0003_AD-2.LIRF.pdf",
            title="Roma Fiumicino",
            status=PageStatus.DONE,
            byte_size=2048,
        ),
        make_page(
            "GEN-0.1",
            AipSection.GEN,
            ordering_index=1,
            output_filename="0001_GEN-0.1.pdf",
            title="Preface",
            status=PageStatus.DONE,
            byte_size=1024,
        ),
        make_page(
            "ENR-1.1",
            AipSection.ENR,
            ordering_index=2,
            output_filename="0002_ENR-1.1.pdf",
            title=None,  # exercises the page_id title fallback
            status=PageStatus.SKIPPED,
        ),
    ]
    return _manifest(pages)


def test_sections_in_gen_enr_ad_order(make_page):
    html = index.render_index(_build_manifest(make_page))
    gen = html.index(">GEN ")
    enr = html.index(">ENR ")
    ad = html.index(">AD ")
    assert gen < enr < ad


def test_pages_keep_manifest_order_within_section(make_page):
    # Two ENR pages whose ordering_index disagrees with numeric page-id sort.
    pages = [
        make_page(
            "ENR-10.1",
            AipSection.ENR,
            ordering_index=1,
            output_filename="0001_ENR-10.1.pdf",
            status=PageStatus.DONE,
        ),
        make_page(
            "ENR-2.1",
            AipSection.ENR,
            ordering_index=2,
            output_filename="0002_ENR-2.1.pdf",
            status=PageStatus.DONE,
        ),
    ]
    html = index.render_index(_manifest(pages))
    assert html.index("ENR-10.1") < html.index("ENR-2.1")


def test_present_pages_link_to_relative_output_filename(make_page):
    html = index.render_index(_build_manifest(make_page))
    assert 'href="0001_GEN-0.1.pdf"' in html
    assert 'href="0002_ENR-1.1.pdf"' in html
    # Relative: no scheme, no leading slash on the href value.
    assert 'href="/' not in html
    assert 'href="http' not in html


def test_title_falls_back_to_page_id(make_page):
    # ENR-1.1 has title=None, so its page_id must appear as the link text.
    html = index.render_index(_build_manifest(make_page))
    assert ">ENR-1.1</a>" in html


def test_failed_and_pending_pages_are_unlinked(make_page):
    pages = [
        make_page(
            "ENR-5.1",
            AipSection.ENR,
            ordering_index=1,
            output_filename="0001_ENR-5.1.pdf",
            title="Broken",
            status=PageStatus.FAILED,
        ),
        make_page(
            "ENR-5.2",
            AipSection.ENR,
            ordering_index=2,
            output_filename="0002_ENR-5.2.pdf",
            title="Untouched",
            status=PageStatus.PENDING,
        ),
    ]
    html = index.render_index(_manifest(pages))
    # No anchors at all, since nothing is present on disk.
    assert "<a href" not in html
    assert "0001_ENR-5.1.pdf" not in html
    assert 'class="missing"' in html
    assert "failed" in html
    assert "pending" in html


def test_titles_are_html_escaped(make_page):
    pages = [
        make_page(
            "ENR-9.9",
            AipSection.ENR,
            ordering_index=1,
            output_filename="0001_ENR-9.9.pdf",
            title='Danger <script>alert("x")</script> & co',
            status=PageStatus.DONE,
        )
    ]
    html = index.render_index(_manifest(pages))
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "&amp; co" in html


def test_summary_reports_counts_and_missing(make_page):
    html = index.render_index(_build_manifest(make_page))
    assert "3 pages total" in html
    # Build manifest has all-present pages; add a failed one and re-check.
    pages = list(_build_manifest(make_page).pages)
    pages.append(
        make_page(
            "AD-2.LIPZ",
            AipSection.AD,
            ordering_index=4,
            output_filename="0004_AD-2.LIPZ.pdf",
            status=PageStatus.FAILED,
        )
    )
    html2 = index.render_index(_manifest(pages))
    assert "1 missing/failed" in html2


def test_write_index_writes_to_version_dir(tmp_path, make_page):
    manifest = _build_manifest(make_page)
    path = index.write_index(manifest, tmp_path)
    assert path == tmp_path / "index.html"
    assert path.exists()
    assert path.read_text(encoding="utf-8").startswith("<!doctype html>")
    # No leftover temp file.
    assert not (tmp_path / "index.html.part").exists()
