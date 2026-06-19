"""Orchestration: auth -> active version -> discover -> download -> manifest.

Pure control flow over the public contracts in interfaces.py, so it is fully
testable with fakes before any site-specific code exists.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from . import manifest as manifest_io
from . import naming
from .config import Settings
from .download import download_all
from .http_client import build_async_client, cookies_from_storage_state
from .interfaces import AuthProvider, Discoverer, VersionProvider
from .logging_setup import get_logger
from .models import DeltaInfo, VersionManifest
from .politeness import Throttle

logger = get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


async def run(
    settings: Settings,
    *,
    auth: AuthProvider,
    version_provider: VersionProvider,
    discoverer: Discoverer,
    dry_run: bool = False,
    force_full: bool = False,
    now: Callable[[], datetime] = _utcnow,
) -> VersionManifest:
    """Download the current active AIP into its own version snapshot.

    Returns the resulting manifest. In dry-run mode it discovers and orders the
    pages but downloads nothing and writes no manifest.
    """
    session = await auth.get_session(settings)
    cookies = (
        cookies_from_storage_state(session.storage_state_path)
        if session.storage_state_path
        else session.cookies
    )
    client = build_async_client(
        settings.politeness, base_url=settings.base_url, cookies=cookies
    )

    async with client:
        # Pin the active version once, so an AIRAC rollover mid-run cannot mix
        # two editions into one snapshot.
        active = await version_provider.get_active_version(client, settings)
        logger.info("active version: %s (%s)", active.version_id, active.effective_date)

        version_dir = settings.output_dir / naming.slugify_version(active.version_id)
        existing = manifest_io.load(version_dir)  # same-version resume state

        records = await discoverer.discover(client, active)
        ordered = naming.renumber(naming.sort_by_page_id(records))
        logger.info("discovered %d pages", len(ordered))

        manifest = VersionManifest(
            version_id=active.version_id,
            effective_date=active.effective_date,
            source_landing_url=active.landing_url,
            pages=ordered,
            airac_cycle=active.airac_cycle,
            delta=DeltaInfo(),
            generated_at=now(),
        )

        if dry_run:
            logger.info("dry-run: skipping download of %d pages", len(ordered))
            return manifest

        prior_by_id = (
            {p.page_id: p for p in existing.pages} if existing is not None else {}
        )
        throttle = Throttle(settings.politeness)
        manifest.pages = await download_all(
            client,
            ordered,
            version_dir,
            throttle=throttle,
            policy=settings.politeness,
            prior_by_id=prior_by_id,
            force_full=force_full,
            now=now,
        )
        manifest_io.save(manifest, version_dir)
        logger.info("wrote manifest for %s", active.version_id)
        return manifest
