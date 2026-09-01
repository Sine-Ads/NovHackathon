"""tests/conftest.py — Pytest fixtures for async database and mock services."""
from __future__ import annotations

import os
from typing import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

TEST_DB_PATH = "./test_haemophilia.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH}"
os.environ["LOG_LEVEL"] = "DEBUG"
os.environ["API_RATE_LIMIT_DELAY_MS"] = "0"
os.environ["ERROR_RETRY_MAX_ATTEMPTS"] = "1"
os.environ["USPTO_API_KEY"] = "test_uspto_key"

from app.database import Base, close_db, get_engine, get_session, init_db


@pytest_asyncio.fixture(autouse=True)
async def setup_test_database() -> AsyncIterator[None]:
    """Ensure database schema is created before every test and cleaned up after."""
    await init_db()
    yield
    # We keep the engine open during tests, clean up rows between tests
    async with get_session() as session:
        for table in reversed(Base.metadata.sorted_tables):
            await session.execute(table.delete())


@pytest_asyncio.fixture
async def test_session() -> AsyncIterator[AsyncSession]:
    """Provide a database session for test execution."""
    async with get_session() as session:
        yield session
