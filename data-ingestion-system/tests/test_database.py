"""tests/test_database.py — Database schema and CRUD operation tests."""
from __future__ import annotations

from datetime import datetime, timezone
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import (
    IngestorLogModel,
    RawItemModel,
    SchedulingMetadataModel,
    get_last_cursor,
    get_scheduling_metadata,
    store_ingestor_log,
    upsert_raw_item,
    upsert_scheduling_metadata,
)


@pytest.mark.asyncio
async def test_upsert_raw_item_insert_and_update(test_session: AsyncSession):
    """Test that upsert_raw_item correctly inserts a new item and updates on duplicate."""
    # 1. Insert new item
    is_new = await upsert_raw_item(
        session=test_session,
        source_name="ClinicalTrials.gov",
        source_id="NCT01234567",
        source_url="https://clinicaltrials.gov/study/NCT01234567",
        title="Initial Study Title",
        raw_content="Brief initial summary",
        date_published=datetime(2023, 1, 1, tzinfo=timezone.utc),
        metadata={"phase": "PHASE3"},
    )
    await test_session.commit()
    assert is_new is True

    # Verify stored
    stmt = select(RawItemModel).where(
        RawItemModel.source_name == "ClinicalTrials.gov",
        RawItemModel.source_id == "NCT01234567",
    )
    result = await test_session.execute(stmt)
    item = result.scalar_one_or_none()
    assert item is not None
    assert item.title == "Initial Study Title"
    assert item.metadata_dict == {"phase": "PHASE3"}
    assert item.is_active is True

    # 2. Update existing item with new content (idempotency)
    is_new_again = await upsert_raw_item(
        session=test_session,
        source_name="ClinicalTrials.gov",
        source_id="NCT01234567",
        source_url="https://clinicaltrials.gov/study/NCT01234567",
        title="Updated Study Title",
        raw_content="Updated detailed content",
        date_published=datetime(2023, 1, 1, tzinfo=timezone.utc),
        metadata={"phase": "PHASE3", "status": "COMPLETED"},
    )
    await test_session.commit()
    assert is_new_again is False

    # Verify updated in-place without creating duplicate
    all_items = (await test_session.execute(stmt)).scalars().all()
    assert len(all_items) == 1
    assert all_items[0].title == "Updated Study Title"
    assert all_items[0].metadata_dict["status"] == "COMPLETED"


@pytest.mark.asyncio
async def test_store_ingestor_log(test_session: AsyncSession):
    """Test storing and querying ingestor audit logs."""
    log = IngestorLogModel(
        ingestor_name="pubmed",
        run_timestamp=datetime.now(timezone.utc),
        items_fetched=100,
        items_stored=95,
        items_skipped=5,
        success=True,
        last_cursor="MCID_123|1|100",
        duration_seconds=3.5,
    )
    await store_ingestor_log(test_session, log)
    await test_session.commit()

    stmt = select(IngestorLogModel).where(IngestorLogModel.ingestor_name == "pubmed")
    result = await test_session.execute(stmt)
    saved_log = result.scalar_one_or_none()

    assert saved_log is not None
    assert saved_log.items_fetched == 100
    assert saved_log.items_stored == 95
    assert saved_log.success is True


@pytest.mark.asyncio
async def test_scheduling_metadata_crud(test_session: AsyncSession):
    """Test creating and updating scheduling metadata."""
    meta = await upsert_scheduling_metadata(
        session=test_session,
        ingestor_name="arxiv",
        run_interval_minutes=1440,
        is_enabled=True,
        last_cursor="50",
    )
    await test_session.commit()
    assert meta.ingestor_name == "arxiv"
    assert meta.run_interval_minutes == 1440

    # Retrieve cursor
    cursor = await get_last_cursor(test_session, "arxiv")
    assert cursor == "50"

    # Update metadata
    await upsert_scheduling_metadata(
        session=test_session,
        ingestor_name="arxiv",
        last_cursor="100",
        consecutive_failures=0,
    )
    await test_session.commit()

    updated_cursor = await get_last_cursor(test_session, "arxiv")
    assert updated_cursor == "100"
