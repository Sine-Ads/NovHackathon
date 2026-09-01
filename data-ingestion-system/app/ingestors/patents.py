"""app/ingestors/patents.py — Patent Filings and Grants Ingestor.

API Reference:
  - USPTO Open Data Portal: https://developer.uspto.gov/
  - Endpoint: https://developer.uspto.gov/ibd-api/v1/patent/application
  - Authentication: API key required via USPTO_API_KEY header.
    If USPTO_API_KEY is not configured, gracefully logs info and returns empty list.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app.ingestors.base import BaseIngestor, RawItem
from app.utils.logging import get_logger

logger = get_logger(__name__)


class PatentsIngestor(BaseIngestor):
    """Fetches patent applications and grants related to haemophilia."""

    name: str = "patents"
    display_name: str = "USPTO Patents"
    BASE_URL: str = "https://developer.uspto.gov/ibd-api/v1/patent/application"

    async def fetch(
        self, last_cursor: Optional[str] = None
    ) -> Tuple[List[RawItem], Optional[str]]:
        """Fetch patent applications matching haemophilia from USPTO API.

        Args:
            last_cursor: Offset start index string.
        """
        items: List[RawItem] = []
        api_key = self.settings.uspto_api_key

        if not api_key:
            logger.warning(
                "[%s] USPTO_API_KEY is not configured. Patents ingestion is disabled. "
                "Get a free API key at https://developer.uspto.gov/",
                self.name,
            )
            return items, last_cursor

        start_offset = 0
        if last_cursor:
            try:
                start_offset = int(last_cursor)
            except ValueError:
                start_offset = 0

        max_items = self.settings.ingestor_max_items_per_run
        page_size = min(50, max_items) if max_items > 0 else 50

        headers = {"X-API-KEY": api_key, "Accept": "application/json"}
        params: Dict[str, Any] = {
            "searchText": "haemophilia OR hemophilia",
            "start": start_offset,
            "rows": page_size,
        }

        try:
            resp = await self.get_with_retry(self.BASE_URL, params=params, headers=headers)
            data = resp.json()
            response_data = data.get("response", {})
            docs = response_data.get("docs", [])

            for doc in docs:
                app_num = doc.get("patentApplicationNumber") or doc.get("id")
                if not app_num:
                    continue

                title = doc.get("inventionTitle") or "Untitled Patent Application"
                abstract = doc.get("abstractText") or ""
                app_date_str = doc.get("filingDate") or doc.get("grantDate")
                date_published = self.parse_datetime(app_date_str)
                applicant = doc.get("applicantName") or doc.get("assigneeEntityName")

                source_url = f"https://patents.google.com/patent/US{app_num}"

                item = RawItem(
                    source_name=self.display_name,
                    source_id=str(app_num),
                    source_url=source_url,
                    title=title,
                    raw_content=abstract,
                    date_published=date_published,
                    metadata={
                        "application_number": app_num,
                        "applicant": applicant,
                        "filing_date": app_date_str,
                        "grant_date": doc.get("grantDate"),
                    },
                )
                items.append(item)

            next_offset = start_offset + len(docs)
            return items, str(next_offset)

        except Exception as e:
            logger.error("[%s] Error fetching USPTO patents: %s", self.name, e)
            return items, last_cursor
