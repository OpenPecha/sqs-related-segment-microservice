from fastapi import APIRouter, HTTPException

from app.models import (
    SegmentsRelationRequest, 
    AllTextSegmentRelationMapping,
    SegmentsRelation,
    Mapping,
    SegmentWithSpan,
    SegmentationResponse,
    Span
)
from app.db.postgres import SessionLocal
from app.db.models import RootJob, SegmentTask
from app.neo4j_database import Neo4JDatabase
from datetime import datetime, timezone
from uuid import uuid4
from app.config import get
import json
import logging

import boto3

relation = APIRouter(
    prefix="/relation",
    tags=["Segments Relation"]
)

logger = logging.getLogger(__name__)

# Initialize SQS client with proper configuration
sqs_client = boto3.client(
    'sqs',
    region_name=get('AWS_REGION'),
    aws_access_key_id=get('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=get('AWS_SECRET_ACCESS_KEY')
)

@relation.get("/{job_id}/status")
def get_job_status(job_id: str):
    try:
        with SessionLocal() as session:
            job = session.query(RootJob).filter(RootJob.job_id == job_id).first()
            if not job:
                raise HTTPException(status_code=404, detail="Job not found")
            
            return job
    except:
        raise HTTPException(status_code=500, detail="Failed to get job status, Database read error")

@relation.get("/{manifestation_id}/all-relations")
def get_all_segments_relation_by_manifestation(manifestation_id: str):
    try:
        with SessionLocal() as session:
            root_job = session.query(RootJob).filter(RootJob.manifestation_id == manifestation_id).first()
            if root_job.completed_segments < root_job.total_segments:
                raise HTTPException(status_code=400, detail="Job not completed")
            
            all_text_segment_relations = session.query(SegmentTask).filter(SegmentTask.job_id == root_job.job_id).all()

            response = _format_all_text_segment_relation_mapping(
                manifestation_id = manifestation_id,
                all_text_segment_relations = all_text_segment_relations
            )
            return response
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to get all segments relation by manifestation, Database read error, Error: " + str(e))

def _format_all_text_segment_relation_mapping(manifestation_id: str, all_text_segment_relations):
    response = AllTextSegmentRelationMapping(
        manifestation_id = manifestation_id,
        segments = []
    )
    for task in all_text_segment_relations:
        task_dict = {
            "task_id": str(task.task_id),
            "job_id": str(task.job_id),
            "segment_id": task.segment_id,
            "status": task.status,
            "result_json": task.result_json,
            "result_location": task.result_location,
            "error_message": task.error_message,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "updated_at": task.updated_at.isoformat() if task.updated_at else None
        }
        logger.info("Starting with formatting task: ", task_dict)
        segment = SegmentsRelation(
            segment_id = task.segment_id,
            mappings = []
        )
        for mapping in task_dict["result_json"]:
            mapping_dict = Mapping(
                manifestation_id = mapping["manifestation_id"],
                segments = mapping["segments"]
            )
            segment.mappings.append(mapping_dict)
        logger.info("Segment: ", segment)
        response.segments.append(segment)
    logger.info("Response: ", response)
    return response

def get_all_segmentation(manifestation_id: str) -> SegmentationResponse:
    """Helper function to get all segments from segmentation/pagination annotation"""
    try:
        db = Neo4JDatabase()
        segments_data = db.get_segments_by_manifestation(manifestation_id)
        
        if not segments_data:
            raise HTTPException(
                status_code=404, 
                detail="Segmentation or pagination annotation not available for this manifestation"
            )
        
        segments = [
            SegmentWithSpan(
                segment_id=seg["segment_id"],
                span=Span(start=seg["span_start"], end=seg["span_end"])
            )
            for seg in segments_data
        ]
        
        return SegmentationResponse(
            manifestation_id=manifestation_id,
            segments=segments
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting segments: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@relation.post("/{manifestation_id}")
def get_all_segments_relation_by_manifestation_id(manifestation_id: str):
    try:
        # Get all segments from the manifestation
        all_segments = get_all_segmentation(manifestation_id=manifestation_id)
        
        # Convert SegmentationResponse to SegmentsRelationRequest
        from app.models import Segments
        segments_list = [
            Segments(
                segment_id=seg.segment_id,
                span=seg.span
            )
            for seg in all_segments.segments
        ]
        
        request = SegmentsRelationRequest(
            manifestation_id=manifestation_id,
            segments=segments_list
        )
        
        # Process the segments relation
        response = get_segments_relation(request=request)
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_all_segments_relation_by_manifestation_id: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get all segments relation by manifestation, Error: {str(e)}")

def get_segments_relation(request: SegmentsRelationRequest):

    job_id = str(uuid4())

    _create_root_job(
        job_id = job_id,
        total_segments = len(request.segments),
        manifestation_id = request.manifestation_id
    )

    # Create segment task records
    _create_segment_tasks(
        job_id = job_id,
        segments = request.segments
    )

    dispatched_count = 0
    for segment in request.segments:
        message_body = {
            "job_id": job_id,
            "manifestation_id": request.manifestation_id,
            "segment_id": segment.segment_id,
            "start": segment.span.start,
            "end": segment.span.end
        }
        
        response = sqs_client.send_message(
            QueueUrl=get("SQS_QUEUE_URL"),
            MessageBody=json.dumps(message_body),
        )
        dispatched_count += 1
        print(f"Dispatched task {dispatched_count} to SQS for segment {segment.segment_id}, MessageId: {response['MessageId']}")

    return {
        "job_id": job_id,
        "status": "QUEUED",
        "message": f"Segments relation job created successfully. Dispatched {dispatched_count} tasks."
    }


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
        raise HTTPException(status_code=500, detail="Failed to create root job, Database write error")

def _create_segment_tasks(job_id: str, segments: list):
    try:
        with SessionLocal() as session:
            for segment in segments:
                session.add(
                    SegmentTask(
                        task_id = uuid4(),
                        job_id = job_id,
                        segment_id = segment.segment_id,
                        status = "QUEUED",
                        created_at = datetime.now(timezone.utc),
                        updated_at = datetime.now(timezone.utc)
                    )
                )
            session.commit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create segment tasks: {str(e)}")