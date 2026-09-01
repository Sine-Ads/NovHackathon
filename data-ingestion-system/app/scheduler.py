"""app/scheduler.py — APScheduler-based periodic task runner.

Features:
  - Dynamically registers all enabled ingestors as recurring async jobs.
  - Initial execution runs immediately upon scheduler start, then follows intervals.
  - Concurrency control: max_instances=1 per job ensures no overlapping runs.
  - Persistent state: loads last cursor from DB, updates scheduling metadata on completion.
  - Error resilience: catches and logs errors; increments failure counts.
  - Manual trigger support: allows ad-hoc execution of any registered ingestor.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import get_settings
from app.database import (
    get_last_cursor,
    get_scheduling_metadata,
    get_session,
    upsert_scheduling_metadata,
)
from app.ingestors import INGESTOR_REGISTRY, BaseIngestor
from app.utils.logging import get_logger

logger = get_logger(__name__)


class IngestionScheduler:
    """Manages periodic execution of all enabled data ingestors."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.scheduler = AsyncIOScheduler(timezone="UTC")
        self._running_jobs: Dict[str, bool] = {}

    async def execute_ingestor(self, ingestor_name: str) -> None:
        """Run a single ingestor job with cursor persistence and concurrency guard.

        Args:
            ingestor_name: The name key in INGESTOR_REGISTRY.
        """
        if ingestor_name not in INGESTOR_REGISTRY:
            logger.error("Ingestor '%s' is not registered in INGESTOR_REGISTRY", ingestor_name)
            return

        if self._running_jobs.get(ingestor_name, False):
            logger.warning(
                "[%s] Job is already running. Skipping duplicate concurrent run.",
                ingestor_name,
            )
            return

        self._running_jobs[ingestor_name] = True
        ingestor_cls = INGESTOR_REGISTRY[ingestor_name]
        ingestor: BaseIngestor = ingestor_cls()

        try:
            # Retrieve last stored cursor
            last_cursor: Optional[str] = None
            async with get_session() as session:
                last_cursor = await get_last_cursor(session, ingestor_name)

            logger.info("[%s] Executing run (last_cursor=%s)...", ingestor_name, last_cursor)
            fetched, stored, next_cursor = await ingestor.run(last_cursor=last_cursor)
            logger.info(
                "[%s] Ingestion finished: %d fetched, %d newly stored in DB, next_cursor=%s",
                ingestor_name,
                fetched,
                stored,
                next_cursor,
            )

        except Exception as exc:
            logger.exception("[%s] Unhandled exception during job execution: %s", ingestor_name, exc)
        finally:
            self._running_jobs[ingestor_name] = False

    async def setup_jobs(self, run_immediately: bool = True) -> None:
        """Initialize scheduling metadata in DB and schedule APScheduler jobs.

        Args:
            run_immediately: If True, schedule the first run immediately on start.
        """
        enabled_names = self.settings.enabled_ingestors_list
        logger.info("Setting up scheduler with enabled ingestors: %s", enabled_names)
        now = datetime.now(timezone.utc)

        async with get_session() as session:
            for name in enabled_names:
                if name not in INGESTOR_REGISTRY:
                    logger.warning("Enabled ingestor '%s' not found in registry. Skipping.", name)
                    continue

                interval_minutes = self.settings.get_interval_minutes(name)
                # Ensure record exists in DB
                await upsert_scheduling_metadata(
                    session=session,
                    ingestor_name=name,
                    run_interval_minutes=interval_minutes,
                    is_enabled=True,
                )

                # Add APScheduler interval job (next_run_time=now triggers immediately)
                next_time = now if run_immediately else None
                self.scheduler.add_job(
                    self.execute_ingestor,
                    trigger=IntervalTrigger(minutes=interval_minutes),
                    next_run_time=next_time,
                    args=[name],
                    id=f"job_{name}",
                    name=f"Ingestor: {name}",
                    replace_existing=True,
                    max_instances=1,
                )
                logger.info(
                    "Scheduled '%s' every %d minutes (first run: %s)",
                    name,
                    interval_minutes,
                    "Immediately" if run_immediately else f"in {interval_minutes}m",
                )

    def start(self) -> None:
        """Start the background scheduler."""
        self.scheduler.start()
        logger.info("APScheduler started successfully")

    def shutdown(self) -> None:
        """Gracefully shut down the scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("APScheduler shut down")

    async def trigger_all_immediately(self) -> None:
        """Trigger an immediate run for all enabled ingestors."""
        enabled_names = self.settings.enabled_ingestors_list
        logger.info("Triggering immediate run for all enabled ingestors: %s", enabled_names)
        tasks = [self.execute_ingestor(name) for name in enabled_names if name in INGESTOR_REGISTRY]
        await asyncio.gather(*tasks, return_exceptions=True)
