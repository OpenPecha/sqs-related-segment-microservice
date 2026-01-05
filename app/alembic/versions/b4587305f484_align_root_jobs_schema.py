"""align_root_jobs_schema

Revision ID: b4587305f484
Revises: 7cc11efc6c3f
Create Date: 2026-01-05 14:37:40.290525

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b4587305f484'
down_revision: Union[str, None] = '7cc11efc6c3f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Make the database schema match current SQLAlchemy models.

    NOTE: Some environments have the Alembic version stamped without the
    corresponding tables existing. This migration is defensive:
    - If tables don't exist, it creates them.
    - If tables exist with legacy columns, it renames/drops to align.
    """
    bind = op.get_bind()
    insp = inspect(bind)

    # --- root_jobs ---
    if not insp.has_table("root_jobs"):
        op.create_table(
            "root_jobs",
            sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("text_id", sa.Text(), nullable=False),
            sa.Column("total_segments", sa.Integer(), nullable=False),
            sa.Column("completed_segments", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.CheckConstraint(
                "status IN ('QUEUED','IN_PROGRESS','COMPLETED','FAILED')",
                name="root_job_status_check",
            ),
            sa.PrimaryKeyConstraint("job_id"),
        )
    else:
        cols = {c["name"] for c in insp.get_columns("root_jobs")}
        # legacy: manifestation_id -> text_id
        if "manifestation_id" in cols and "text_id" not in cols:
            op.alter_column("root_jobs", "manifestation_id", new_column_name="text_id")
        # legacy: merged_result_location removed
        cols = {c["name"] for c in insp.get_columns("root_jobs")}
        if "merged_result_location" in cols:
            op.drop_column("root_jobs", "merged_result_location")

    # --- segment_tasks ---
    if not insp.has_table("segment_tasks"):
        op.create_table(
            "segment_tasks",
            sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("segment_id", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("result_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("result_location", sa.Text(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.CheckConstraint(
                "status IN ('QUEUED','IN_PROGRESS','COMPLETED','FAILED','RETRYING')",
                name="segment_task_status_check",
            ),
            sa.ForeignKeyConstraint(["job_id"], ["root_jobs.job_id"]),
            sa.PrimaryKeyConstraint("task_id"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    if insp.has_table("segment_tasks"):
        op.drop_table("segment_tasks")

    if insp.has_table("root_jobs"):
        cols = {c["name"] for c in insp.get_columns("root_jobs")}
        if "merged_result_location" not in cols:
            op.add_column("root_jobs", sa.Column("merged_result_location", sa.Text(), nullable=True))
        cols = {c["name"] for c in insp.get_columns("root_jobs")}
        if "text_id" in cols and "manifestation_id" not in cols:
            op.alter_column("root_jobs", "text_id", new_column_name="manifestation_id")
