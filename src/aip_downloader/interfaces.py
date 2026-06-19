"""Structural contracts (typing.Protocol) for the site-specific collaborators.

The pipeline and tests depend on these shapes, not on the concrete ENAV
implementations. That is what lets the recon-blocked modules (auth/version/
discover) be swapped for fakes today and real logic after recon, with no change
to the orchestration code.
"""

from __future__ import annotations

from typing import Protocol

import httpx

from .config import Settings
from .models import PageRecord, SessionContext, VersionInfo


class AuthProvider(Protocol):
    async def get_session(self, settings: Settings) -> SessionContext: ...


class VersionProvider(Protocol):
    async def get_active_version(
        self, client: httpx.AsyncClient, settings: Settings
    ) -> VersionInfo: ...


class Discoverer(Protocol):
    async def discover(
        self, client: httpx.AsyncClient, version: VersionInfo
    ) -> list[PageRecord]: ...
