# SQS Microservice - Segment Relationship Processor

A production-ready microservice that consumes messages from AWS SQS, processes segment relationships using Neo4j graph database, and stores results in PostgreSQL. Built for high-throughput processing with support for multiple concurrent workers.

## 🌟 Features

- **AWS SQS Consumer**: Reliable message consumption with automatic retry and error handling
- **Multi-Worker Support**: Race condition protection for concurrent processing
- **Atomic Task Claiming**: Prevents duplicate processing across multiple workers
- **Dragonfly Cache**: High-performance caching for Neo4j alignment queries
- **Graph Database Integration**: Neo4j for complex relationship traversal (BFS algorithm)
- **PostgreSQL Storage**: Persistent storage of job status and results
- **Structured Logging**: Production-ready logging with proper log levels
- **Database Migrations**: Alembic integration for schema management
- **Error Recovery**: Automatic retry mechanism with error tracking

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────┐
│            SQS Consumer Workers                 │
│  (Multiple instances supported with atomic      │
│   task claiming to prevent duplicates)          │
├─────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────┐  │
│  │  1. Receive message from SQS             │  │
│  │  2. Atomically claim task (QUEUED→       │  │
│  │     IN_PROGRESS)                         │  │
│  │  3. Query Neo4j for related segments     │  │
│  │  4. Store results in PostgreSQL          │  │
│  │  5. Update job completion status         │  │
│  │  6. Send completion message to SQS       │  │
│  └──────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
          │                           │
          ▼                           ▼
    ┌──────────┐               ┌──────────┐
    │ AWS SQS  │               │  Neo4j   │
    │  Queue   │               │ Database │
    └──────────┘               └──────────┘
          │                           
          ▼                           
    ┌──────────┐               
    │PostgreSQL│               
    │ Database │               
    └──────────┘               
```

## 🚀 Quick Start

### Prerequisites

- Python 3.12+
- AWS Account with SQS access
- PostgreSQL database
- Neo4j database (cloud or self-hosted)

### Installation

1. **Clone the repository**
```bash
git clone <repository-url>
cd sqs-microservice
```

2. **Create virtual environment**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Configure environment**
```bash
cp env.example .env
# Edit .env with your credentials
```

5. **Run database migrations**
```bash
alembic upgrade head
```

6. **Start the consumer**
```bash
python -m app.main
```

## 📝 Configuration

### Environment Variables

Create a `.env` file with the following variables:

```env
# Neo4j Database
NEO4J_URI=neo4j+s://xxx.databases.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-password

# PostgreSQL Database
POSTGRES_URL=postgresql://user:password@host:5432/database

# AWS Configuration
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key

# SQS Queues
SQS_QUEUE_URL=https://sqs.region.amazonaws.com/account/queue-name
SQS_COMPLETED_QUEUE_URL=https://sqs.region.amazonaws.com/account/completed-queue

# Dragonfly Cache (Optional - improves performance)
DRAGONFLY_URL=redis://default:password@your-instance.dragonflydb.cloud:6379
```

See `env.example` for a complete template.

## 🔄 How It Works

### Message Flow

1. **Message Reception**: Worker receives a message from SQS containing:
   ```json
   {
     "job_id": "uuid",
     "manifestation_id": "string",
     "segment_id": "string",
     "start": 0,
     "end": 100
   }
   ```

2. **Atomic Task Claiming**: Worker attempts to claim the task by updating status from `QUEUED` to `IN_PROGRESS`. If another worker already claimed it, this worker skips processing.

3. **Relationship Processing**: Worker queries Neo4j to find all related segments using BFS traversal through alignment pairs.

4. **Result Storage**: Worker stores the related segments in PostgreSQL with the segment task record.

5. **Job Completion**: When all segments are processed, a completion message is sent to the completed queue.

### Race Condition Protection

The microservice uses **atomic task claiming** to prevent duplicate processing:

```python
# Only updates if status is currently "QUEUED"
UPDATE segment_task 
SET status = 'IN_PROGRESS' 
WHERE job_id = ? AND segment_id = ? AND status = 'QUEUED'
```

This ensures that even with multiple workers consuming from the same queue, each segment is processed exactly once.

## 📊 Database Schema

### RootJob Table
```sql
- job_id (UUID, PK)
- manifestation_id (String)
- total_segments (Integer)
- completed_segments (Integer)
- status (Enum: QUEUED, IN_PROGRESS, COMPLETED, FAILED)
- created_at (Timestamp)
- updated_at (Timestamp)
```

### SegmentTask Table
```sql
- task_id (UUID, PK)
- job_id (UUID, FK)
- segment_id (String)
- status (Enum: QUEUED, IN_PROGRESS, COMPLETED, RETRYING, FAILED)
- result_json (JSONB) - Stores related segments
- result_location (String, optional)
- error_message (Text, nullable)
- created_at (Timestamp)
- updated_at (Timestamp)
```

## 🚢 Deployment

### Render (Background Worker)

1. **Create a new Background Worker** on Render
2. **Environment**: Select `Python 3`
3. **Build Command**: `pip install -r requirements.txt`
4. **Start Command**: `python -m app.main`
5. **Add environment variables** from your `.env` file
6. **Deploy**: Render will automatically deploy when you push to main branch

**Important**: Create a `runtime.txt` file to specify Python version:
```
python-3.12.8
```

### Running Multiple Workers

To scale processing, deploy multiple instances:

**On Render:**
- Increase the number of instances in the service settings
- Each instance will automatically claim tasks atomically

**Locally:**
```bash
# Terminal 1
python -m app.main

# Terminal 2
python -m app.main

# Terminal 3
python -m app.main
```

All workers will consume from the same queue without duplicating work.

## 📁 Project Structure

```
sqs-microservice/
├── app/
│   ├── main.py                 # SQS consumer entry point
│   ├── tasks.py                # Task processing logic
│   ├── relation.py             # API endpoints (optional)
│   ├── config.py               # Configuration management
│   ├── models.py               # Pydantic models
│   ├── neo4j_database.py       # Neo4j integration
│   ├── neo4j_quries.py         # Cypher queries
│   ├── neo4j_database_validator.py
│   ├── alembic/                # Database migrations
│   │   └── versions/
│   ├── alembic.ini
│   └── db/
│       ├── postgres.py         # PostgreSQL connection
│       └── models.py           # SQLAlchemy models
├── requirements.txt            # Python dependencies
├── runtime.txt                 # Python version for deployment
├── env.example                 # Environment template
├── purge_sqs.py               # Utility to purge SQS queue
└── README.md
```

## 🔧 Key Components

### 1. SQS Consumer (`app/main.py`)

The main consumer that polls SQS and processes messages:

```python
consumer = SimpleConsumer(
    queue_url=queue_url,
    region=get("AWS_REGION"),
    polling_wait_time_ms=50
)
consumer.start()
```

### 2. Task Processor (`app/tasks.py`)

Handles the business logic:
- Atomic task claiming
- Neo4j relationship queries
- Result storage
- Error handling and retries

### 3. Neo4j Database (`app/neo4j_database.py`)

Graph database operations:
- BFS traversal for related segments
- Alignment pair queries
- Segment overlap detection

### 4. Database Models (`app/db/models.py`)

SQLAlchemy models for job and task tracking.

## 🐛 Troubleshooting

### Consumer Not Starting

```bash
# Check environment variables
python -c "from app.config import get; print(get('SQS_QUEUE_URL'))"

# Test AWS credentials
aws sqs get-queue-attributes --queue-url <YOUR_QUEUE_URL>
```

### Database Connection Issues

```bash
# Test PostgreSQL
python -c "from app.db.postgres import engine; engine.connect(); print('✓ PostgreSQL connected')"

# Test Neo4j
python -c "from app.neo4j_database import Neo4JDatabase; db = Neo4JDatabase(); print('✓ Neo4j connected')"
```

### No Messages Being Processed

1. Check SQS queue has messages: `aws sqs get-queue-attributes --queue-url <URL> --attribute-names ApproximateNumberOfMessages`
2. Verify visibility timeout is appropriate (recommended: 60+ seconds)
3. Check worker logs for errors

### Duplicate Processing

If you see duplicate processing even with multiple workers:
1. Ensure all workers are using the same database
2. Check that `_try_claim_segment_task` is being called before processing
3. Verify database transactions are properly committed

## 📊 Monitoring

### Logging

The application uses structured logging:

```
2025-11-18 10:30:45 - app.tasks - INFO - Processing segment ABC123 for job 550e8400
2025-11-18 10:30:45 - app.tasks - INFO - Attempting to claim segment task ABC123
2025-11-18 10:30:45 - app.tasks - INFO - Successfully claimed segment task ABC123
2025-11-18 10:30:46 - app.neo4j_database - INFO - Starting BFS traversal from manifestation XYZ
```

### Job Status

Query the database to check job progress:

```sql
SELECT 
    job_id,
    manifestation_id,
    completed_segments,
    total_segments,
    status,
    updated_at
FROM root_job
WHERE status = 'IN_PROGRESS'
ORDER BY updated_at DESC;
```

## 🧪 Testing

### Utility Scripts

**Purge SQS Queue** (for testing):
```bash
python purge_sqs.py
```

### Manual Testing

1. Send a test message to SQS
2. Check logs for processing
3. Query database for results

## 🔐 Security Best Practices

- ✅ Never commit `.env` file
- ✅ Use IAM roles instead of access keys (when on AWS)
- ✅ Rotate credentials regularly
- ✅ Use connection pooling for database connections
- ✅ Set appropriate SQS visibility timeouts
- ✅ Monitor failed message dead letter queues

## ⚡ Performance Tips

1. **Adjust Polling Wait Time**: Increase `polling_wait_time_ms` to reduce API calls
2. **Database Connection Pooling**: Already configured in PostgreSQL connection
3. **Neo4j Connection Reuse**: Singleton driver pattern implemented
4. **Multiple Workers**: Scale horizontally for high throughput
5. **SQS Batch Size**: Consumer handles messages one at a time for reliable processing

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

[Add your license here]

## 📞 Support

For issues or questions:
1. Check the troubleshooting section
2. Review application logs
3. Check database records for task status
4. Open an issue on GitHub

---

**Built with Python, AWS SQS, PostgreSQL, and Neo4j** 🚀
