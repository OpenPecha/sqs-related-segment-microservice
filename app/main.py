import json
import logging
from aws_sqs_consumer import Consumer, Message
from app.tasks import process_segment_task
from app.config import get


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger(__name__)

queue_url = get("SQS_QUEUE_URL")


class SimpleConsumer(Consumer):
    """
    Simple consumer for the SQS queue.
    """
    def handle_message(self, message: Message):
        json_content = json.loads(message.Body)

        root_job_id = json_content['root_job_id']
        text_id = json_content['text_id']
        batch_number = json_content['batch_number']
        total_segments = json_content['total_segments']
        segments = json_content['segments']

        segment_relations = process_segment_task(
            root_job_id=root_job_id,
            text_id=text_id,
            batch_number=int(batch_number),
            total_segments=int(total_segments),
            segments=list(segments)
        )
        logger.info("Segment relations: %s", segment_relations)


consumer = SimpleConsumer(
    queue_url=queue_url,
    region=get("AWS_REGION"),
    polling_wait_time_ms=50
)

if __name__ == "__main__":
    logger.info("Starting SQS consumer...")
    consumer.start()
