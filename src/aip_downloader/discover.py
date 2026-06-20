"""Enumerate the pages of an edition from its eAIP TOC menu.

Pages are listed (with duplicates) in <edition>/eAIP/menu.html as
``LI-<page_id>-it-IT.html`` links. We keep the first occurrence of each page in
document order — which is the authoritative publication order (numeric sort is
wrong for AD aerodromes). The per-page PDF is derived per docs/RECON.md section 5:
``documents/PDF/LI-<page_id>.pdf`` (one bilingual PDF, language suffix dropped).
"""

from __future__ import annotations

import re
from urllib.parse import quote

import httpx

from .logging_setup import get_logger
from .models import AipSection, PageRecord, VersionInfo

logger = get_logger(__name__)

# it-IT links only, so each page is counted once (the PDF is language-neutral).
_PAGE_RE = re.compile(r"LI-((?:GEN|ENR|AD)[^'\"#]+?)-it-IT\.html")


def pdf_url(edition_url: str, page_id: str) -> str:
    """Build the per-page PDF URL under the edition's documents/PDF folder."""
    return f"{edition_url}documents/PDF/{quote(f'LI-{page_id}.pdf')}"


class EnavDiscoverer:
    async def discover(
        self, client: httpx.AsyncClient, version: VersionInfo
    ) -> list[PageRecord]:
        menu_url = f"{version.landing_url}eAIP/menu.html"
        response = await client.get(menu_url)
        response.raise_for_status()

        seen: set[str] = set()
        records: list[PageRecord] = []
        for match in _PAGE_RE.finditer(response.text):
            page_id = match.group(1).strip()
            if page_id in seen:
                continue
            seen.add(page_id)
            records.append(
                PageRecord(
                    ordering_index=0,  # stamped by naming.renumber in menu order
                    section=AipSection(page_id.split()[0]),
                    page_id=page_id,
                    source_url=pdf_url(version.landing_url, page_id),
                    output_filename="",
                )
            )
        logger.info("enumerated %d pages from %s", len(records), menu_url)
        return records
