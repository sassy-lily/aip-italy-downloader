"""Active-version identification. RECON-BLOCKED parsing; pure logic implemented.

get_active_version must read the service landing page to find the current active
edition (vs upcoming not-yet-active ones) — the selectors/date format are a
Phase 1 recon target. detect_change is pure and implemented now.
"""

from __future__ import annotations

import httpx

from .config import Settings
from .models import VersionInfo

_NOT_YET = (
    "EnavVersionProvider.get_active_version is recon-blocked: how the landing "
    "page lists the active version is determined in Phase 1."
)


def detect_change(active: VersionInfo, stored_version_id: str | None) -> bool:
    """True if the active version differs from the last one we downloaded."""
    return stored_version_id != active.version_id


class EnavVersionProvider:
    async def get_active_version(
        self, client: httpx.AsyncClient, settings: Settings
    ) -> VersionInfo:
        raise NotImplementedError(_NOT_YET)
