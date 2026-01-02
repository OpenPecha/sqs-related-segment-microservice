import logging
import json
from app.db.postgres import SessionLocal
from app.db.models import SegmentTask, RootJob
from datetime import datetime, timezone
from sqlalchemy import update, insert, case
from app.neo4j_database import Neo4JDatabase
from dotenv import load_dotenv
import boto3
from app.config import get
from app.sqs_service import (
    send_completed_mapping_text_to_sqs_service
)

# Configure logger
logger = logging.getLogger(__name__)

# Load environment variables FIRST
load_dotenv(override=True)

# Initialize SQS client AFTER loading env vars
sqs_client = boto3.client(
    'sqs',
    region_name=get('AWS_REGION'),
    aws_access_key_id=get('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=get('AWS_SECRET_ACCESS_KEY')
)
    

def process_segment_task(
    root_job_id,
    text_id: str,
    batch_number: int,
    total_segments: int,
    segments: list[dict]
):

    try:

        db = Neo4JDatabase()

        for segment in segments:
            span_start = segment['span']['start']
            span_end = segment['span']['end']
            related_segments = db._get_related_segments(
                manifestation_id=text_id,
                start=span_start,
                end=span_end,
                transform=True
            )

            _store_related_segments_in_db(
                job_id=root_job_id,
                segment_id=segment['segment_id'],
                result_json=related_segments
            )

        _update_root_job_status(
            job_id=root_job_id,
            inc=total_segments
        )

        segment_ids = [segment['segment_id'] for segment in segments]
        send_completed_mapping_text_to_sqs_service(
            text_id=text_id,
            segment_ids=segment_ids,
            total_segments=total_segments
        )

        return {
            "root_job_id": root_job_id,
            "text_id": text_id,
            "status": "COMPLETED"
        }

    except Exception as exc:
        raise exc


def _store_related_segments_in_db(job_id: str, segment_id: str, result_json: dict):
    try:
        now = datetime.now(timezone.utc)

        stmt = insert(SegmentTask).values(
            job_id=job_id,
            segment_id=segment_id,
            result_json=result_json,
            status="COMPLETED",
            updated_at=now,
            created_at=now,   # include if you have it
        ).on_conflict_do_update(
            index_elements=[SegmentTask.job_id, SegmentTask.segment_id],
            set_={
                "result_json": result_json,     # overwrite
                "status": "COMPLETED",
                "updated_at": now,
            }
        ).returning(SegmentTask)  # Postgres only

        with SessionLocal() as session:
            row = session.execute(stmt).scalar_one()  # Postgres: returns the row
            session.commit()
            return row
    except Exception as error:
        raise error


def _update_root_job_status(job_id, inc: int = 1):
    now = datetime.now(timezone.utc)
    new_completed = RootJob.completed_segments + inc

    with SessionLocal() as session:
        stmt = (
            update(RootJob)
            .where(
                RootJob.job_id == job_id,
                RootJob.status != "COMPLETED",
            )
            .values(
                completed_segments=new_completed,
                status=case(
                    (new_completed >= RootJob.total_segments, "COMPLETED"),
                    (RootJob.status == "QUEUED", "IN_PROGRESS"),
                    else_=RootJob.status,
                ),
                updated_at=now,
            )
            .returning(RootJob.status, RootJob.text_id)
        )

        row = session.execute(stmt).one_or_none()
        session.commit()
