"""Persistent lexical retrieval.

SQLite uses FTS5 so the corpus is indexed once and queried in the database.
Other SQL backends use a bounded LIKE fallback until a native full-text
backend is configured.
"""

import re
import time
from collections import OrderedDict
from typing import Any, Dict, List

from sqlalchemy import text

from storage.db import get_session


def _fts_query(query: str) -> str:
    terms = re.findall(r"[\wÀ-ÿ]+", query.lower())
    return " AND ".join(f'"{term.replace(chr(34), "")}"' for term in terms[:16])


class LexicalRetriever:
    _cache: "OrderedDict[tuple, tuple[float, List[Dict[str, Any]]]]" = OrderedDict()
    _cache_ttl = 30.0
    _cache_size = 256

    def retrieve(self, query: str, library_id: str, top_k: int = 12) -> List[Dict[str, Any]]:
        if not query.strip() or not library_id:
            return []
        key = (query.strip().lower(), library_id, top_k)
        cached = self._cache.get(key)
        if cached and time.monotonic() - cached[0] < self._cache_ttl:
            return [dict(item) for item in cached[1]]
        db = get_session()
        try:
            if db.bind.dialect.name == "sqlite":
                expression = _fts_query(query)
                if not expression:
                    return []
                rows = db.execute(
                    text(
                        "SELECT chunk_id, text, title, author, description, url, bm25(chunks_fts) AS rank "
                        "FROM chunks_fts WHERE chunks_fts MATCH :query AND library_id = :library_id "
                        "ORDER BY rank LIMIT :limit"
                    ),
                    {"query": expression, "library_id": library_id, "limit": top_k},
                ).mappings().all()
                result = [
                    self._match(row["chunk_id"], row, float(1.0 / (1.0 + abs(row["rank"] or 0.0))))
                    for row in rows
                ]
                self._remember(key, result)
                return result

            if db.bind.dialect.name == "postgresql":
                rows = db.execute(
                    text(
                        "SELECT c.id AS chunk_id, c.text, s.title, s.author, s.description, s.url, "
                        "ts_rank_cd(to_tsvector('simple', concat_ws(' ', c.text, s.title, s.author, s.description)), "
                        "plainto_tsquery('simple', :query)) AS rank "
                        "FROM chunks c JOIN sources s ON s.id = c.source_id "
                        "JOIN library_sources ls ON ls.source_id = c.source_id "
                        "WHERE ls.library_id = :library_id "
                        "AND to_tsvector('simple', concat_ws(' ', c.text, s.title, s.author, s.description)) "
                        "@@ plainto_tsquery('simple', :query) "
                        "ORDER BY rank DESC LIMIT :limit"
                    ),
                    {"query": query, "library_id": library_id, "limit": top_k},
                ).mappings().all()
                result = [self._match(row["chunk_id"], row, float(row["rank"] or 0.0)) for row in rows]
                self._remember(key, result)
                return result

            # Safe bounded fallback for other development databases.
            pattern = f"%{query.strip()[:120]}%"
            rows = db.execute(
                text(
                    "SELECT c.id AS chunk_id, c.text, s.title, s.author, s.description, s.url "
                    "FROM chunks c JOIN sources s ON s.id = c.source_id "
                    "WHERE c.library_id = :library_id AND (c.text LIKE :pattern OR s.title LIKE :pattern) "
                    "LIMIT :limit"
                ),
                {"library_id": library_id, "pattern": pattern, "limit": top_k},
            ).mappings().all()
            result = [self._match(row["chunk_id"], row, 0.5) for row in rows]
            self._remember(key, result)
            return result
        finally:
            db.close()

    @classmethod
    def invalidate(cls, library_id: str = "") -> None:
        if not library_id:
            cls._cache.clear()
            return
        for key in list(cls._cache):
            if key[1] == library_id:
                cls._cache.pop(key, None)

    @classmethod
    def _remember(cls, key: tuple, result: List[Dict[str, Any]]) -> None:
        cls._cache[key] = (time.monotonic(), result)
        cls._cache.move_to_end(key)
        while len(cls._cache) > cls._cache_size:
            cls._cache.popitem(last=False)

    @staticmethod
    def _match(chunk_id: str, row: Dict[str, Any], score: float) -> Dict[str, Any]:
        return {
            "id": chunk_id,
            "score": score,
            "metadata": {
                "chunk_id": chunk_id,
                "source_id": chunk_id.rsplit(":", 1)[0] if ":" in chunk_id else chunk_id,
                "extracted_knowledge": row.get("text") or "",
                "title": row.get("title") or "",
                "author": row.get("author") or "",
                "original_description": row.get("description") or "",
                "url": row.get("url") or "",
            },
        }
