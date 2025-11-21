import logging
import json
from app.db.postgres import SessionLocal
from app.db.models import SegmentTask, RootJob
from datetime import datetime, timezone
from sqlalchemy import update
from app.neo4j_database import Neo4JDatabase
from dotenv import load_dotenv
import boto3
from app.config import get

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
    job_id,
    manifestation_id: str,
    segment_id: str,
    start: int,
    end: int
):

    try:
        logger.info(f"Processing segment {segment_id} for job {job_id}")

        logger.info(f"Attempting to claim segment task {segment_id}")
        if not _try_claim_segment_task(job_id=job_id, segment_id=segment_id):
            logger.warning(
                f"Segment {segment_id} already claimed. Skipping."
            )
            raise Exception(f"Segment {segment_id} already claimed. Skipping.")

        logger.info(
            f"Successfully claimed segment task {segment_id}"
        )
        
        logger.info("Updating root job status to IN_PROGRESS (if currently QUEUED)")
        _update_root_job_status(job_id=job_id)

        logger.info("Connecting to Neo4J database")
        db = Neo4JDatabase()

        logger.info("Getting related segments from Neo4J database")
        logger.info(f"""
        Parameters for getting related segments are
        manifestation_id: {manifestation_id}
        start: {start}
        end: {end}
        """)
        related_segments = db._get_related_segments(
            manifestation_id=manifestation_id,
            start=start,
            end=end,
            transform=True
        )
        logger.info(f"Related segments: {related_segments}")
        logger.info("Fetched related segments from Neo4J database")

        logger.info("Storing related segments in database")

        db_response = _store_related_segments_in_db(
            job_id=job_id,
            segment_id=segment_id,
            result_json=related_segments
        )
        logger.info(f"Database response: {db_response}")
        logger.info("Stored related segments in database")

        logger.info("Updating root job count")
        _update_root_job_count(job_id=job_id)
        logger.info("Updated root job count")

        return {
            "job_id": job_id,
            "segment_id": segment_id,
            "related_segments": related_segments,
            "status": "COMPLETED"
        }

    except Exception as exc:
        logger.error(f"Error processing segment relationships for segment {segment_id} for job {job_id}")
        logger.error(f"Error message: {str(exc)}")
        logger.error("Updating segment task record in database to RETRYING")
        _update_segment_task_record(
            job_id=job_id,
            segment_id=segment_id,
            status="RETRYING",
            error_message=str(exc)
        )
        raise exc


def _try_claim_segment_task(job_id, segment_id):
    """
    Atomically claim a segment task by updating from QUEUED to IN_PROGRESS.
    Returns True if successfully claimed, False if already claimed by another worker.
    """
    with SessionLocal() as session:
        result = session.query(SegmentTask).filter(
            SegmentTask.job_id == job_id, 
            SegmentTask.segment_id == segment_id,
            SegmentTask.status == "QUEUED"  # Only update if status is QUEUED
        ).update({
            "status": "IN_PROGRESS",
            "updated_at": datetime.now(timezone.utc)
        })
        session.commit()
        return result > 0  # True if we updated a row (claimed it), False otherwise


def _update_segment_task_record(job_id, segment_id, status, error_message=None):
    with SessionLocal() as session:
        result = session.query(SegmentTask).filter(
            SegmentTask.job_id == job_id, 
            SegmentTask.segment_id == segment_id
        ).update({
            "status": status,
            "error_message": error_message,
            "updated_at": datetime.now(timezone.utc)
        })
        session.commit()
        return result  # Returns number of rows affected


def _store_related_segments_in_db(job_id, segment_id, result_json):
    with SessionLocal() as session:
        segment_task = session.query(SegmentTask).filter(
            SegmentTask.job_id == job_id,
            SegmentTask.segment_id == segment_id
        ).first()
        if segment_task is None:
            logger.error(f"Segment task not found for job_id={job_id}, segment_id={segment_id}")
            return
        segment_task.result_json = result_json
        segment_task.status = "COMPLETED"
        segment_task.updated_at = datetime.now(timezone.utc)
        logger.info(f"Updated segment task record in SegmentTask table with segment id = {segment_id}")
        session.commit()

        return segment_task


def _update_root_job_status(job_id):
    """Update root job status to IN_PROGRESS only if it's currently QUEUED"""
    with SessionLocal() as session:
        session.execute(
            update(RootJob)
            .where(RootJob.job_id == job_id, RootJob.status == "QUEUED")
            .values(status="IN_PROGRESS", updated_at=datetime.now(timezone.utc))
        )
        session.commit()


def _update_root_job_count(job_id):
    with SessionLocal() as session:
        # Increment and fetch in one transaction
        root = session.execute(
            update(RootJob)
            .where(RootJob.job_id == job_id)
            .values(
                completed_segments=RootJob.completed_segments + 1,
                updated_at=datetime.now(timezone.utc)
            )
            .returning(RootJob)
        ).scalar_one()

        # Check completion in same transaction
        if root.completed_segments >= root.total_segments:
            root.status = "COMPLETED"
            root.updated_at = datetime.now(timezone.utc)

            # Send completion message to SQS
            try:
                queue_url = get('SQS_COMPLETED_QUEUE_URL')
                if not queue_url:
                    logger.error(f"SQS_COMPLETED_QUEUE_URL not configured! Cannot send completion message for job {job_id}")
                else:
                    message_body = {
                        "job_id": job_id,
                        "manifestation_id": root.manifestation_id
                    }
                    logger.info(f"Sending completion message to SQS for job {job_id}: {message_body}")
                    
                    response = sqs_client.send_message(
                        QueueUrl=queue_url,
                        MessageBody=json.dumps(message_body)
                    )
                    
                    logger.info(f"✅ Successfully sent message to completed queue. MessageId: {response.get('MessageId')}")
            except Exception as sqs_error:
                logger.error(f"❌ Failed to send completion message to SQS for job {job_id}: {str(sqs_error)}")
                # Don't raise - we don't want SQS errors to rollback the database transaction
        
        session.commit()
