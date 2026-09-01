"""app/ingestors/medrxiv.py — medRxiv / bioRxiv Preprints Ingestor.

API Reference:
  - Official Docs: https://api.biorxiv.org/
  - Endpoint: https://api.biorxiv.org/details/[server]/[interval]/[cursor]/[format]
  - Servers: medrxiv, biorxiv
  - Authentication: None required
  - Pagination: 100 records per page; increment cursor by 100
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from app.ingestors.base import BaseIngestor, RawItem
from app.utils.logging import get_logger

logger = get_logger(__name__)

HAEMOPHILIA_KEYWORDS = [
    "haemophilia",
    "hemophilia",
    "factor viii",
    "factor ix",
    "emicizumab",
    "fitusiran",
    "valoctocogene",
    "etranacogene",
]


class MedRxivIngestor(BaseIngestor):
    """Fetches preprints from medRxiv / bioRxiv and filters for haemophilia research."""

    name: str = "medrxiv"
    display_name: str = "medRxiv"
    BASE_URL: str = "https://api.biorxiv.org/details/medrxiv"

    def _matches_haemophilia(self, title: str, abstract: str) -> bool:
        """Check if title or abstract contains any haemophilia keywords."""
        content = (title + " " + abstract).lower()
        return any(kw in content for kw in HAEMOPHILIA_KEYWORDS)

    async def fetch(
        self, last_cursor: Optional[str] = None
    ) -> Tuple[List[RawItem], Optional[str]]:
        """Fetch preprints from medRxiv over the configured time window.

        Args:
            last_cursor: Formatted as "{start_date}:{cursor_offset}"
        """
        items: List[RawItem] = []
        max_items = self.settings.ingestor_max_items_per_run

        cursor_offset = 0
        now = datetime.now(timezone.utc)
        # Default interval: past 90 days
        start_date_str = (now - timedelta(days=90)).strftime("%Y-%m-%d")
        end_date_str = now.strftime("%Y-%m-%d")

        if last_cursor and ":" in last_cursor:
            parts = last_cursor.split(":")
            if len(parts) == 2:
                start_date_str = parts[0]
                try:
                    cursor_offset = int(parts[1])
                except ValueError:
                    cursor_offset = 0

        interval_param = f"{start_date_str}/{end_date_str}"

        while True:
            url = f"{self.BASE_URL}/{interval_param}/{cursor_offset}/json"
            logger.debug("[%s] Fetching %s", self.name, url)

            try:
                resp = await self.get_with_retry(url)
                data = resp.json()
            except Exception as e:
                logger.error("[%s] Error fetching medRxiv API: %s", self.name, e)
                break

            messages = data.get("messages", [{}])
            total_in_interval = int(messages[0].get("total", 0)) if messages else 0
            collection = data.get("collection", [])

            if not collection:
                logger.info("[%s] No preprints returned for interval %s at cursor %d", self.name, interval_param, cursor_offset)
                break

            for paper in collection:
                doi = paper.get("doi")
                if not doi:
                    continue

                title = paper.get("title", "Untitled Preprint")
                abstract = paper.get("abstract", "")

                # Filter client-side for haemophilia keywords
                if not self._matches_haemophilia(title, abstract):
                    continue

                date_str = paper.get("date")
                date_published = self.parse_datetime(date_str)
                authors = paper.get("authors", "")
                category = paper.get("category", "")
                version = paper.get("version", "1")
                server = paper.get("server", "medrxiv")

                source_url = f"https://www.medrxiv.org/content/{doi}v{version}"

                item = RawItem(
                    source_name=self.display_name,
                    source_id=doi,
                    source_url=source_url,
                    title=title,
                    raw_content=abstract,
                    date_published=date_published,
                    metadata={
                        "doi": doi,
                        "authors": authors,
                        "category": category,
                        "version": version,
                        "server": server,
                        "published_doi": paper.get("published"),
                    },
                )
                items.append(item)

                if max_items > 0 and len(items) >= max_items:
                    break

            cursor_offset += len(collection)

            # Stop if reached total or max_items
            if cursor_offset >= total_in_interval or (max_items > 0 and len(items) >= max_items):
                break

        next_cursor = f"{start_date_str}:{cursor_offset}"
        return items, next_cursor
