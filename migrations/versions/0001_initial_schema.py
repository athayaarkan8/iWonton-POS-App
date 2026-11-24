"""Create Wonton POS schema when tables do not exist; preserve existing data.

Revision ID: 0001_initial
Revises:
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from app import db
from app import models  # register model metadata

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    # Add missing tables without dropping or recreating existing tables.
    db.metadata.create_all(bind=bind, checkfirst=True)

    # Stage 6/older Stage 7 databases may not yet contain this Stage 7 column.
    inspector = inspect(bind)
    if "user" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("user")}
        if "is_active" not in columns:
            op.add_column(
                "user",
                sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            )


def downgrade():
    # Intentionally non-destructive: this baseline must never drop POS data.
    pass
