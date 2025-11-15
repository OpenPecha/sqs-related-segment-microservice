class Queries:
    pass

Queries.annotations = {
    "get_alignment_pairs_by_manifestation": """
MATCH (m:Manifestation {id: $manifestation_id})
MATCH (m)<-[:ANNOTATION_OF]-(a1:Annotation)-[:HAS_TYPE]->(:AnnotationType {name: 'alignment'})
MATCH (a1)-[:ALIGNED_TO]-(a2:Annotation)
WITH a1, a2, m.id as manifestation_id

RETURN manifestation_id, a1.id as alignment_1_id, a2.id as alignment_2_id
""",
}

Queries.manifestations = {
    "get_expression_ids_by_manifestation_ids": """
MATCH (m:Manifestation)-[:MANIFESTATION_OF]->(e:Expression)
WHERE m.id IN $manifestation_ids
RETURN m.id as manifestation_id, e.id as expression_id
""",
    "fetch_by_annotation_id": """
MATCH (a:Annotation {id: $annotation_id})-[:ANNOTATION_OF]->(m:Manifestation)
RETURN m.id AS manifestation_id
""",
}

Queries.segments = {
    "get_aligned_segments": """
MATCH (a1:Annotation {id: $alignment_1_id})<-[:SEGMENTATION_OF]-(s1:Segment)
WHERE s1.span_start < $span_end AND s1.span_end > $span_start
MATCH (s1)-[:ALIGNED_TO]-(s2:Segment)
RETURN DISTINCT s2.id as segment_id,
       s2.span_start as span_start,
       s2.span_end as span_end
ORDER BY s2.span_start
""",
    "get_overlapping_segments": """
MATCH (m:Manifestation {id: $manifestation_id})<-[:ANNOTATION_OF]-(ann:Annotation)-[:HAS_TYPE]->(:AnnotationType {name: 'segmentation'})
MATCH (ann)<-[:SEGMENTATION_OF]-(s:Segment)
WHERE s.span_start < $span_end AND s.span_end > $span_start
RETURN s.id as segment_id,
       s.span_start as span_start,
       s.span_end as span_end
ORDER BY s.span_start
""",
    "get_segments_by_manifestation": """
MATCH (m:Manifestation {id: $manifestation_id})<-[:ANNOTATION_OF]-(ann:Annotation)-[:HAS_TYPE]->(at:AnnotationType)
WHERE at.name IN ['segmentation', 'pagination']
MATCH (ann)<-[:SEGMENTATION_OF]-(s:Segment)
RETURN s.id as segment_id,
       s.span_start as span_start,
       s.span_end as span_end
ORDER BY s.span_start
"""
}
