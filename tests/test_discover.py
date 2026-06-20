"""Page enumeration from the eAIP menu: order, dedup, language, PDF URLs."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import httpx
import respx

from aip_downloader.discover import EnavDiscoverer, pdf_url
from aip_downloader.models import AipSection, VersionInfo

FIXTURES = Path(__file__).parent / "fixtures"
EDITION_URL = "https://onlineservices.test/(A06-26)_2026_06_11/"


def _version() -> VersionInfo:
    return VersionInfo(
        "(A06-26)_2026_06_11", date(2026, 6, 11), EDITION_URL, True, "A06-26"
    )


@respx.mock
async def test_discover_enumerates_in_menu_order():
    menu = (FIXTURES / "eaip_menu_sample.html").read_text(encoding="utf-8")
    respx.get(EDITION_URL + "eAIP/menu.html").mock(
        return_value=httpx.Response(200, text=menu)
    )

    async with httpx.AsyncClient() as client:
        records = await EnavDiscoverer().discover(client, _version())

    # Document order preserved (AD grouped by ICAO, not sorted by page number);
    # en-GB variant excluded; GEN 0.1 not duplicated.
    assert [r.page_id for r in records] == [
        "GEN 0.1",
        "GEN 0.4",
        "ENR 1.1",
        "ENR 1.2",
        "ENR 1.10",
        "AD 2  LIRF - ROMA FIUMICINO 1",
        "AD 2  LIRF - ROMA FIUMICINO 2",
        "AD 2  LIMC - MILANO MALPENSA 1",
    ]

    gen04 = next(r for r in records if r.page_id == "GEN 0.4")
    assert gen04.section == AipSection.GEN
    assert gen04.source_url == EDITION_URL + "documents/PDF/LI-GEN%200.4.pdf"


def test_pdf_url_encodes_spaces():
    assert pdf_url(EDITION_URL, "AD 2  LIRF - ROMA FIUMICINO 1") == (
        EDITION_URL + "documents/PDF/LI-AD%202%20%20LIRF%20-%20ROMA%20FIUMICINO%201.pdf"
    )
