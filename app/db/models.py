from app.db.postgres import Base
from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from uuid import uuid4


class RootJob(Base):
    __tablename__ = "root_jobs"

    job_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    text_id = Column(Text, nullable=False)
    total_segments = Column(Integer, nullable=False)
    completed_segments = Column(Integer, nullable=False, default=0)
    status = Column(
        String(20),
        CheckConstraint(
            "status IN ('QUEUED','IN_PROGRESS','COMPLETED','FAILED')",
            name="root_job_status_check"
        ),
        nullable=False
    )
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    segment_mappings = relationship(
        "SegmentMapping",
        back_populates="root_job",
        cascade="all, delete-orphan"
    )


class SegmentMapping(Base):
    __tablename__ = "segment_mapping"
    __table_args__ = (
        UniqueConstraint(
            "root_job_id",
            "segment_id",
            name="uq_segment_mapping_root_job_segment",
        ),
    )

    task_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    root_job_id = Column(
        UUID(as_uuid=True),
        ForeignKey("root_jobs.job_id"),
        nullable=False
    )
    text_id = Column(
        Text
    )
    segment_id = Column(Text, nullable=False)
    status = Column(
        String(20),
        CheckConstraint(
            "status IN ('QUEUED','IN_PROGRESS','COMPLETED','FAILED','"
            "RETRYING')",
            name="segment_task_status_check"
        ),
        nullable=False
    )
    result_json = Column(JSONB, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    root_job = relationship("RootJob", back_populates="segment_mappings")
