import redis
import json
import logging
from app.config import get


logger = logging.getLogger(__name__)

_redis_client = None

def get_redis_client():
    global _redis_client
    if _redis_client is None:
        try:
            redis_url = get("REDIS_URL")
            if not redis_url:
                logger.warning("REDIS_URL is not set in the environment variables")
                return None
            
            _redis_client = redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=60
            )
            _redis_client.ping()
            logger.info("Redis connection established")
        except Exception as e:
            logger.warning(f"Failed to connect to Redis: {e}")
            _redis_client = None
    return _redis_client


class RedisCache:

    def __init__(self, default_ttl: int = 3600):
        self.client = get_redis_client()
        self.default_ttl = default_ttl

    def get(self, key: str):
        if not self.client:
            return None
        try:
            value = self.client.get(key)
            if value:
                logger.debug(f"Cache HIT: {key}")
                return json.loads(value)
            logger.debug(f"Cache MISS: {key}")
            return None
        except Exception as e:
            logger.warning(f"Failed to get value from Redis: {e}")
            return None
        
    def set(self, key: str, value: str, ttl: int = None):
        if not self.client:
            return False
        try:
            ttl = ttl or self.default_ttl
            serialized = json.dumps(value)
            self.client.setex(key, ttl, serialized)
            logger.debug(f"Cache SET: {key} (TTL: {ttl}s)")
            return True

        except Exception as e:
            logger.warning(f"REdis SET error for key {key}: {e}")
            return False
    
