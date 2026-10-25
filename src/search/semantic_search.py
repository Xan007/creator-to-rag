"""Semantic Vector Search Engine for Creator RAG Posts.

Provides dense semantic vector search via Gemini embeddings & Pinecone,
with graceful fallback to SQLite BM25/FTS5 lexical search.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import or_
from sqlalchemy.orm import Session

from storage.models import Post
from src.rag.query_engine import QueryEngine
from src.search.query_parser import parse_search_query

logger = logging.getLogger(__name__)


import re

def _extract_topic(knowledge: Optional[str], fallback: str = "") -> str:
    if not knowledge:
        return fallback
    m = re.search(r"##\s*Topic\s*[:\n\- ]*([^\n#]+)", knowledge, re.IGNORECASE)
    if m:
        topic = m.group(1).strip().strip('"\'').rstrip(".").lstrip("#* ")
        if topic:
            return topic
    return fallback


def search_posts_semantic(
    query_text: str,
    db: Session,
    creator: Optional[str] = None,
    library_id: Optional[str] = None,
    unlinked_only: bool = False,
    top_k: int = 200,
) -> List[Tuple[Post, float]]:
    """Search posts semantically using vector embeddings and Pinecone.
    
    Returns a list of tuples (Post, similarity_score) sorted by score descending.
    """
    if not query_text or not query_text.strip():
        return []

    parsed = parse_search_query(query_text)

    # Extract filter tokens if present in query
    effective_creator = creator
    if not effective_creator and parsed.authors:
        effective_creator = parsed.authors[0]

    effective_unlinked = unlinked_only
    if parsed.is_linked is False:
        effective_unlinked = True

    # Use parsed positive terms or original query text
    clean_query = " ".join(parsed.positive_terms) if parsed.positive_terms else query_text.strip()
    if not clean_query:
        clean_query = query_text.strip()

    # Step 1: Embed query text via QueryEngine
    qe = QueryEngine()
    query_vector = qe._get_embedding(clean_query)

    post_scores: Dict[str, float] = {}

    if query_vector and qe.index:
        try:
            res = qe.index.query(
                vector=query_vector,
                top_k=top_k,
                include_metadata=True,
            )
            matches = res.get("matches", [])
            for m in matches:
                meta = m.get("metadata", {}) or {}
                pid = meta.get("post_id") or meta.get("source_id")
                if not pid and ":" in m.get("id", ""):
                    parts = m["id"].split(":")
                    if len(parts) >= 3:
                        pid = parts[-2]
                    else:
                        pid = parts[-1]
                if pid:
                    score = float(m.get("score") or 0.0)
                    if pid not in post_scores or score > post_scores[pid]:
                        post_scores[pid] = score
        except Exception as e:
            logger.warning("Pinecone semantic query failed: %s", e)

    # Step 2: If Pinecone returned results, fetch and filter from DB (strictly indexed with topic)
    if post_scores:
        q = db.query(Post).filter(
            Post.id.in_(list(post_scores.keys())),
        )

        if effective_creator:
            q = q.filter(Post.creator_username.ilike(f"%{effective_creator}%"))
        if effective_unlinked:
            q = q.filter(or_(Post.library_id == None, Post.library_id == ""))
        elif library_id:
            q = q.filter(Post.library_id == library_id)

        posts = q.all()
        results: List[Tuple[Post, float]] = []
        for p in posts:
            p.title = _extract_topic(p.extracted_knowledge, p.title)
            score = post_scores.get(p.id, 0.0)
            results.append((p, score))

        # Sort descending by similarity score
        results.sort(key=lambda x: x[1], reverse=True)
        return results

    # Step 3: Fallback if Pinecone unavailable or 0 matches
    logger.info("Semantic search fallback to lexical search for: %s", clean_query)
    from src.search.query_parser import apply_search_filters

    q = db.query(Post)
    if effective_creator:
        q = q.filter(Post.creator_username.ilike(f"%{effective_creator}%"))
    if effective_unlinked:
        q = q.filter(or_(Post.library_id == None, Post.library_id == ""))
    elif library_id:
        q = q.filter(Post.library_id == library_id)

    q = apply_search_filters(q, clean_query, Post)
    posts = q.limit(top_k).all()
    for p in posts:
        p.title = _extract_topic(p.extracted_knowledge, p.title)
    return [(p, 0.50) for p in posts]
