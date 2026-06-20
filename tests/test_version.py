"""Active-version detection and edition-href parsing."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import httpx
import respx

from aip_downloader import version as ver
from aip_downloader.config import Settings
from aip_downloader.models import VersionInfo

FIXTURES = Path(__file__).parent / "fixtures"


def test_detect_change():
    active = VersionInfo("(A06-26)_2026_06_11", date(2026, 6, 11), "https://x/")
    assert ver.detect_change(active, "(A05-26)_2026_05_14") is True
    assert ver.detect_change(active, "(A06-26)_2026_06_11") is False
    assert ver.detect_change(active, None) is True


def test_parse_edition_normalizes_backslash_href():
    v = ver.parse_edition(r"(A06-26)_2026_06_11\index.html")
    assert v.version_id == "(A06-26)_2026_06_11"
    assert v.effective_date == date(2026, 6, 11)
    assert v.airac_cycle == "A06-26"
    assert v.landing_url.endswith("(A06-26)_2026_06_11/")


@respx.mock
async def test_get_active_version_from_landing_fixture():
    landing = (FIXTURES / "landing_defaultInt.html").read_text(encoding="utf-8")
    respx.get(ver.LANDING_URL).mock(return_value=httpx.Response(200, text=landing))
    settings = Settings(base_url="x", output_dir=Path(), user="", password="")

    async with httpx.AsyncClient() as client:
        v = await ver.EnavVersionProvider().get_active_version(client, settings)

    # The active edition is the one under "Uscita Corrente" (A06-26), not the
    # upcoming A07 or the archived A05.
    assert v.version_id == "(A06-26)_2026_06_11"
    assert v.effective_date == date(2026, 6, 11)
    assert v.is_active
