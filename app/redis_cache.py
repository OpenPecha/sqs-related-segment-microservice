import redis
import json
import logging
from app.config import get


logger = logging.getLogger(__name__)

_dragonfly_client = None

def get_dragonfly_client():
    global _dragonfly_client
    if _dragonfly_client is None:
        try:
            dragonfly_url = get("DRAGONFLY_URL")
            if not dragonfly_url:
                logger.warning("DRAGONFLY_URL is not set in the environment variables")
                return None
            
            _dragonfly_client = redis.from_url(
                dragonfly_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=60
            )
            _dragonfly_client.ping()
            logger.info("Dragonfly connection established")
        except Exception as e:
            logger.warning(f"Failed to connect to Dragonfly: {e}")
            _dragonfly_client = None
    return _dragonfly_client


class DragonflyCache:

    def __init__(self, default_ttl: int = 3600):
        """
        Initialize Dragonfly cache.
        
        Args:
            default_ttl: Default time-to-live in seconds (default: 1 hour)
        """
        self.client = get_dragonfly_client()
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
            logger.warning(f"Failed to get value from Dragonfly: {e}")
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
            logger.warning(f"Dragonfly SET error for key {key}: {e}")
            return False
    
