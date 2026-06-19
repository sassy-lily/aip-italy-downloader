"""Recon-blocked stubs: pure logic works; site-specific calls raise until recon."""

from __future__ import annotations

from datetime import date

import pytest

from aip_downloader.auth import EnavAuth
from aip_downloader.discover import EnavDiscoverer
from aip_downloader.models import VersionInfo
from aip_downloader.version import EnavVersionProvider, detect_change


def test_detect_change():
    active = VersionInfo("2026-06-25-AIRAC", date(2026, 6, 25), "https://x")
    assert detect_change(active, "2026-05-28-AIRAC") is True
    assert detect_change(active, "2026-06-25-AIRAC") is False
    assert detect_change(active, None) is True


async def test_auth_is_recon_blocked():
    with pytest.raises(NotImplementedError):
        await EnavAuth().get_session(None)


async def test_version_provider_is_recon_blocked():
    with pytest.raises(NotImplementedError):
        await EnavVersionProvider().get_active_version(None, None)


async def test_discoverer_is_recon_blocked():
    with pytest.raises(NotImplementedError):
        await EnavDiscoverer().discover(None, None)
