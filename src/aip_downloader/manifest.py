"""Read, write, and diff the per-version manifest.json.

The manifest is the single source of truth for a version snapshot: it drives
idempotent resume (within a version) and change detection (across versions).
This module owns all JSON shape concerns so models.py can stay pure data.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from .models import (
    AipSection,
    DeltaInfo,
    DeltaSignal,
    PageRecord,
    PageStatus,
    VersionManifest,
)

MANIFEST_NAME = "manifest.json"


def _page_to_dict(page: PageRecord) -> dict:
    return {
        "ordering_index": page.ordering_index,
        "section": page.section.value,
        "page_id": page.page_id,
        "title": page.title,
        "source_url": page.source_url,
        "output_filename": page.output_filename,
        "content_hash": page.content_hash,
        "byte_size": page.byte_size,
        "etag": page.etag,
        "last_modified": page.last_modified,
        "status": page.status.value,
        "fetched_at": page.fetched_at.isoformat() if page.fetched_at else None,
        "change_marker": page.change_marker,
    }


def _page_from_dict(data: dict) -> PageRecord:
    fetched_at = data.get("fetched_at")
    return PageRecord(
        ordering_index=data["ordering_index"],
        section=AipSection(data["section"]),
        page_id=data["page_id"],
        source_url=data["source_url"],
        output_filename=data["output_filename"],
        title=data.get("title"),
        content_hash=data.get("content_hash"),
        byte_size=data.get("byte_size"),
        etag=data.get("etag"),
        last_modified=data.get("last_modified"),
        status=PageStatus(data.get("status", PageStatus.PENDING.value)),
        fetched_at=datetime.fromisoformat(fetched_at) if fetched_at else None,
        change_marker=data.get("change_marker"),
    )


def manifest_to_dict(manifest: VersionManifest) -> dict:
    return {
        "schema_version": manifest.schema_version,
        "version_id": manifest.version_id,
        "effective_date": manifest.effective_date.isoformat(),
        "airac_cycle": manifest.airac_cycle,
        "source_landing_url": manifest.source_landing_url,
        "generated_at": (
            manifest.generated_at.isoformat() if manifest.generated_at else None
        ),
        "tool_version": manifest.tool_version,
        "delta": {
            "signal": manifest.delta.signal.value,
            "compared_against": manifest.delta.compared_against,
        },
        "pages": [_page_to_dict(p) for p in manifest.pages],
    }


def manifest_from_dict(data: dict) -> VersionManifest:
    delta_data = data.get("delta", {})
    generated_at = data.get("generated_at")
    return VersionManifest(
        version_id=data["version_id"],
        effective_date=date.fromisoformat(data["effective_date"]),
        source_landing_url=data["source_landing_url"],
        pages=[_page_from_dict(p) for p in data.get("pages", [])],
        airac_cycle=data.get("airac_cycle"),
        delta=DeltaInfo(
            signal=DeltaSignal(delta_data.get("signal", DeltaSignal.NONE.value)),
            compared_against=delta_data.get("compared_against"),
        ),
        schema_version=data.get("schema_version", 1),
        tool_version=data.get("tool_version", "0.1.0"),
        generated_at=datetime.fromisoformat(generated_at) if generated_at else None,
    )


def merge_pages(
    prior: VersionManifest | None, fresh: list[PageRecord]
) -> list[PageRecord]:
    """Overlay this run's pages onto the prior snapshot without dropping any.

    A version snapshot is append/update-only, so a manifest write must never
    truncate to just the pages processed this run (which is what `--limit` would
    otherwise cause). Keyed by `page_id`:

    - a page processed this run *replaces* its prior record;
    - a page new this run is *appended*;
    - a prior page not touched this run is *preserved unchanged* (status, hash,
      validators all intact, so a later run still emits conditional GETs).

    The merged list is returned sorted by `ordering_index` to keep the manifest
    in authoritative menu order. With `prior=None` this is just `fresh` ordered.
    """
    # dict preserves insertion order, but ordering_index is the authority, so we
    # sort at the end regardless of which side a given page came from.
    by_id: dict[str, PageRecord] = {}
    if prior is not None:
        for page in prior.pages:
            by_id[page.page_id] = page
    for page in fresh:
        by_id[page.page_id] = page
    return sorted(by_id.values(), key=lambda p: p.ordering_index)


def manifest_path(version_dir: Path) -> Path:
    return version_dir / MANIFEST_NAME


def save(manifest: VersionManifest, version_dir: Path) -> Path:
    """Write the manifest atomically into the version directory."""
    version_dir.mkdir(parents=True, exist_ok=True)
    target = manifest_path(version_dir)
    tmp = target.with_suffix(".json.part")
    tmp.write_text(json.dumps(manifest_to_dict(manifest), indent=2), encoding="utf-8")
    tmp.replace(target)
    return target


def load(version_dir: Path) -> VersionManifest | None:
    """Load an existing manifest, or None if this version was never downloaded."""
    target = manifest_path(version_dir)
    if not target.exists():
        return None
    return manifest_from_dict(json.loads(target.read_text(encoding="utf-8")))


@dataclass(frozen=True)
class ManifestDiff:
    """Set-level comparison of page ids between two versions."""

    added: list[str]
    removed: list[str]
    common: list[str]


def diff_against(
    current: list[PageRecord], previous: VersionManifest | None
) -> ManifestDiff:
    """Compare current page ids against a previous version's manifest.

    Reports added/removed/common ids. Deciding which *common* pages actually
    changed (and must be re-fetched) is the caller's job, using the chosen
    DeltaSignal — this stays pure set logic.
    """
    current_ids = {p.page_id for p in current}
    previous_ids = (
        {p.page_id for p in previous.pages} if previous is not None else set()
    )
    return ManifestDiff(
        added=sorted(current_ids - previous_ids),
        removed=sorted(previous_ids - current_ids),
        common=sorted(current_ids & previous_ids),
    )
