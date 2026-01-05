"""align_segment_mapping_to_models

Revision ID: 70f379be1cec
Revises: b4587305f484
Create Date: 2026-01-05 14:42:17.763446

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = '70f379be1cec'
down_revision: Union[str, None] = 'b4587305f484'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Align DB schema to current SQLAlchemy models in app/db/models.py:

    SegmentMapping model expects:
      - table: segment_mapping
      - columns: task_id, root_job_id (FK->root_jobs.job_id), text_id, segment_id,
                 status, result_json, error_message, created_at, updated_at

    Current DB has:
      - table: segment_tasks
      - columns: task_id, job_id, segment_id, status, result_json, result_location,
                 error_message, created_at, updated_at
    """
    bind = op.get_bind()
    insp = inspect(bind)

    has_tasks = insp.has_table("segment_tasks")
    has_mapping = insp.has_table("segment_mapping")

    if has_tasks and not has_mapping:
        op.rename_table("segment_tasks", "segment_mapping")

    if not insp.has_table("segment_mapping"):
        # Nothing else to do (or DB is in unexpected state)
        return

    cols = {c["name"] for c in insp.get_columns("segment_mapping")}

    # job_id -> root_job_id
    if "job_id" in cols and "root_job_id" not in cols:
        op.alter_column("segment_mapping", "job_id", new_column_name="root_job_id")
        cols = {c["name"] for c in insp.get_columns("segment_mapping")}

    # Add optional text_id
    if "text_id" not in cols:
        op.add_column("segment_mapping", sa.Column("text_id", sa.Text(), nullable=True))
        cols = {c["name"] for c in insp.get_columns("segment_mapping")}

    # Drop result_location (not in models)
    if "result_location" in cols:
        op.drop_column("segment_mapping", "result_location")

    # Fix FK constraint to point at root_job_id (the old constraint name persists across rename)
    constraint_names = {c["name"] for c in insp.get_foreign_keys("segment_mapping")}
    if "segment_tasks_job_id_fkey" in constraint_names:
        op.drop_constraint("segment_tasks_job_id_fkey", "segment_mapping", type_="foreignkey")
    if "segment_mapping_root_job_id_fkey" not in constraint_names:
        op.create_foreign_key(
            "segment_mapping_root_job_id_fkey",
            "segment_mapping",
            "root_jobs",
            ["root_job_id"],
            ["job_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    if not insp.has_table("segment_mapping"):
        return

    cols = {c["name"] for c in insp.get_columns("segment_mapping")}

    # Drop new FK, restore old FK name (best-effort)
    fk_names = {c["name"] for c in insp.get_foreign_keys("segment_mapping")}
    if "segment_mapping_root_job_id_fkey" in fk_names:
        op.drop_constraint("segment_mapping_root_job_id_fkey", "segment_mapping", type_="foreignkey")

    # Re-add result_location
    if "result_location" not in cols:
        op.add_column("segment_mapping", sa.Column("result_location", sa.Text(), nullable=True))

    # Drop text_id
    cols = {c["name"] for c in insp.get_columns("segment_mapping")}
    if "text_id" in cols:
        op.drop_column("segment_mapping", "text_id")

    # root_job_id -> job_id
    cols = {c["name"] for c in insp.get_columns("segment_mapping")}
    if "root_job_id" in cols and "job_id" not in cols:
        op.alter_column("segment_mapping", "root_job_id", new_column_name="job_id")

    # Restore old FK name if possible
    fk_names = {c["name"] for c in insp.get_foreign_keys("segment_mapping")}
    if "segment_tasks_job_id_fkey" not in fk_names:
        op.create_foreign_key(
            "segment_tasks_job_id_fkey",
            "segment_mapping",
            "root_jobs",
            ["job_id"],
            ["job_id"],
        )

    # Rename back to segment_tasks
    if insp.has_table("segment_mapping") and not insp.has_table("segment_tasks"):
        op.rename_table("segment_mapping", "segment_tasks")
