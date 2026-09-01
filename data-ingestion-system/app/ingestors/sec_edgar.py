"""app/ingestors/sec_edgar.py — SEC EDGAR Corporate Filings Ingestor.

API Reference:
  - SEC EDGAR Full-Text Search (EFTS): https://efts.sec.gov/LATEST/search-index
  - Developer Info: https://www.sec.gov/developer
  - User-Agent: MANDATORY by SEC Fair Access Policy (e.g. "AppName admin@example.com")
  - Rate limit: 10 req/s maximum
  - Query: Searches Form 10-K, 10-Q disclosures for haemophilia/hemophilia mentions.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.ingestors.base import BaseIngestor, RawItem
from app.utils.logging import get_logger

logger = get_logger(__name__)


class SecEdgarIngestor(BaseIngestor):
    """Fetches SEC EDGAR corporate filings mentioning haemophilia treatments or research."""

    name: str = "sec_edgar"
    display_name: str = "SEC EDGAR"
    SEARCH_URL: str = "https://efts.sec.gov/LATEST/search-index"

    async def fetch(
        self, last_cursor: Optional[str] = None
    ) -> Tuple[List[RawItem], Optional[str]]:
        """Fetch SEC Form 10-K, 10-Q filings with haemophilia keywords.

        Args:
            last_cursor: Integer offset string for pagination.
        """
        items: List[RawItem] = []
        max_items = self.settings.ingestor_max_items_per_run
        page_size = min(50, max_items) if max_items > 0 else 50

        from_offset = 0
        if last_cursor:
            try:
                from_offset = int(last_cursor)
            except ValueError:
                from_offset = 0

        # Query 10-K (annual) and 10-Q (quarterly) filings
        params: Dict[str, Any] = {
            "q": '"haemophilia" OR "hemophilia"',
            "forms": "10-K,10-Q",
            "from": from_offset,
            "size": page_size,
        }

        # SEC requires compliant User-Agent
        headers = {
            "User-Agent": self.settings.sec_edgar_user_agent or "HaemophiliaIngestionSystem admin@example.com",
            "Accept": "application/json",
        }

        try:
            logger.debug("[%s] Searching SEC EDGAR from=%d size=%d", self.name, from_offset, page_size)
            resp = await self.get_with_retry(self.SEARCH_URL, params=params, headers=headers)
            data = resp.json()

            hits_container = data.get("hits", {})
            hits = hits_container.get("hits", [])

            for hit in hits:
                doc_id = hit.get("_id")
                source = hit.get("_source", {})
                if not doc_id:
                    continue

                adsh = source.get("adsh", doc_id)
                display_names = source.get("display_names", [])
                company_name = display_names[0] if display_names else "Unknown Company"
                form_type = source.get("form", "Filing")
                file_date_str = source.get("file_date")
                period_ending = source.get("period_ending")
                file_desc = source.get("file_description", "")

                highlights = hit.get("highlight", {})
                file_text_highlights = highlights.get("file_text", [])
                highlight_snippet = "\n...\n".join(file_text_highlights)

                date_published = self.parse_datetime(file_date_str)
                title = f"{company_name} — Form {form_type} ({file_date_str or 'N/A'})"

                raw_content = (
                    f"Company: {company_name}\n"
                    f"Form Type: {form_type}\n"
                    f"Period Ending: {period_ending or 'N/A'}\n"
                    f"File Description: {file_desc}\n\n"
                    f"Matching Excerpts:\n{highlight_snippet}"
                )

                # Link to SEC filing archives
                # Form url format: https://www.sec.gov/edgar/searchedgar/companysearch
                source_url = f"https://www.sec.gov/Archives/edgar/data/{source.get('ciks', [''])[0]}/{adsh.replace('-', '')}"

                item = RawItem(
                    source_name=self.display_name,
                    source_id=f"{adsh}:{doc_id}",
                    source_url=source_url,
                    title=title,
                    raw_content=raw_content,
                    date_published=date_published,
                    metadata={
                        "adsh": adsh,
                        "form": form_type,
                        "company_name": company_name,
                        "ciks": source.get("ciks", []),
                        "file_date": file_date_str,
                        "period_ending": period_ending,
                        "sic": source.get("sics", []),
                    },
                )
                items.append(item)

                if max_items > 0 and len(items) >= max_items:
                    break

            next_offset = from_offset + len(hits)
            return items, str(next_offset)

        except Exception as e:
            logger.error("[%s] Failed fetching SEC EDGAR: %s", self.name, e)
            return items, last_cursor
