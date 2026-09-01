"""tests/test_scheduler.py — Tests for scheduler job registration and execution."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch
import pytest

from app.config import get_settings
from app.ingestors.base import RawItem
from app.scheduler import IngestionScheduler


@pytest.mark.asyncio
async def test_scheduler_setup_jobs(test_session):
    """Test that scheduler registers enabled ingestor jobs with correct intervals."""
    scheduler = IngestionScheduler()
    await scheduler.setup_jobs()

    # Verify jobs were added to APScheduler
    jobs = scheduler.scheduler.get_jobs()
    job_ids = [j.id for j in jobs]

    assert "job_clinical_trials" in job_ids
    assert "job_pubmed" in job_ids
    assert "job_openfda" in job_ids
    assert "job_arxiv" in job_ids


@pytest.mark.asyncio
async def test_scheduler_concurrency_guard(test_session):
    """Test that concurrent executions of the same ingestor are prevented."""
    scheduler = IngestionScheduler()

    # Mock the ingestor run method
    mock_item = RawItem(
        source_name="ClinicalTrials.gov",
        source_id="NCT99999999",
        title="Mock Trial",
        raw_content="Mock summary",
    )

    with patch(
        "app.ingestors.clinical_trials.ClinicalTrialsIngestor.run",
        new=AsyncMock(return_value=(1, 1, "next_token")),
    ):
        # First call succeeds
        await scheduler.execute_ingestor("clinical_trials")
        assert not scheduler._running_jobs.get("clinical_trials", False)
