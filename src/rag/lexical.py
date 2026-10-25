"""Persistent lexical retrieval.

SQLite uses FTS5 so the corpus is indexed once and queried in the database.
Other SQL backends use a bounded LIKE fallback until a native full-text
backend is configured.
"""

import re
import threading
import time
from collections import OrderedDict
from typing import Any, Dict, List

from sqlalchemy import text

from storage.db import get_session


_STOPWORDS = {
    "a", "al", "algo", "algunas", "algunos", "ante", "antes", "como", "con", "contra",
    "cual", "cuales", "cuando", "de", "del", "desde", "donde", "durante", "e", "el",
    "ella", "ellas", "ellos", "en", "entre", "era", "erais", "eran", "eras", "eres",
    "es", "esa", "esas", "ese", "eso", "esos", "esta", "estas", "este", "esto", "estos",
    "estoy", "fue", "fueron", "fui", "fuimos", "ha", "hace", "hacen", "hacer", "hacia",
    "han", "has", "hasta", "hay", "la", "las", "le", "les", "lo", "los", "me", "mi",
    "mis", "mucho", "muchos", "muy", "mas", "nos", "nosotros", "o", "otra", "otras",
    "otro", "otros", "para", "pero", "poco", "por", "porque", "que", "quien", "quienes",
    "se", "sea", "sean", "segun", "ser", "si", "sido", "siempre", "sin", "sobre", "sois",
    "somos", "son", "soy", "su", "sus", "suya", "suyas", "suyo", "suyos", "tal", "tales",
    "tambien", "tanto", "te", "tendra", "tendran", "teneis", "tenemos", "tener", "tenga",
    "tengan", "tengo", "tenia", "tenian", "ti", "tiene", "tienen", "toda", "todas", "todo",
    "todos", "tu", "tus", "un", "una", "unas", "uno", "unos", "vosostras", "vosotros",
    "vuestra", "vuestras", "vuestro", "vuestros", "y", "ya", "yo",
    "cómo", "qué", "cuál", "cuáles", "cuándo", "dónde", "quién", "quiénes", "más", "según",
    "the", "an", "and", "or", "in", "on", "at", "to", "for", "of", "with", "by",
    "is", "are", "was", "were", "be", "been", "have", "has", "had", "do", "does", "did",
    "how", "what", "which", "who", "whom", "where", "when", "why", "can", "could", "will"
}


def _fts_query(query: str) -> str:
    terms = [term.replace('"', "") for term in re.findall(r"[\wÀ-ÿ]+", query.lower())]
    filtered = [t for t in terms if t not in _STOPWORDS and len(t) > 1]
    tokens = filtered[:16] if filtered else terms[:16]
    if not tokens:
        return ""
    return " OR ".join(f'"{t}"' for t in tokens)


class LexicalRetriever:
    _cache: "OrderedDict[tuple, tuple[float, List[Dict[str, Any]]]]" = OrderedDict()
    _cache_lock = threading.Lock()
    _cache_ttl = 30.0
    _cache_size = 256

    def retrieve(self, query: str, library_id: str, top_k: int = 12) -> List[Dict[str, Any]]:
        if not query.strip() or not library_id:
            return []
        key = (query.strip().lower(), library_id, top_k)
        with self._cache_lock:
            cached = self._cache.get(key)
            if cached and time.monotonic() - cached[0] < self._cache_ttl:
                return [dict(item) for item in cached[1]]
        db = get_session()
        try:
            lib_row = db.execute(
                text("SELECT id, slug FROM libraries WHERE id = :lid OR slug = :lid"),
                {"lid": library_id}
            ).fetchone()
            resolved_lids = [library_id]
            if lib_row:
                resolved_lids = list({str(lib_row[0]), str(lib_row[1])})

            dialect = db.get_bind().dialect.name if db.get_bind() else "sqlite"
            if dialect == "sqlite":
                expression = _fts_query(query)
                if not expression:
                    return []
                placeholders = ", ".join(f":lid_{idx}" for idx in range(len(resolved_lids)))
                params = {"query": expression, "limit": top_k}
                for idx, lid in enumerate(resolved_lids):
                    params[f"lid_{idx}"] = lid
                rows = db.execute(
                    text(
                        f"SELECT chunk_id, text, title, author, description, url, bm25(chunks_fts) AS rank "
                        f"FROM chunks_fts WHERE chunks_fts MATCH :query AND library_id IN ({placeholders}) "
                        f"ORDER BY rank LIMIT :limit"
                    ),
                    params,
                ).mappings().all()
                result = [
                    self._match(row["chunk_id"], row, float(abs(row["rank"] or 0.0)))
                    for row in rows
                ]
                self._remember(key, result)
                return result

            if dialect == "postgresql":
                placeholders = ", ".join(f":lid_{idx}" for idx in range(len(resolved_lids)))
                params = {"query": query, "limit": top_k}
                for idx, lid in enumerate(resolved_lids):
                    params[f"lid_{idx}"] = lid
                rows = db.execute(
                    text(
                        f"SELECT c.id AS chunk_id, c.text, s.title, s.author, s.description, s.url, "
                        f"ts_rank_cd(to_tsvector('simple', concat_ws(' ', c.text, s.title, s.author, s.description)), "
                        f"plainto_tsquery('simple', :query)) AS rank "
                        f"FROM chunks c JOIN sources s ON s.id = c.source_id "
                        f"JOIN library_sources ls ON ls.source_id = c.source_id "
                        f"WHERE ls.library_id IN ({placeholders}) "
                        f"AND to_tsvector('simple', concat_ws(' ', c.text, s.title, s.author, s.description)) "
                        f"@@ plainto_tsquery('simple', :query) "
                        f"ORDER BY rank DESC LIMIT :limit"
                    ),
                    params,
                ).mappings().all()
                result = [self._match(row["chunk_id"], row, float(row["rank"] or 0.0)) for row in rows]
                self._remember(key, result)
                return result

            # Safe bounded fallback for other development databases.
            placeholders = ", ".join(f":lid_{idx}" for idx in range(len(resolved_lids)))
            pattern = f"%{query.strip()[:120]}%"
            params = {"pattern": pattern, "limit": top_k}
            for idx, lid in enumerate(resolved_lids):
                params[f"lid_{idx}"] = lid
            rows = db.execute(
                text(
                    f"SELECT c.id AS chunk_id, c.text, s.title, s.author, s.description, s.url "
                    f"FROM chunks c JOIN sources s ON s.id = c.source_id "
                    f"WHERE c.library_id IN ({placeholders}) AND (c.text LIKE :pattern OR s.title LIKE :pattern) "
                    f"LIMIT :limit"
                ),
                params,
            ).mappings().all()
            result = [self._match(row["chunk_id"], row, 0.5) for row in rows]
            self._remember(key, result)
            return result
        finally:
            db.close()

    @classmethod
    def invalidate(cls, library_id: str = "") -> None:
        with cls._cache_lock:
            if not library_id:
                cls._cache.clear()
                return
            for key in list(cls._cache):
                if key[1] == library_id:
                    cls._cache.pop(key, None)

    @classmethod
    def _remember(cls, key: tuple, result: List[Dict[str, Any]]) -> None:
        with cls._cache_lock:
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
