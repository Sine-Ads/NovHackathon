"""app/ingestors/base.py — Base classes and data structures for all ingestors.

Defines:
  - RawItem: Unified normalized dataclass representing an ingested record.
  - BaseIngestor: Abstract base class that all 8 ingestors implement.
  - Common utilities for HTTP requests, retry logic, date parsing, rate-limiting.
"""
from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from email.utils import parsedate_to_datetime

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import get_settings
from app.database import IngestorLogModel, get_session, store_ingestor_log, upsert_raw_item, upsert_scheduling_metadata
from app.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class RawItem:
    """Normalized data representation of an item fetched from any source.

    Attributes:
        source_name: Identifier of the source (e.g. "ClinicalTrials.gov", "PubMed").
        source_id: Original unique identifier in the source system (e.g. NCT01234567, PMID 123456).
        source_url: Direct URL to the item on the source site.
        title: Title, headline, or brief label of the item.
        raw_content: Full text content (abstract, summary, filing excerpt, description).
        date_published: When the item was originally published/reported.
        date_ingested: When the item was fetched (defaults to now).
        metadata: Dictionary of source-specific structured attributes.
        is_active: Whether this item is active (default True).
    """

    source_name: str
    source_id: str
    source_url: Optional[str] = None
    title: Optional[str] = None
    raw_content: Optional[str] = None
    date_published: Optional[datetime] = None
    date_ingested: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_active: bool = True


class BaseIngestor(ABC):
    """Abstract Base Class for all data source ingestors.

    Subclasses must implement:
      - name (property or class attribute): Unique string identifier (e.g. "clinical_trials")
      - display_name (property): Human-readable name (e.g. "ClinicalTrials.gov")
      - fetch(last_cursor): Async method that yields or returns fetched items and next cursor.
    """

    name: str = "base"
    display_name: str = "Base Ingestor"

    def __init__(self) -> None:
        self.settings = get_settings()
        self._last_request_time: float = 0.0

    async def _rate_limit(self) -> None:
        """Enforce rate limit delay between successive API calls."""
        delay_seconds = self.settings.api_rate_limit_delay_ms / 1000.0
        now = asyncio.get_event_loop().time()
        elapsed = now - self._last_request_time
        if elapsed < delay_seconds:
            await asyncio.sleep(delay_seconds - elapsed)
        self._last_request_time = asyncio.get_event_loop().time()

    async def get_with_retry(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = 30.0,
    ) -> httpx.Response:
        """Execute an HTTP GET with rate limiting and exponential-backoff retry."""
        await self._rate_limit()

        default_headers = {
            "User-Agent": self.settings.sec_edgar_user_agent or "HaemophiliaDataIngestion/1.0",
            "Accept": "application/json, text/xml, application/xml, text/plain, */*",
        }
        if headers:
            default_headers.update(headers)

        @retry(
            reraise=True,
            stop=stop_after_attempt(self.settings.error_retry_max_attempts),
            wait=wait_exponential(
                multiplier=self.settings.error_retry_base_delay_seconds, min=1, max=10
            ),
            retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
        )
        async def _do_get() -> httpx.Response:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                resp = await client.get(url, params=params, headers=default_headers)
                # Retry on server errors or rate limit 429
                if resp.status_code in (429, 500, 502, 503, 504):
                    logger.warning(
                        "[%s] HTTP %s for %s, retrying...", self.name, resp.status_code, url
                    )
                    resp.raise_for_status()
                return resp

        return await _do_get()

    async def post_with_retry(
        self,
        url: str,
        json_data: Optional[Dict[str, Any]] = None,
        data: Optional[Any] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = 30.0,
    ) -> httpx.Response:
        """Execute an HTTP POST with rate limiting and exponential-backoff retry."""
        await self._rate_limit()

        default_headers = {
            "User-Agent": self.settings.sec_edgar_user_agent or "HaemophiliaDataIngestion/1.0",
        }
        if headers:
            default_headers.update(headers)

        @retry(
            reraise=True,
            stop=stop_after_attempt(self.settings.error_retry_max_attempts),
            wait=wait_exponential(
                multiplier=self.settings.error_retry_base_delay_seconds, min=1, max=10
            ),
            retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
        )
        async def _do_post() -> httpx.Response:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                resp = await client.post(
                    url, json=json_data, data=data, headers=default_headers
                )
                if resp.status_code in (429, 500, 502, 503, 504):
                    logger.warning(
                        "[%s] HTTP %s for %s, retrying...", self.name, resp.status_code, url
                    )
                    resp.raise_for_status()
                return resp

        return await _do_post()

    @staticmethod
    def parse_datetime(date_str: Optional[str]) -> Optional[datetime]:
        """Safely parse various common date string formats into UTC datetime."""
        if not date_str:
            return None
        date_str = date_str.strip()
        if not date_str:
            return None

        # ISO formats
        for fmt in (
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%Y%m%d",
            "%d/%m/%Y",
            "%m/%d/%Y",
            "%B %d, %Y",
            "%b %d, %Y",
            "%Y-%m",
            "%Y",
        ):
            try:
                dt = datetime.strptime(date_str, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                continue

        # Try RFC 2822 / HTTP date format
        try:
            dt = parsedate_to_datetime(date_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            pass

        return None

    @abstractmethod
    async def fetch(
        self, last_cursor: Optional[str] = None
    ) -> Tuple[List[RawItem], Optional[str]]:
        """Fetch items from the data source.

        Args:
            last_cursor: Cursor/token/offset from previous execution (if any).

        Returns:
            Tuple of:
              - list of parsed RawItem objects
              - next_cursor: new cursor to save for next run (or None if completed)
        """
        raise NotImplementedError

    async def run(self, last_cursor: Optional[str] = None) -> Tuple[int, int, Optional[str]]:
        """Execute a full ingestion run: fetch items, store to DB, return stats.

        Returns:
            Tuple of (items_fetched, items_stored, next_cursor)
        """
        start_time = datetime.now(timezone.utc)
        items_fetched = 0
        items_stored = 0
        error_msg: Optional[str] = None
        next_cursor: Optional[str] = None

        logger.info("[%s] Starting ingestion run (last_cursor=%s)", self.name, last_cursor)

        try:
            items, next_cursor = await self.fetch(last_cursor=last_cursor)
            items_fetched = len(items)

            # Store items to database
            async with get_session() as session:
                for item in items:
                    stored = await upsert_raw_item(
                        session=session,
                        source_name=item.source_name,
                        source_id=item.source_id,
                        source_url=item.source_url,
                        title=item.title,
                        raw_content=item.raw_content,
                        date_published=item.date_published,
                        metadata=item.metadata,
                        is_active=item.is_active,
                    )
                    if stored:
                        items_stored += 1

                # Update scheduling metadata
                await upsert_scheduling_metadata(
                    session=session,
                    ingestor_name=self.name,
                    last_run_timestamp=datetime.now(timezone.utc),
                    last_cursor=next_cursor,
                    consecutive_failures=0,
                )

            logger.info(
                "[%s] Ingestion completed: %d fetched, %d newly stored, next_cursor=%s",
                self.name,
                items_fetched,
                items_stored,
                next_cursor,
            )

        except Exception as exc:
            error_msg = f"{type(exc).__name__}: {str(exc)}"
            logger.exception("[%s] Ingestion failed: %s", self.name, error_msg)
            # Update consecutive failures in metadata
            try:
                async with get_session() as session:
                    meta = await upsert_scheduling_metadata(
                        session=session,
                        ingestor_name=self.name,
                        last_run_timestamp=datetime.now(timezone.utc),
                    )
                    meta.consecutive_failures += 1
            except Exception:
                pass
            raise
        finally:
            end_time = datetime.now(timezone.utc)
            duration = (end_time - start_time).total_seconds()
            # Record audit log
            try:
                async with get_session() as session:
                    log_entry = IngestorLogModel(
                        ingestor_name=self.name,
                        run_timestamp=start_time,
                        items_fetched=items_fetched,
                        items_stored=items_stored,
                        items_skipped=max(0, items_fetched - items_stored),
                        success=(error_msg is None),
                        error_message=error_msg,
                        last_cursor=next_cursor or last_cursor,
                        duration_seconds=duration,
                    )
                    await store_ingestor_log(session, log_entry)
            except Exception as log_exc:
                logger.error("[%s] Failed to record audit log: %s", self.name, log_exc)

        return items_fetched, items_stored, next_cursor
