"""Active-version identification from the eAIP landing page.

The landing page groups editions under labelled headings; the active edition is
the link under "Uscita Corrente". See docs/RECON.md section 2.
"""

from __future__ import annotations

import re
from datetime import date

import httpx
from bs4 import BeautifulSoup

from .config import Settings
from .logging_setup import get_logger
from .models import VersionInfo

logger = get_logger(__name__)

AIP_SERVICE_ROOT = "https://onlineservices.enav.it/enavWebPortalStatic/AIP/AIP/"
LANDING_URL = AIP_SERVICE_ROOT + "defaultInt.html"
ACTIVE_HEADING = "Uscita Corrente"

# Edition folder e.g. "(A06-26)_2026_06_11": AIRAC code in parens, then date.
_DATE_RE = re.compile(r"(\d{4})_(\d{2})_(\d{2})")
_CODE_RE = re.compile(r"\(([^)]+)\)")


def detect_change(active: VersionInfo, stored_version_id: str | None) -> bool:
    """True if the active version differs from the last one we downloaded."""
    return stored_version_id != active.version_id


def _edition_folder(href: str) -> str:
    """First path segment of an href, normalising backslash separators."""
    return href.replace("\\", "/").split("/")[0]


def parse_edition(href: str) -> VersionInfo:
    """Turn an edition href into a VersionInfo (no network)."""
    folder = _edition_folder(href)
    date_match = _DATE_RE.search(folder)
    if date_match is None:
        raise ValueError(f"no effective date in edition folder: {folder!r}")
    effective = date(int(date_match[1]), int(date_match[2]), int(date_match[3]))
    code_match = _CODE_RE.search(folder)
    return VersionInfo(
        version_id=folder,
        effective_date=effective,
        # Parentheses in the folder are valid URI sub-delims; recon confirmed the
        # server accepts them raw, so we don't percent-encode the edition folder.
        landing_url=f"{AIP_SERVICE_ROOT}{folder}/",
        is_active=True,
        airac_cycle=code_match[1] if code_match else None,
    )


class EnavVersionProvider:
    async def get_active_version(
        self, client: httpx.AsyncClient, settings: Settings
    ) -> VersionInfo:
        response = await client.get(LANDING_URL)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "lxml")

        heading = next(
            (h for h in soup.find_all("h2") if ACTIVE_HEADING in h.get_text()),
            None,
        )
        if heading is None:
            raise RuntimeError(f"could not find '{ACTIVE_HEADING}' on landing page")
        table = heading.find_next("table")
        link = table.find("a", href=True) if table else None
        if link is None:
            raise RuntimeError("no edition link under the active-version heading")

        version = parse_edition(link["href"])
        if version.effective_date > date.today():
            logger.warning(
                "active edition %s effective %s is in the future?",
                version.version_id,
                version.effective_date,
            )
        return version
