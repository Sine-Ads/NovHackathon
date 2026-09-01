"""001 Initial Schema for Haemophilia Data Ingestion.

Revision ID: 001_initial_schema
Revises: None
Create Date: 2026-09-02 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. raw_items table
    op.create_table(
        "raw_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_name", sa.String(length=100), nullable=False),
        sa.Column("source_id", sa.String(length=500), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("raw_content", sa.Text(), nullable=True),
        sa.Column("date_published", sa.DateTime(timezone=True), nullable=True),
        sa.Column("date_ingested", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_name", "source_id", name="uq_source_name_source_id"),
    )
    op.create_index("ix_raw_items_source_name", "raw_items", ["source_name"])
    op.create_index("ix_raw_items_date_ingested", "raw_items", ["date_ingested"])
    op.create_index("ix_raw_items_source_url", "raw_items", ["source_url"])

    # 2. ingestor_logs table
    op.create_table(
        "ingestor_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ingestor_name", sa.String(length=100), nullable=False),
        sa.Column("run_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("items_fetched", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("items_stored", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("items_skipped", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("last_cursor", sa.Text(), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ingestor_logs_ingestor_name", "ingestor_logs", ["ingestor_name"])

    # 3. scheduling_metadata table
    op.create_table(
        "scheduling_metadata",
        sa.Column("ingestor_name", sa.String(length=100), nullable=False),
        sa.Column("last_run_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_scheduled_run", sa.DateTime(timezone=True), nullable=True),
        sa.Column("run_interval_minutes", sa.Integer(), nullable=False, server_default=sa.text("1440")),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("last_cursor", sa.Text(), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.PrimaryKeyConstraint("ingestor_name"),
    )


def downgrade() -> None:
    op.drop_table("scheduling_metadata")
    op.drop_table("ingestor_logs")
    op.drop_index("ix_raw_items_source_url", table_name="raw_items")
    op.drop_index("ix_raw_items_date_ingested", table_name="raw_items")
    op.drop_index("ix_raw_items_source_name", table_name="raw_items")
    op.drop_table("raw_items")
