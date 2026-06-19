"""Pure data structures for the downloader. No I/O, no network — just types.

Keeping these free of behaviour means every other module can depend on them
without dragging in httpx/Playwright, and tests can build fixtures trivially.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum


class AipSection(StrEnum):
    """Top-level eAIP sections, in publication order."""

    GEN = "GEN"
    ENR = "ENR"
    AD = "AD"


# Lower rank sorts earlier. Kept separate from the enum so recon can extend the
# enum (e.g. SUP/AIC) without the ordering logic silently defaulting to 0.
SECTION_RANK: dict[AipSection, int] = {
    AipSection.GEN: 0,
    AipSection.ENR: 1,
    AipSection.AD: 2,
}


class PageStatus(StrEnum):
    """Lifecycle of a single page within a version snapshot."""

    PENDING = "pending"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"  # already present and unchanged; not re-fetched


class DeltaSignal(StrEnum):
    """How we decided which pages changed between versions (best → worst)."""

    CHECKLIST = "checklist"  # GEN 0.4 checklist of effective pages
    AMDT = "amdt"  # AIRAC AMDT change list
    HTTP_VALIDATORS = "http_validators"  # ETag / Last-Modified
    HASH = "hash"  # content hash comparison
    NONE = "none"  # no reliable signal → full re-download


@dataclass(frozen=True)
class VersionInfo:
    """An AIP edition as advertised on the service landing page."""

    version_id: str
    effective_date: date
    landing_url: str
    is_active: bool = False
    airac_cycle: str | None = None


@dataclass
class PageRecord:
    """One AIP page. Mutable: hash/status/validators are filled at download time."""

    ordering_index: int
    section: AipSection
    page_id: str
    source_url: str
    output_filename: str
    title: str | None = None
    content_hash: str | None = None
    byte_size: int | None = None
    etag: str | None = None
    last_modified: str | None = None
    status: PageStatus = PageStatus.PENDING
    fetched_at: datetime | None = None
    change_marker: str | None = None  # site-provided NEW/CHG marker, if any


@dataclass
class DeltaInfo:
    """Provenance of the delta decision recorded in a manifest."""

    signal: DeltaSignal = DeltaSignal.NONE
    compared_against: str | None = None


@dataclass
class VersionManifest:
    """The per-version source of truth, persisted as manifest.json."""

    version_id: str
    effective_date: date
    source_landing_url: str
    pages: list[PageRecord] = field(default_factory=list)
    airac_cycle: str | None = None
    delta: DeltaInfo = field(default_factory=DeltaInfo)
    schema_version: int = 1
    tool_version: str = "0.1.0"
    generated_at: datetime | None = None

    def page_by_id(self, page_id: str) -> PageRecord | None:
        return next((p for p in self.pages if p.page_id == page_id), None)


@dataclass
class SessionContext:
    """An authenticated session, however it was obtained.

    `cookies` seed an httpx client; `storage_state_path` points at a persisted
    Playwright state for browser reuse. `expires_at` lets the pipeline re-auth.
    """

    cookies: dict[str, str] = field(default_factory=dict)
    storage_state_path: str | None = None
    expires_at: datetime | None = None
