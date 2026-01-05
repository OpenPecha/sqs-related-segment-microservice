"""fix_segment_mapping_columns

Revision ID: 794baa1751e3
Revises: 70f379be1cec
Create Date: 2026-01-05 14:43:24.228339

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = '794baa1751e3'
down_revision: Union[str, None] = '70f379be1cec'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    if not insp.has_table("segment_mapping"):
        return

    cols = {c["name"] for c in insp.get_columns("segment_mapping")}

    # Rename FK column to match models
    if "job_id" in cols and "root_job_id" not in cols:
        op.alter_column("segment_mapping", "job_id", new_column_name="root_job_id")

    # Add optional text_id column
    cols = {c["name"] for c in inspect(bind).get_columns("segment_mapping")}
    if "text_id" not in cols:
        op.add_column("segment_mapping", sa.Column("text_id", sa.Text(), nullable=True))

    # Drop result_location (not in models)
    cols = {c["name"] for c in inspect(bind).get_columns("segment_mapping")}
    if "result_location" in cols:
        op.drop_column("segment_mapping", "result_location")

    # Fix FK constraint name + columns (drop legacy constraint name if present)
    fks = inspect(bind).get_foreign_keys("segment_mapping")
    fk_names = {fk["name"] for fk in fks}
    if "segment_tasks_job_id_fkey" in fk_names:
        op.drop_constraint("segment_tasks_job_id_fkey", "segment_mapping", type_="foreignkey")
    if "segment_mapping_root_job_id_fkey" not in fk_names:
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

    fks = insp.get_foreign_keys("segment_mapping")
    fk_names = {fk["name"] for fk in fks}
    if "segment_mapping_root_job_id_fkey" in fk_names:
        op.drop_constraint("segment_mapping_root_job_id_fkey", "segment_mapping", type_="foreignkey")

    cols = {c["name"] for c in insp.get_columns("segment_mapping")}
    if "result_location" not in cols:
        op.add_column("segment_mapping", sa.Column("result_location", sa.Text(), nullable=True))

    cols = {c["name"] for c in inspect(bind).get_columns("segment_mapping")}
    if "text_id" in cols:
        op.drop_column("segment_mapping", "text_id")

    cols = {c["name"] for c in inspect(bind).get_columns("segment_mapping")}
    if "root_job_id" in cols and "job_id" not in cols:
        op.alter_column("segment_mapping", "root_job_id", new_column_name="job_id")

    # restore legacy FK name (best-effort)
    fks = inspect(bind).get_foreign_keys("segment_mapping")
    fk_names = {fk["name"] for fk in fks}
    if "segment_tasks_job_id_fkey" not in fk_names:
        op.create_foreign_key(
            "segment_tasks_job_id_fkey",
            "segment_mapping",
            "root_jobs",
            ["job_id"],
            ["job_id"],
        )
