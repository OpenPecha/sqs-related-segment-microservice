# SQS Segment Mapping Calculator — Documentation

## Introduction

The SQS Segment Mapping Calculator is the core processing service in the pipeline. It consumes messages from the first SQS queue, computes related segment mappings using Neo4j (including graph traversal logic), stores results in PostgreSQL, updates job progress, and publishes completion messages to a second SQS queue.

This service performs the main computation step and supports asynchronous, scalable processing.

---

## 1. Service Overview

**Role in pipeline:** The calculator sits between two SQS queues. It reads batch messages from the first (input) queue, runs the segment-mapping computation, persists results and job state in PostgreSQL, then notifies the next stage by sending to the second (completed) queue.

**End-to-end responsibility:**

1. Parse the incoming SQS message (batch of segments for one job).
2. For each segment in the batch: run Neo4j BFS to compute related segments across manifestations.
3. Upsert each segment’s mapping into the `segment_mapping` table.
4. Update the root job’s `completed_segments` and set status to `IN_PROGRESS` or `COMPLETED` as appropriate.
5. Send one completion message to Queue #2 for the batch.

**Pipeline position:** First queue (input) → this service (compute) → second queue (completion).

---

## 2. SQS Consumption Flow

### Consumer setup

- **Implementation:** `SimpleConsumer` in `app/main.py`, extending `aws_sqs_consumer.Consumer`.
- **Configuration:** `queue_url` from `SQS_QUEUE_URL`, `region` from `AWS_REGION`, `polling_wait_time_ms=50`.
- **Entry point:** Run with `python -m app.main`; the process calls `consumer.start()` and polls the queue.

### Message parsing

- The handler parses the body as JSON: `json.loads(message.Body)`.
- **Required fields:**
  - `root_job_id` — UUID of the root job.
  - `text_id` — Manifestation/text identifier (used as Neo4j manifestation id).
  - `batch_number` — Batch index (passed through; used for context).
  - `total_segments` — Total number of segments for the job.
  - `segments` — List of segment objects, each with `segment_id` and `span`: `{ "start", "end" }`.
  - `source_environment` — Environment label for Neo4j/config (e.g. `DEVELOPMENT`, `PRODUCTION`).
  - `destination_environment` — Target environment label.

### Incoming message schema (Queue #1)

| Field | Type | Description |
|-------|------|-------------|
| `root_job_id` | string (UUID) | Root job identifier. |
| `text_id` | string | Manifestation ID for Neo4j and storage. |
| `batch_number` | number | Batch index. |
| `total_segments` | number | Total segments in the job. |
| `segments` | array | List of `{ "segment_id": string, "span": { "start": number, "end": number } }`. |
| `source_environment` | string | Source environment (e.g. DEVELOPMENT, PRODUCTION). |
| `destination_environment` | string | Destination environment. |

**Sample (Queue #1):**

```json
{
  "root_job_id": "550e8400-e29b-41d4-a716-446655440000",
  "text_id": "manifestation-uuid-123",
  "batch_number": 1,
  "total_segments": 10,
  "segments": [
    { "segment_id": "seg-1", "span": { "start": 0, "end": 100 } },
    { "segment_id": "seg-2", "span": { "start": 100, "end": 200 } }
  ],
  "source_environment": "DEVELOPMENT",
  "destination_environment": "PRODUCTION"
}
```

### Task execution flow

1. The consumer’s `handle_message` extracts the fields above and calls `process_segment_task(...)` in `app/tasks.py`.
2. There is no per-segment “claim” step in code; each SQS message represents a batch. The handler processes every segment in the batch, then performs one job progress update and sends one completion message to Queue #2.
3. For each segment: Neo4j `_get_related_segments(text_id, span_start, span_end, transform=True)` is called, then `_store_related_segments_in_db` upserts the result. After all segments, `_update_root_job_status` is called with the batch size, then `send_completed_mapping_text_to_sqs_service` is invoked once.

---

## 3. Relation Calculation Logic

### Neo4j traversal (BFS)

- **Location:** `_get_related_segments` in `app/neo4j_database.py`.
- **Input:** One `manifestation_id` (the `text_id`) and a span `(start, end)`.
- **Algorithm:** Breadth-first search over the graph of manifestations connected by alignment annotations:
  - A queue is used; the initial item is `{ manifestation_id, span_start, span_end }`.
  - For each dequeued item: get alignment pairs for that manifestation (Cypher in `app/neo4j_quries.py`: Manifestation → ANNOTATION_OF → Annotation with type `alignment` → ALIGNED_TO to another annotation).
  - For each alignment pair not yet traversed: get aligned segments for that alignment and span (`get_aligned_segments`), compute the overall span of those segments, and resolve the other manifestation via `get_manifestation_id_by_annotation_id`.
  - `visited_manifestations` and `traversed_alignment_pairs` are kept to avoid cycles and duplicate edges.
  - The other manifestation is enqueued with the computed span for the next level of BFS.

### Transform option

- When `transform=True` (as used by `app/tasks.py`), for each reached manifestation the service fetches **overlapping segments** on that manifestation (Cypher `get_overlapping_segments`) and returns those as the mapping for that manifestation.
- When `transform=False`, the aligned segments from the alignment query are returned as-is.

### Segment mapping output

- The result is a list of objects: `{ "manifestation_id": str, "segments": [ { "segment_id", "span": { "start", "end" } } ] }`.
- This list is the “segment mapping” for one source segment and is stored in PostgreSQL in `SegmentMapping.result_json`.

---

## 4. Database Operations

### Storing segment_mapping

- **Function:** `_store_related_segments_in_db` in `app/tasks.py`.
- **Mechanism:** SQLAlchemy `insert(SegmentMapping).values(...).on_conflict_do_update(index_elements=[SegmentMapping.root_job_id, SegmentMapping.segment_id], set_={ result_json, status, updated_at })`.
- This uses PostgreSQL `INSERT ... ON CONFLICT` on the unique constraint `uq_segment_mapping_root_job_segment` on `(root_job_id, segment_id)` (see `app/db/models.py`).
- One row per segment; the mapping list is stored in `result_json`; `status` is set to `COMPLETED`.

### Upsert / idempotency strategy

- Re-processing the same batch or segment overwrites `result_json` and `status` for that `(root_job_id, segment_id)`. Duplicate messages or retries do not create duplicate rows and produce consistent results.

### Job status and progress updates

- **Function:** `_update_root_job_status(job_id, inc=total_segments)` in `app/tasks.py`.
- **Behavior:** Updates `RootJob`: adds `inc` to `completed_segments`, sets `status` to `COMPLETED` when `completed_segments >= total_segments`, or to `IN_PROGRESS` when the job was `QUEUED` and now has progress. The update is conditional: `WHERE status != 'COMPLETED'`, so completed jobs are not overwritten.

---

## 5. Queue #2 Publishing

- **When:** After all segments in the batch are processed and the root job’s `completed_segments` (and status) have been updated, `app/tasks.py` calls `send_completed_mapping_text_to_sqs_service(...)` once per batch.
- **Purpose:** Notify downstream that mapping for the given text and the listed segment IDs has been completed for this batch, so the next stage (e.g. aggregation, export, or another service) can proceed.

---

## 6. Queue #2 Payload

### Message schema

The body is a single JSON object with:

| Field | Type | Description |
|-------|------|-------------|
| `text_id` | string | Manifestation/text identifier. |
| `segment_ids` | array of string | Segment IDs processed in this batch. |
| `total_segments` | number | Total segments for the job. |
| `source_environment` | string | Source environment (e.g. DEVELOPMENT, PRODUCTION). |
| `destination_environment` | string | Destination environment. |

### Sample JSON (Queue #2)

```json
{
  "text_id": "manifestation-uuid-123",
  "segment_ids": ["seg-1", "seg-2"],
  "total_segments": 10,
  "source_environment": "DEVELOPMENT",
  "destination_environment": "PRODUCTION"
}
```

---

## 7. Reliability Concerns

### Retries

- Retry behavior is not configured in this repo; it comes from the `aws-sqs-consumer` library and/or AWS SQS (e.g. visibility timeout, redrive, dead-letter queue). The application does not implement its own retry loop for task processing.

### Visibility timeout

- Not set in application code. Configure the SQS input queue in AWS with an appropriate visibility timeout (e.g. 60+ seconds as recommended in the README) so that if a worker fails mid-processing, the message becomes visible again for another worker.

### Multi-worker and concurrency

- One consumer process per process; scaling is by running multiple processes (e.g. multiple instances on Render or multiple `python -m app.main`). There is no in-repo concurrency limit.
- **Idempotency:** The segment_mapping upsert on `(root_job_id, segment_id)` and the job update restricted to `status != 'COMPLETED'` avoid corrupting results when the same batch is processed more than once. Duplicate completion messages to Queue #2 can still occur if a batch is processed twice; downstream consumers should be idempotent if required.

---

## 8. Error Handling, Logging, Config & Libraries

### Error handling

- Exceptions in `process_segment_task` are re-raised; there is no in-task retry. The SQS send in `app/sqs_service.py` catches exceptions, logs with `logger.error`, and re-raises. Failed processing typically results in the message returning to the queue (or moving to a DLQ) according to SQS and consumer behavior.
- The `SegmentMapping` model has `status` (including `RETRYING`, `FAILED`) and `error_message`; the current success path only sets `COMPLETED` and does not populate failure status in this code path.

### Logging

- Standard library `logging` is used. `logging.basicConfig` is set in `app/main.py` (level INFO, format with timestamp, name, level, message). Module-level loggers are used in `main`, `tasks`, `neo4j_database`, and `sqs_service` for INFO (flow) and ERROR (e.g. send failure).

### Config

- **File:** `app/config.py`; `load_dotenv()` loads `.env`. A `Config` dict is populated from the environment; `get(key)` returns values.
- **Variables:** Neo4j (`NEO4J_USER`, `DEVELOPMENT_NEO4J_URI`, `DEVELOPMENT_NEO4J_PASSWORD`, `PRODUCTION_NEO4J_URI`, `PRODUCTION_NEO4J_PASSWORD`), `POSTGRES_URL`, AWS (`AWS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`), `SQS_QUEUE_URL`, `SQS_COMPLETED_QUEUE_URL`. The Neo4j driver also resolves `{source.upper()}_NEO4J_URI` and `{source.upper()}_NEO4J_PASSWORD` (e.g. from `env.example`).

### Libraries

- From `requirements.txt`: `pydantic`, `sqlalchemy`, `alembic`, `psycopg2-binary`, `neo4j`, `python-dotenv`, `boto3`, `aws-sqs-consumer==0.0.15`. No separate logging framework.

---