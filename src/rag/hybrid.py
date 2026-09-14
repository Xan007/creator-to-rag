import logging
import re
from typing import Any, Dict, List, Optional
from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)

_WORD_RE = re.compile(r"\w+", re.UNICODE)


def tokenize(text: str) -> List[str]:
    return [w.lower() for w in _WORD_RE.findall(text or "")]


class HybridRetriever:
    def __init__(self, rrf_k: int = 60):
        self.rrf_k = rrf_k

    def retrieve(
        self,
        query: str,
        pinecone_matches: List[Dict[str, Any]],
        local_documents: Optional[List[Dict[str, Any]]] = None,
        creator: Optional[str] = None,
        post_ids: Optional[List[str]] = None,
        top_k: int = 6,
    ) -> List[Dict[str, Any]]:
        # Local documents are the lexical corpus for the whole library. Dense
        # retrieval is optional; lexical retrieval must still work during
        # outages, cold indexes, or provider changes.
        candidates = list(pinecone_matches or [])
        if local_documents:
            known = {
                (d.get("metadata", {}).get("chunk_id") or d.get("id"))
                for d in candidates
            }
            candidates.extend(
                d for d in local_documents
                if (d.get("metadata", {}).get("chunk_id") or d.get("id")) not in known
            )
        if not candidates:
            return []

        doc_by_id: Dict[str, Dict[str, Any]] = {}

        for m in candidates:
            meta = m.get("metadata", {})
            pid = meta.get("post_id") or meta.get("chunk_id") or m.get("id")
            if pid and pid not in doc_by_id:
                doc_by_id[pid] = m

        valid_docs = list(doc_by_id.values())
        if not valid_docs:
            return pinecone_matches[:top_k]

        tokenized_corpus = [
            tokenize(
                f"{d['metadata'].get('original_description', '')} {d['metadata'].get('extracted_knowledge', '')}"
            )
            for d in valid_docs
        ]
        tokenized_query = tokenize(query)

        bm25_ranked_ids: List[str] = []
        if local_documents:
            bm25_ranked_ids = [
                d.get("metadata", {}).get("post_id")
                or d.get("metadata", {}).get("chunk_id")
                or d.get("id")
                for d in local_documents
            ]
        elif any(tokenized_corpus) and tokenized_query:
            bm25 = BM25Okapi(tokenized_corpus)
            bm25_scores = bm25.get_scores(tokenized_query)
            scored_docs = [
                (
                    valid_docs[i]["metadata"].get("post_id")
                    or valid_docs[i]["metadata"].get("chunk_id")
                    or valid_docs[i]["id"],
                    score,
                )
                for i, score in enumerate(bm25_scores)
                if score > 0.0
            ]
            # BM25's IDF can legitimately be zero for a tiny corpus where a
            # term appears in half of the documents. Preserve lexical
            # retrieval in that common cold-start case with overlap ranking.
            if not scored_docs:
                query_terms = set(tokenized_query)
                scored_docs = [
                    (
                valid_docs[i]["metadata"].get("post_id")
                or valid_docs[i]["metadata"].get("chunk_id")
                or valid_docs[i]["id"],
                        float(len(query_terms.intersection(set(tokens)))),
                    )
                    for i, tokens in enumerate(tokenized_corpus)
                    if query_terms.intersection(tokens)
                ]
            scored_docs.sort(key=lambda x: x[1], reverse=True)
            bm25_ranked_ids = [doc_id for doc_id, _ in scored_docs]

        dense_ranked_ids: List[str] = [
            m.get("metadata", {}).get("post_id")
            or m.get("metadata", {}).get("chunk_id")
            or m.get("id")
            for m in pinecone_matches
        ]

        rrf_scores: Dict[str, float] = {}

        for rank, doc_id in enumerate(dense_ranked_ids):
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + (1.0 / (self.rrf_k + (rank + 1)))

        for rank, doc_id in enumerate(bm25_ranked_ids):
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + (1.0 / (self.rrf_k + (rank + 1)))

        sorted_doc_ids = sorted(rrf_scores.keys(), key=lambda did: rrf_scores[did], reverse=True)

        final_matches: List[Dict[str, Any]] = []
        for did in sorted_doc_ids[:top_k]:
            doc = doc_by_id.get(did)
            if doc:
                normalized_score = min(1.0, rrf_scores[did] * 30.0)
                final_matches.append({
                    "id": doc.get("id", did),
                    "score": normalized_score,
                    "metadata": doc.get("metadata", {}),
                })

        return final_matches if final_matches else pinecone_matches[:top_k]
