"""Filename and ordering logic — pure functions, no I/O.

The ordering reproduces EUROCONTROL eAIP publication order; discover() may
override by supplying records already in the site's TOC order, in which case it
just calls renumber() to stamp the sequential prefix.
"""

from __future__ import annotations

import re
from datetime import date

from .models import SECTION_RANK, AipSection, PageRecord

_NUMBER_RE = re.compile(r"\d+")
_UNSAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")


def page_sort_key(
    section: AipSection, page_id: str
) -> tuple[int, tuple[int, ...], str]:
    """Order by section (GEN<ENR<AD), then dotted number compared as integers.

    Integer-tuple comparison makes ``ENR-1.2`` precede ``ENR-1.10`` (which a
    plain string sort would get wrong). The raw id is a final tiebreaker for
    non-numeric page ids.
    """
    numbers = tuple(int(n) for n in _NUMBER_RE.findall(page_id))
    return (SECTION_RANK[section], numbers, page_id)


def sort_by_page_id(records: list[PageRecord]) -> list[PageRecord]:
    """Return records sorted into eAIP publication order."""
    return sorted(records, key=lambda r: page_sort_key(r.section, r.page_id))


def output_filename(ordering_index: int, page_id: str) -> str:
    """Zero-padded order prefix + filesystem-safe official page id."""
    safe_id = _UNSAFE_RE.sub("-", page_id).strip("-")
    return f"{ordering_index:04d}_{safe_id}.pdf"


def renumber(records: list[PageRecord]) -> list[PageRecord]:
    """Assign a 1-based monotonic ordering_index and matching filename in place.

    Numbering follows the given list order, so callers control whether that is
    page-id order (sort_by_page_id) or the site's TOC order.
    """
    for index, record in enumerate(records, start=1):
        record.ordering_index = index
        record.output_filename = output_filename(index, record.page_id)
    return records


def slugify_version(version_id: str) -> str:
    """Make a version id safe to use as a directory name."""
    slug = _UNSAFE_RE.sub("-", version_id).strip("-")
    return slug or "unknown-version"


def version_dirname(effective_date: date, airac_cycle: str | None) -> str:
    """Chronologically-sortable snapshot dir name: ``<YYYY-MM-DD>_<airac>``.

    Leading with the ISO effective date makes a plain lexical sort match
    chronological order (unlike the AIRAC code, which sorts amendment-then-year).
    """
    date_part = effective_date.isoformat()  # ISO date: lexical == chronological
    if not airac_cycle:
        return date_part
    return f"{date_part}_{slugify_version(airac_cycle)}"
