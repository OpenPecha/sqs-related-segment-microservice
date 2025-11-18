from aws_sqs_consumer import Consumer, Message
from app.tasks import process_segment_task
from app.config import get
import json
import logging

logger = logging.getLogger(__name__)

queue_url = get("SQS_QUEUE_URL")

class SimpleConsumer(Consumer):
    def handle_message(self, message: Message):
        json_content = json.loads(message.Body)
        
        manifestation_id = json_content['manifestation_id']
        job_id = json_content['job_id']
        segment_id = json_content['segment_id']
        start = int(json_content['start'])
        end = int(json_content['end'])

        segment_relations = process_segment_task(
            job_id = job_id,
            manifestation_id = manifestation_id,
            segment_id = segment_id,
            start = start,
            end = end
        )
        print("Segment relations:", segment_relations)

consumer = SimpleConsumer(
    queue_url=queue_url,
    region=get("AWS_REGION"),
    polling_wait_time_ms=50
)

if __name__ == "__main__":
    logger.info("Starting SQS consumer...")
    consumer.start()