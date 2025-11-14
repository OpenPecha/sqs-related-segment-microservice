from app.celery_app import celery_app
import time
import logging
from app.db.postgres import SessionLocal
from app.db.models import SegmentTask, RootJob
from datetime import datetime, timezone
from sqlalchemy import update
from app.neo4j_database import Neo4JDatabase
from uuid import uuid4

logger = logging.getLogger(__name__)

@celery_app.task(bind=True, name="process_segment_task")
def process_segment_task(self, job_id, manifestation_id: str, segment_id: str, start: int, end: int):

    try:
        job_id = str(uuid4())
    
        _create_root_job(
            job_id = job_id,
            total_segments = 4,
            manifestation_id = manifestation_id
        )

        _create_segment_tasks(
            job_id = job_id,
            segment_id = segment_id
        )

        logger.info(f"Processing segment {segment_id} for job {job_id}")

        logger.info(f"Checking if task {job_id} has completed")
        has_completed = _check_if_task_completed(job_id=job_id)
        if has_completed:
            logger.info(f"Task {job_id} has completed")
            return {
                "job_id": job_id,
                "segment_id": segment_id,
                "status": "COMPLETED"
            }

        logger.info(f"Updating root job status to IN_PROGRESS")
        _update_root_job_status(job_id=job_id)

        logger.info(f"Updating segment task record in database to IN_PROGRESS")
        _update_segment_task_record(
            job_id = job_id,
            segment_id = segment_id,
            status = "IN_PROGRESS"
        )
        logger.info(f"Connecting to Neo4J database")
        db = Neo4JDatabase()

        logger.info(f"Getting related segments from Neo4J database")
        logger.info(f"""
        Parameters for getting related segments are
        manifestation_id: {manifestation_id}
        start: {start}
        end: {end}
        """)
        related_segments = db._get_related_segments(
            manifestation_id = manifestation_id,
            start = start,
            end = end,
            transform = True
        )
        logger.info(f"Related segments: {related_segments}")
        logger.info(f"Fetched related segments from Neo4J database")

        logger.info(f"Storing related segments in database")
        
        db_response = _store_related_segments_in_db(
            job_id = job_id,
            segment_id = segment_id,
            result_json = related_segments
        )
        logger.info(f"Database response: {db_response}")
        logger.info(f"Stored related segments in database")

        logger.info(f"Updating root job count")
        _update_root_job_count(job_id=job_id)
        logger.info(f"Updated root job count")
    
        return {
            "job_id": job_id,
            "segment_id": segment_id,
            "related_segments": related_segments,
            "status": "COMPLETED"
        }
    
    except Exception as exc:
        logger.error(f"Error processing segment relationships for segment {segment_id} for job {job_id}")
        logger.error(f"Error message: {str(exc)}")
        logger.error(f"Updating segment task record in database to RETRYING")
        _update_segment_task_record(
            job_id = job_id,
            segment_id = segment_id,
            status="RETRYING",
            error_message = str(exc)
        )
        raise self.retry(exc=exc, countdown=10, max_retries=3)


def _update_segment_task_record(job_id, segment_id, status, error_message=None):
    with SessionLocal() as session:
        segment_task = session.query(SegmentTask).filter(SegmentTask.job_id == job_id, SegmentTask.segment_id == segment_id).update({
            "status": status,
            "error_message": error_message,
            "updated_at": datetime.now(timezone.utc)
        })
        session.commit()

def _store_related_segments_in_db(job_id, segment_id, result_json):
    with SessionLocal() as session:
        segment_task = session.query(SegmentTask).filter(SegmentTask.job_id == job_id, SegmentTask.segment_id == segment_id).first()
        if segment_task is None:
            logger.error(f"Segment task not found for job_id={job_id}, segment_id={segment_id}")
            return
        segment_task.result_json = result_json
        segment_task.status = "COMPLETED"
        segment_task.updated_at = datetime.now(timezone.utc)
        logger.info(f"Updated segment task record in SegmentTask table with segment id = {segment_id}")
        session.commit()

def _update_root_job_status(job_id):
    with SessionLocal() as session:
        session.execute(
            update(RootJob)
            .where(RootJob.job_id == job_id)
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
        
        session.commit()

def _check_if_task_completed(job_id):
    with SessionLocal() as session:
        task = session.query(SegmentTask).filter(SegmentTask.job_id == job_id, SegmentTask.status == "COMPLETED").first()
        return task is not None

def _create_root_job(job_id: uuid4, total_segments: int, manifestation_id: str):
    try:
        with SessionLocal() as session:
            session.add(
                RootJob(
                    job_id = job_id,
                    manifestation_id = manifestation_id,
                    total_segments = total_segments,
                    completed_segments = 0,
                    status = "QUEUED",
                    created_at = datetime.now(timezone.utc),
                    updated_at = datetime.now(timezone.utc)
                )
            )
            session.commit()

    except:
        raise Exception("Failed to create root job, Database write error")

def _create_segment_tasks(job_id: str, segment_id: str):
    try:
        with SessionLocal() as session:
            session.add(
                SegmentTask(
                    task_id = uuid4(),
                    job_id = job_id,
                    segment_id = segment_id,
                    status = "QUEUED",
                    created_at = datetime.now(timezone.utc),
                    updated_at = datetime.now(timezone.utc)
                )
            )
            session.commit()
    except Exception as e:
        raise Exception(f"Failed to create segment tasks: {str(e)}")