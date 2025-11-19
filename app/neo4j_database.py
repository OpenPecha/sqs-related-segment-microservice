import queue as queue_module
import logging
from typing import override
from dotenv import load_dotenv

# Configure logger
logger = logging.getLogger(__name__)

from neo4j import GraphDatabase
from app.neo4j_database_validator import Neo4JDatabaseValidator
import os
from app.neo4j_quries import Queries
from app.redis_cache import RedisCache

load_dotenv(override=True)

# Singleton driver instance - thread-safe and reusable
_neo4j_driver = None

def get_neo4j_driver():
    """Get or create a singleton Neo4j driver instance."""
    global _neo4j_driver
    if _neo4j_driver is None:
        uri = os.environ.get("NEO4J_URI")
        user = os.environ.get("NEO4J_USER", "neo4j")  # Default to "neo4j" if not set
        password = os.environ.get("NEO4J_PASSWORD")
        logger.info(f"Creating Neo4j driver connection to {uri} with user {user}")
        _neo4j_driver = GraphDatabase.driver(uri, auth=(user, password))
        _neo4j_driver.verify_connectivity()
        logger.info("Neo4j driver connection established")
    return _neo4j_driver

class Neo4JDatabase:

    def __init__(self, neo4j_uri: str = None, neo4j_auth: tuple = None):
        # Use singleton driver for better concurrency handling
        if neo4j_uri and neo4j_auth:
            self.__driver = GraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
        else:
            self.__driver = get_neo4j_driver()
        
        self.__validator = Neo4JDatabaseValidator()
        logger.info("Neo4JDatabase instance initialized with shared driver")
    
    def get_session(self):
        """Return a new database session."""
        return self.__driver.session()

    def _get_alignment_pairs_by_manifestation(self, manifestation_id: str) -> list[dict]:
        logger.info(f"Checking cache for alignment pairs by manifestation {manifestation_id}")
        cache = RedisCache()
        cache_key = f"alignment_pairs_by_manifestation_{manifestation_id}"
        cache_result = cache.get(key=cache_key)
        if cache_result:
            logger.info(f"Cache hit for alignment pairs by manifestation {manifestation_id}")
            return cache_result
        logger.info(f"Cache miss for alignment pairs by manifestation {manifestation_id}")
        with self.get_session() as session:
            result = session.execute_read(
                lambda tx: tx.run(
                    Queries.annotations["get_alignment_pairs_by_manifestation"],
                    manifestation_id=manifestation_id
                ).data()
            )
            logger.info(f"Setting cache for alignment pairs by manifestation {manifestation_id}")
            cache.set(
                key = cache_key,
                value = result
            )
            logger.info(f"Cache set for alignment pairs by manifestation {manifestation_id}")
            return result

    def get_expression_ids_by_manifestation_ids(self, manifestation_ids: list[str]) -> dict[str, str]:
        """
        Get expression IDs for a list of manifestation IDs.
        
        Args:
            manifestation_ids: List of manifestation IDs
            
        Returns:
            Dictionary mapping manifestation_id to expression_id
        """
        if not manifestation_ids:
            return {}
        
        with self.__driver.session() as session:
            result = session.execute_read(
                lambda tx: list(tx.run(
                    Queries.manifestations["get_expression_ids_by_manifestation_ids"],
                    manifestation_ids=manifestation_ids
                ))
            )
            return {record["manifestation_id"]: record["expression_id"] for record in result}

    def _get_aligned_segments(self, alignment_1_id: str, start:int, end:int) -> list[dict]:
        with self.get_session() as session:
            result = session.execute_read(
                lambda tx: tx.run(
                    Queries.segments["get_aligned_segments"],
                    alignment_1_id=alignment_1_id,
                    span_start=start,
                    span_end=end
                ).data()
            )
            return [
                {
                    "segment_id": record["segment_id"],
                    "span": {"start": record["span_start"], "end": record["span_end"]},
                }
                for record in result
            ]

    def get_manifestation_id_by_annotation_id(self, annotation_id: str) -> str:
        logger.info(f"Checking cache for manifestation id by annotation id {annotation_id}")
        cache = RedisCache()
        cache_key = f"manifestation_id_by_annotation_id_{annotation_id}"
        cache_result = cache.get(key=cache_key)
        if cache_result:
            logger.info(f"Cache hit for manifestation id by annotation id {annotation_id}")
            return cache_result
        logger.info(f"Cache miss for manifestation id by annotation id {annotation_id}")
        with self.__driver.session() as session:
            record = session.execute_read(
                lambda tx: tx.run(Queries.manifestations["fetch_by_annotation_id"], annotation_id=annotation_id).single()
            )
            if record is None:
                return None
            d = record.data()
            logger.info(f"Setting cache for manifestation id by annotation id {annotation_id}")
            cache.set(
                key = cache_key,
                value = d["manifestation_id"]
            )
            logger.info(f"Cache set for manifestation id by annotation id {annotation_id}")
            return d["manifestation_id"]

    def _get_overlapping_segments(self, manifestation_id: str, start:int, end:int) -> list[dict]:
        with self.get_session() as session:
            result = session.execute_read(
                lambda tx: tx.run(
                    Queries.segments["get_overlapping_segments"],
                    manifestation_id=manifestation_id,
                    span_start=start,
                    span_end=end
                ).data()
            )
            return [
                {
                    "segment_id": record["segment_id"],
                    "span": {"start": record["span_start"], "end": record["span_end"]},
                }
                for record in result
            ]

    def _get_related_segments(self, manifestation_id:str, start:int, end:int, transform:bool = False) -> list[dict]:
        
        # Use local variables instead of globals to prevent race conditions
        transformed_related_segments = []
        untransformed_related_segments = []
        traversed_alignment_pairs = []
        visited_manifestations = set()  # Track visited manifestations to prevent infinite loops

        queue = queue_module.Queue()
        queue.put({"manifestation_id": manifestation_id, "span_start": start, "span_end": end})
        visited_manifestations.add(manifestation_id)  # Mark initial manifestation as visited
        
        logger.info(f"Starting BFS traversal from manifestation {manifestation_id}")
        
        while not queue.empty():
            item = queue.get()  # get() removes and returns the item (like pop())
            manifestation_1_id = item["manifestation_id"]
            span_start = item["span_start"]
            span_end = item["span_end"]
            
            alignment_list = self._get_alignment_pairs_by_manifestation(manifestation_1_id)
            logger.info(f"Found {len(alignment_list)} alignment pair(s) for manifestation {manifestation_1_id}")
            
            for alignment in alignment_list:
                if (alignment["alignment_1_id"], alignment["alignment_2_id"]) not in traversed_alignment_pairs:
                    segments_list = self._get_aligned_segments(alignment["alignment_1_id"], span_start, span_end)
                    
                    # Skip if no segments found
                    if not segments_list:
                        logger.info("No aligned segments found, skipping")
                        continue
                    
                    overall_start = min(segments_list, key=lambda x: x["span"]["start"])["span"]["start"]
                    overall_end = max(segments_list, key=lambda x: x["span"]["end"])["span"]["end"]
                    manifestation_2_id = self.get_manifestation_id_by_annotation_id(alignment["alignment_2_id"])
                    logger.info(f"Target manifestation: {manifestation_2_id}, overall span=[{overall_start}, {overall_end})")
                    
                    # Skip if manifestation already visited (prevents infinite loops)
                    if manifestation_2_id in visited_manifestations:
                        logger.info(f"Manifestation {manifestation_2_id} already visited, skipping")
                        continue
                    
                    visited_manifestations.add(manifestation_2_id)
                    
                    if transform:
                        transformed_segments = self._get_overlapping_segments(manifestation_2_id, overall_start, overall_end)
                        logger.info(f"Found {len(transformed_segments)} transformed segment(s) for manifestation {manifestation_2_id}")
                        transformed_related_segments.append({"manifestation_id": manifestation_2_id, "segments": transformed_segments})
                    else:
                        logger.info(f"Using untransformed segments for manifestation {manifestation_2_id}")
                        untransformed_related_segments.append({"manifestation_id": manifestation_2_id, "segments": segments_list})
                    traversed_alignment_pairs.append((alignment["alignment_1_id"], alignment["alignment_2_id"]))
                    traversed_alignment_pairs.append((alignment["alignment_2_id"], alignment["alignment_1_id"]))
                    queue.put({"manifestation_id": manifestation_2_id, "span_start": overall_start, "span_end": overall_end})

        if transform:
            logger.info(f"Transformed related segments: \n{transformed_related_segments}")
            return transformed_related_segments
        else:
            return untransformed_related_segments

    def get_segments_by_manifestation(self, manifestation_id: str) -> list[dict]:
        """
        Get all segments from segmentation or pagination annotation for a manifestation.
        
        Args:
            manifestation_id: The manifestation ID
            
        Returns:
            List of dictionaries containing segment_id, span_start, and span_end
        """
        with self.get_session() as session:
            result = session.execute_read(
                lambda tx: list(tx.run(
                    Queries.segments["get_segments_by_manifestation"],
                    manifestation_id=manifestation_id
                ))
            )
            return [dict(record) for record in result]