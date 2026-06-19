"""Page enumeration. RECON-BLOCKED: body filled in after Phase 1.

discover() must walk the active edition's TOC and yield one PageRecord per page
across GEN/ENR/AD, each carrying its section, official page id, title, and the
URL from which its PDF can be fetched. Whether the TOC is static HTML or
JS-rendered, and the exact PDF URL shape, are Phase 1 recon targets.
"""

from __future__ import annotations

import httpx

from .models import PageRecord, VersionInfo

_NOT_YET = (
    "EnavDiscoverer.discover is recon-blocked: the eAIP TOC structure and "
    "per-page PDF URLs are determined in Phase 1."
)


class EnavDiscoverer:
    async def discover(
        self, client: httpx.AsyncClient, version: VersionInfo
    ) -> list[PageRecord]:
        raise NotImplementedError(_NOT_YET)
