"""app/ingestors/arxiv.py — arXiv Preprints Ingestor.

API Reference:
  - Official API: http://export.arxiv.org/api/query
  - User Manual: https://info.arxiv.org/help/api/user-manual.html
  - Search Query: (ti:haemophilia OR abs:haemophilia OR ti:hemophilia OR abs:hemophilia)
  - Pagination: start (offset) + max_results
  - Response Format: Atom 1.0 XML
  - Rate limits: 3 req/s maximum (1 req / 3s recommended)
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

import defusedxml.ElementTree as DefusedET

from app.ingestors.base import BaseIngestor, RawItem
from app.utils.logging import get_logger

logger = get_logger(__name__)

# Atom XML namespace
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


class ArxivIngestor(BaseIngestor):
    """Fetches scientific preprints from arXiv matching haemophilia queries."""

    name: str = "arxiv"
    display_name: str = "arXiv"
    BASE_URL: str = "http://export.arxiv.org/api/query"

    async def fetch(
        self, last_cursor: Optional[str] = None
    ) -> Tuple[List[RawItem], Optional[str]]:
        """Fetch arXiv preprints matching haemophilia terms.

        Args:
            last_cursor: Integer string representing the start offset.
        """
        items: List[RawItem] = []
        max_items = self.settings.ingestor_max_items_per_run
        batch_size = 50

        start_offset = 0
        if last_cursor:
            try:
                start_offset = int(last_cursor)
            except ValueError:
                start_offset = 0

        # Query searches title and abstract for both spellings
        search_query = "(ti:haemophilia OR abs:haemophilia OR ti:hemophilia OR abs:hemophilia)"

        while True:
            params: Dict[str, Any] = {
                "search_query": search_query,
                "start": start_offset,
                "max_results": batch_size,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
            }

            logger.debug("[%s] Fetching arXiv start=%d max=%d", self.name, start_offset, batch_size)
            resp = await self.get_with_retry(self.BASE_URL, params=params)

            try:
                root = DefusedET.fromstring(resp.content)
            except Exception as e:
                logger.error("[%s] Failed to parse arXiv Atom XML: %s", self.name, e)
                break

            entries = root.findall("atom:entry", ATOM_NS)
            if not entries:
                logger.info("[%s] No entries returned at offset %d", self.name, start_offset)
                break

            for entry in entries:
                id_elem = entry.find("atom:id", ATOM_NS)
                if id_elem is None or not id_elem.text:
                    continue

                full_id_url = id_elem.text.strip()
                # Extract arxiv id, e.g. "2301.12345v1" or "math/0102034v1"
                arxiv_id_match = re.search(r"arxiv\.org/abs/(.+)$", full_id_url)
                arxiv_id = arxiv_id_match.group(1) if arxiv_id_match else full_id_url

                title_elem = entry.find("atom:title", ATOM_NS)
                title = " ".join(title_elem.text.split()) if title_elem is not None and title_elem.text else "Untitled"

                summary_elem = entry.find("atom:summary", ATOM_NS)
                summary = " ".join(summary_elem.text.split()) if summary_elem is not None and summary_elem.text else ""

                published_elem = entry.find("atom:published", ATOM_NS)
                published_str = published_elem.text.strip() if published_elem is not None and published_elem.text else None
                date_published = self.parse_datetime(published_str)

                # Authors
                authors = [
                    a.findtext("atom:name", "", ATOM_NS).strip()
                    for a in entry.findall("atom:author", ATOM_NS)
                    if a.findtext("atom:name", "", ATOM_NS)
                ]

                # Categories
                categories = [
                    cat.attrib.get("term", "")
                    for cat in entry.findall("atom:category", ATOM_NS)
                    if cat.attrib.get("term")
                ]

                # DOI if present
                doi_elem = entry.find("arxiv:doi", ATOM_NS)
                doi = doi_elem.text.strip() if doi_elem is not None and doi_elem.text else None

                source_url = f"https://arxiv.org/abs/{arxiv_id}"

                item = RawItem(
                    source_name=self.display_name,
                    source_id=arxiv_id,
                    source_url=source_url,
                    title=title,
                    raw_content=summary,
                    date_published=date_published,
                    metadata={
                        "arxiv_id": arxiv_id,
                        "doi": doi,
                        "authors": authors,
                        "categories": categories,
                        "feed_url": full_id_url,
                    },
                )
                items.append(item)

                if max_items > 0 and len(items) >= max_items:
                    break

            start_offset += len(entries)

            if len(entries) < batch_size or (max_items > 0 and len(items) >= max_items):
                break

        return items, str(start_offset)
