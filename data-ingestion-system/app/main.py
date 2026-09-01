"""app/main.py — Application entry point and CLI command handler.

Commands supported:
    python run.py                     # Start scheduler (runs continuously)
    python run.py --run-once <name>   # Execute single ingestor once and exit
    python run.py --run-all-once      # Execute all enabled ingestors once and exit
    python run.py --list-ingestors    # Print list of available ingestors and configs
    python run.py --init-db          # Initialize database tables only
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from typing import List, Optional

from app.config import get_settings
from app.database import close_db, get_session, get_scheduling_metadata, init_db
from app.ingestors import INGESTOR_REGISTRY
from app.scheduler import IngestionScheduler
from app.utils.logging import configure_logging, get_logger

logger = get_logger(__name__)


def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Haemophilia Data Ingestion and Scheduling System"
    )
    parser.add_argument(
        "--run-once",
        metavar="INGESTOR_NAME",
        help="Run a specific ingestor once and exit (e.g. pubmed, clinical_trials)",
    )
    parser.add_argument(
        "--run-all-once",
        action="store_true",
        help="Run all enabled ingestors once sequentially/concurrently and exit",
    )
    parser.add_argument(
        "--list-ingestors",
        action="store_true",
        help="List all available ingestors, enabled status, and intervals",
    )
    parser.add_argument(
        "--init-db",
        action="store_true",
        help="Initialize database tables and exit",
    )
    return parser.parse_args(args)


async def cmd_list_ingestors() -> None:
    """Print status and configuration of all registered ingestors."""
    settings = get_settings()
    enabled = set(settings.enabled_ingestors_list)

    print("\n" + "=" * 60)
    print("Registered Haemophilia Ingestors")
    print("=" * 60)
    for name, cls in INGESTOR_REGISTRY.items():
        is_en = name in enabled
        interval = settings.get_interval_minutes(name)
        status_str = "ENABLED" if is_en else "DISABLED"
        print(f"  • {name:<18} [{status_str:<8}] Interval: {interval:>6} min ({cls.display_name})")
    print("=" * 60 + "\n")


async def main(argv: Optional[List[str]] = None) -> None:
    """Main application lifecycle controller."""
    settings = get_settings()
    configure_logging(level=settings.log_level)

    args = parse_args(argv)

    if args.list_ingestors:
        await cmd_list_ingestors()
        return

    # Always ensure database schema is ready
    await init_db()

    if args.init_db:
        logger.info("Database initialization completed.")
        await close_db()
        return

    scheduler = IngestionScheduler()

    if args.run_once:
        ingestor_name = args.run_once.strip().lower()
        if ingestor_name not in INGESTOR_REGISTRY:
            print(f"Error: Unknown ingestor '{ingestor_name}'. Available: {list(INGESTOR_REGISTRY.keys())}")
            sys.exit(1)
        logger.info("Executing single ingestor run: %s", ingestor_name)
        await scheduler.execute_ingestor(ingestor_name)
        await close_db()
        return

    if args.run_all_once:
        logger.info("Executing one-off run for all enabled ingestors...")
        await scheduler.trigger_all_immediately()
        await close_db()
        return

    # Start long-running scheduler mode
    logger.info("Starting Haemophilia Data Ingestion System in background scheduler mode...")
    await scheduler.setup_jobs()
    scheduler.start()

    try:
        # Keep running until cancelled
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Shutting down scheduler...")
    finally:
        scheduler.shutdown()
        await close_db()
