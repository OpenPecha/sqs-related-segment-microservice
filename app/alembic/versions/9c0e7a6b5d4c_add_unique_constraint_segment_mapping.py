"""add_unique_constraint_segment_mapping

Revision ID: 9c0e7a6b5d4c
Revises: 794baa1751e3
Create Date: 2026-01-05

"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "9c0e7a6b5d4c"
down_revision: Union[str, None] = "794baa1751e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    if not insp.has_table("segment_mapping"):
        return

    existing = {uc.get("name") for uc in insp.get_unique_constraints("segment_mapping")}
    if "uq_segment_mapping_root_job_segment" not in existing:
        op.create_unique_constraint(
            "uq_segment_mapping_root_job_segment",
            "segment_mapping",
            ["root_job_id", "segment_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    if not insp.has_table("segment_mapping"):
        return

    existing = {uc.get("name") for uc in insp.get_unique_constraints("segment_mapping")}
    if "uq_segment_mapping_root_job_segment" in existing:
        op.drop_constraint(
            "uq_segment_mapping_root_job_segment",
            "segment_mapping",
            type_="unique",
        )


