"""Store the latest classification for each ingested item."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002_classifications"
down_revision: Union[str, None] = "001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "classifications",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("raw_item_id", sa.String(length=36), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=True),
        sa.Column("justification", sa.Text(), nullable=True),
        sa.Column("method", sa.String(length=20), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="classified"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("classified_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["raw_item_id"], ["raw_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("raw_item_id", name="uq_classifications_raw_item_id"),
    )
    op.create_index("ix_classifications_raw_item_id", "classifications", ["raw_item_id"])
    op.create_index("ix_classifications_category", "classifications", ["category"])
    op.create_index("ix_classifications_status", "classifications", ["status"])


def downgrade() -> None:
    op.drop_index("ix_classifications_status", table_name="classifications")
    op.drop_index("ix_classifications_category", table_name="classifications")
    op.drop_index("ix_classifications_raw_item_id", table_name="classifications")
    op.drop_table("classifications")