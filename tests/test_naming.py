"""Ordering and filename logic."""

from __future__ import annotations

from datetime import date

from aip_downloader import naming
from aip_downloader.models import AipSection


def test_section_then_numeric_order(make_page):
    pages = [
        make_page("ENR-1.10", AipSection.ENR),
        make_page("ENR-1.2", AipSection.ENR),
        make_page("AD-2.1", AipSection.AD),
        make_page("GEN-0.4", AipSection.GEN),
    ]
    ordered = naming.sort_by_page_id(pages)
    # GEN before ENR before AD; within ENR, 1.2 before 1.10 (numeric, not lexical).
    assert [p.page_id for p in ordered] == ["GEN-0.4", "ENR-1.2", "ENR-1.10", "AD-2.1"]


def test_renumber_assigns_index_and_filename(make_page):
    pages = [make_page("GEN-0.4", AipSection.GEN), make_page("ENR-1.1")]
    naming.renumber(pages)
    assert pages[0].ordering_index == 1
    assert pages[0].output_filename == "0001_GEN-0.4.pdf"
    assert pages[1].ordering_index == 2
    assert pages[1].output_filename == "0002_ENR-1.1.pdf"


def test_output_filename_sanitizes_unsafe_chars():
    assert naming.output_filename(7, "AD 2/ENR") == "0007_AD-2-ENR.pdf"


def test_slugify_version():
    assert naming.slugify_version("2026-06-25 AIRAC") == "2026-06-25-AIRAC"
    assert naming.slugify_version("") == "unknown-version"


def test_version_dirname_iso_date_prefix():
    assert naming.version_dirname(date(2026, 6, 11), "A06-26") == "2026-06-11_A06-26"


def test_version_dirname_none_airac_falls_back_to_date():
    assert naming.version_dirname(date(2026, 6, 11), None) == "2026-06-11"


def test_version_dirname_sorts_chronologically_across_years():
    # The old AIRAC-code-first naming sorted Jan 2026 before Dec 2025; the ISO
    # date prefix fixes that.
    dec_2025 = naming.version_dirname(date(2025, 12, 25), "A12-25")
    jan_2026 = naming.version_dirname(date(2026, 1, 22), "A01-26")
    assert sorted([jan_2026, dec_2025]) == [dec_2025, jan_2026]
