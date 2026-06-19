"""Shared test fixtures."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from aip_downloader.models import AipSection, PageRecord, PageStatus
from aip_downloader.politeness import PolitenessPolicy, Throttle


@pytest.fixture
def fast_policy() -> PolitenessPolicy:
    """A policy with no delays and no retries — fast and deterministic."""
    return PolitenessPolicy(
        max_concurrency=4,
        delay_seconds=0.0,
        jitter_seconds=0.0,
        max_attempts=1,
    )


@pytest.fixture
def throttle(fast_policy: PolitenessPolicy) -> Throttle:
    return Throttle(fast_policy, rng=lambda: 0.0)


@pytest.fixture
def make_page() -> Callable[..., PageRecord]:
    def _make(
        page_id: str,
        section: AipSection = AipSection.ENR,
        *,
        source_url: str | None = None,
        output_filename: str | None = None,
        status: PageStatus = PageStatus.PENDING,
        ordering_index: int = 0,
        **kwargs: object,
    ) -> PageRecord:
        return PageRecord(
            ordering_index=ordering_index,
            section=section,
            page_id=page_id,
            source_url=source_url or f"https://example.test/{page_id}.pdf",
            output_filename=output_filename or f"{page_id}.pdf",
            status=status,
            **kwargs,
        )

    return _make
