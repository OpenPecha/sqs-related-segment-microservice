import os
from dotenv import load_dotenv

# Load .env file from project root
load_dotenv()

Config = {
    "NEO4J_USER": os.getenv('NEO4J_USER', None),

    "DEVELOPMENT_NEO4J_URI": os.getenv('NEO4J_URI', None),
    "DEVELOPMENT_NEO4J_PASSWORD": os.getenv('NEO4J_PASSWORD', None),
    
    "PRODUCTION_NEO4J_URI": os.getenv('PRODUCTION_NEO4J_URI', None),
    "PRODUCTION_NEO4J_PASSWORD": os.getenv('PRODUCTION_NEO4J_PASSWORD', None),
    
    "POSTGRES_URL": os.getenv('POSTGRES_URL', 'postgresql://admin:pechaAdmin@localhost:5435/pecha'),
    
    # AWS SQS Configuration
    "AWS_REGION": os.getenv('AWS_REGION', 'us-east-1'),
    "AWS_ACCESS_KEY_ID": os.getenv('AWS_ACCESS_KEY_ID', None),
    "AWS_SECRET_ACCESS_KEY": os.getenv('AWS_SECRET_ACCESS_KEY', None),
    "SQS_QUEUE_URL": os.getenv('SQS_QUEUE_URL', None),

    "SQS_COMPLETED_QUEUE_URL": os.getenv('SQS_COMPLETED_QUEUE_URL', None),
}


def get(key: str, default=None):
    return Config.get(key, default)