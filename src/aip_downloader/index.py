"""Render a human-browsable ``index.html`` table of contents for a snapshot.

A version snapshot is a directory of per-page PDFs plus ``manifest.json`` — the
manifest is the source of truth, but it is JSON, not something you open in a
browser. This module turns a :class:`VersionManifest` into a self-contained
HTML page whose links resolve when the file is opened directly from the version
directory.

Rendering (pure, ``str``-producing) is kept separate from the file write so the
markup can be unit-tested without touching the filesystem, and so this module
never needs httpx, parsing, or any network I/O.
"""

from __future__ import annotations

from datetime import UTC, datetime
from html import escape
from pathlib import Path

from .logging_setup import get_logger
from .models import (
    SECTION_RANK,
    AipSection,
    PageRecord,
    PageStatus,
    VersionManifest,
)

logger = get_logger(__name__)

INDEX_NAME = "index.html"

# Statuses whose page is actually present on disk and therefore safe to link.
_PRESENT_STATUSES = frozenset({PageStatus.DONE, PageStatus.SKIPPED})

_STYLE = """\
:root { color-scheme: light dark; }
body { font-family: system-ui, sans-serif; margin: 2rem auto; max-width: 60rem;
       padding: 0 1rem; line-height: 1.5; }
h1 { margin-bottom: 0.25rem; }
.meta { color: #666; font-size: 0.9rem; margin-bottom: 1.5rem; }
.summary { background: #0001; border-radius: 6px; padding: 0.75rem 1rem;
           margin-bottom: 1.5rem; font-size: 0.9rem; }
h2 { border-bottom: 2px solid currentColor; padding-bottom: 0.2rem;
     margin-top: 2rem; }
table { border-collapse: collapse; width: 100%; }
td, th { text-align: left; padding: 0.3rem 0.6rem; vertical-align: top; }
tr:nth-child(even) { background: #0001; }
td.idx { text-align: right; color: #888; font-variant-numeric: tabular-nums; }
td.size { text-align: right; color: #888; white-space: nowrap;
          font-variant-numeric: tabular-nums; }
.page-id { font-family: ui-monospace, monospace; font-size: 0.85em; color: #888; }
tr.missing td { color: #b00; }
tr.missing { background: #b0000010; }
.badge { font-size: 0.75em; text-transform: uppercase; letter-spacing: 0.03em;
         border: 1px solid currentColor; border-radius: 4px; padding: 0 0.3rem; }
"""


def _human_size(num_bytes: int | None) -> str:
    """Format a byte count as a compact human-readable string (1024-based)."""
    if num_bytes is None:
        return ""
    size = float(num_bytes)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024 or unit == "GiB":
            # Whole bytes have no fractional part worth showing.
            precision = 0 if unit == "B" else 1
            return f"{size:.{precision}f} {unit}"
        size /= 1024
    return f"{size:.1f} GiB"  # unreachable; satisfies type checkers


def _group_by_section(
    pages: list[PageRecord],
) -> list[tuple[AipSection, list[PageRecord]]]:
    """Group pages by section in SECTION_RANK order, preserving menu order within.

    ``ordering_index`` is already the authoritative menu order from discovery, so
    we never sort numerically by page id — we only sort *sections* by rank and
    keep each section's pages in the index order they arrived in.
    """
    groups: dict[AipSection, list[PageRecord]] = {}
    for page in pages:
        groups.setdefault(page.section, []).append(page)
    for section_pages in groups.values():
        section_pages.sort(key=lambda p: p.ordering_index)
    return sorted(
        groups.items(),
        key=lambda item: SECTION_RANK.get(item[0], len(SECTION_RANK)),
    )


def _render_row(page: PageRecord) -> str:
    present = page.status in _PRESENT_STATUSES
    title = escape(page.title or page.page_id)
    page_id = escape(page.page_id)
    size = _human_size(page.byte_size)

    if present:
        href = escape(page.output_filename, quote=True)
        title_cell = f'<a href="{href}">{title}</a>'
        row_class = ""
    else:
        # FAILED / PENDING: no file on disk, so make the gap obvious and unlinked.
        badge = escape(page.status.value)
        title_cell = f'{title} <span class="badge">{badge}</span>'
        row_class = ' class="missing"'

    return (
        f"<tr{row_class}>"
        f'<td class="idx">{page.ordering_index}</td>'
        f'<td><span class="page-id">{page_id}</span></td>'
        f"<td>{title_cell}</td>"
        f'<td class="size">{size}</td>'
        f"</tr>"
    )


def _render_section(section: AipSection, pages: list[PageRecord]) -> str:
    present = sum(1 for p in pages if p.status in _PRESENT_STATUSES)
    heading = (
        f"<h2>{escape(section.value)} "
        f'<span class="meta">({present}/{len(pages)} pages)</span></h2>'
    )
    rows = "\n".join(_render_row(p) for p in pages)
    return (
        f"{heading}\n"
        "<table>\n"
        "<thead><tr><th>#</th><th>Page</th><th>Title</th><th>Size</th></tr></thead>\n"
        f"<tbody>\n{rows}\n</tbody>\n"
        "</table>"
    )


def _render_summary(pages: list[PageRecord]) -> str:
    grouped = _group_by_section(pages)
    parts = [
        f"{escape(section.value)}: {len(section_pages)}"
        for section, section_pages in grouped
    ]
    missing = sum(1 for p in pages if p.status not in _PRESENT_STATUSES)
    line = f"{' · '.join(parts)} — {len(pages)} pages total"
    if missing:
        line += f", {missing} missing/failed"
    return f'<p class="summary">{line}</p>'


def render_index(manifest: VersionManifest) -> str:
    """Render a snapshot manifest as a self-contained HTML table of contents.

    Pure: produces a string and touches neither the filesystem nor the network.
    """
    generated = datetime.now(UTC).isoformat(timespec="seconds")
    title = f"AIP snapshot {escape(manifest.version_id)}"

    meta_bits = [f"Effective {escape(manifest.effective_date.isoformat())}"]
    if manifest.airac_cycle:
        meta_bits.append(f"AIRAC {escape(manifest.airac_cycle)}")
    meta_bits.append(f"generated {escape(generated)}")
    meta_line = " · ".join(meta_bits)

    sections = "\n".join(
        _render_section(section, pages)
        for section, pages in _group_by_section(manifest.pages)
    )

    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{title}</title>\n"
        f"<style>\n{_STYLE}</style>\n"
        "</head>\n"
        "<body>\n"
        f"<h1>{title}</h1>\n"
        f'<p class="meta">{meta_line}</p>\n'
        f"{_render_summary(manifest.pages)}\n"
        f"{sections}\n"
        "</body>\n"
        "</html>\n"
    )


def write_index(manifest: VersionManifest, version_dir: Path) -> Path:
    """Render and atomically write ``index.html`` into the version directory.

    Returns the path written. Uses the same ``.part`` → ``replace`` pattern as
    ``manifest.save`` so a reader never sees a half-written file.
    """
    version_dir.mkdir(parents=True, exist_ok=True)
    target = version_dir / INDEX_NAME
    tmp = target.with_suffix(".html.part")
    tmp.write_text(render_index(manifest), encoding="utf-8")
    tmp.replace(target)
    logger.info("wrote index to %s", target)
    return target
