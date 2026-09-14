import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from google import genai
from pinecone import Pinecone
from config.env import getenv, load_runtime_env
from src.llm.factory import LLMClientFactory
from src.rag.artifacts import get_artifact_system_prompt
from src.rag.conversation import (
    build_history_block,
    normalize_history,
)
from src.rag.hybrid import HybridRetriever
from src.rag.lexical import LexicalRetriever

load_runtime_env()

logger = logging.getLogger(__name__)

INDEX_NAME = getenv("PINECONE_INDEX", "creatorrag")
EMBEDDING_MODEL = "gemini-embedding-001"

_CITATION_RE = re.compile(r"Source\s*(\d+)", re.IGNORECASE)

DEFAULT_TOP_K = 6
DEFAULT_MIN_SCORE = 0.25
MAX_CAPTION_CHARS = 600

MODES = ("strict", "grounded_plus")


_LOW_CONFIDENCE_ANSWER = (
    "No encontré información directa sobre eso en los posts o reels guardados de los creadores. "
    "¿Quieres que busquemos sobre otro ejercicio, tema o receta?"
)

_NATURAL_ASSISTANT_PROMPT = """You are an intelligent, friendly, and expert AI assistant that responds like a natural, helpful chat conversation (WhatsApp style).
Your knowledge comes from the Instagram posts and reels provided in the context.

Conversation Guidelines:
1. Answer accurately, clearly, and concisely in the same language as the user's question.
2. Avoid robotic phrasing: do not say "Based on the provided documents" or "In the context given".
3. Cite your sources with [Source N] sparingly and naturally only when giving specific recommendations or data from creators. Do not spam or overuse citations on every single line.
4. NEVER invent, paste, or repeat URLs or posts that are not in the context.
5. Balanced proactivity: If the user asks a purely factual question, answer directly and concisely. If they ask for advice, planning, or routines, naturally offer 1 or 2 helpful follow-up suggestions or next steps without being pushy."""

_STRICT_RULES = _NATURAL_ASSISTANT_PROMPT + """


Strict Instructions:
- Answer the user's question using ONLY the provided context.
- If the context does not contain the answer, say clearly that you don't have that information from the creators' content."""

_GROUNDED_PLUS_RULES = _STRICT_RULES + """

Grounded Plus Extension:
- If general knowledge would clearly help the user, append ONE short additional block introduced exactly by:
---
General (no proviene de los creadores):
followed by 1-3 plain sentences of widely accepted knowledge on the topic.
- Never attribute anything in that final block to the creators or to any [Source N]; it must be clearly separate.
- If your grounded answer already fully covers the question, omit the extra block entirely."""


from src.embeddings.factory import EmbeddingFactory

def _extract_brief_summary(knowledge: str, caption: str) -> str:
    text = (knowledge or "").strip() or (caption or "").strip()
    if not text:
        return "Contenido y recomendaciones del post"
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line or line.startswith(("#", "-", "*", "=")):
            continue
        cleaned = re.sub(r"\[Source\s*\d+[^\]]*\]", "", line).strip()
        if len(cleaned) >= 10:
            if len(cleaned) > 110:
                cleaned = cleaned[:107] + "..."
            return cleaned
    first_line = text.split("\n")[0].strip()
    return (first_line[:107] + "...") if len(first_line) > 110 else first_line


class QueryEngine:
    def __init__(self):
        pinecone_key = os.getenv("PINECONE_API_KEY")
        self.pc = Pinecone(api_key=pinecone_key) if pinecone_key else None
        self.index = self.pc.Index(INDEX_NAME) if self.pc else None

        self.embed_provider = EmbeddingFactory.get_provider()
        self.llm = LLMClientFactory.get_client(stage="rag")
        self.rag_model = os.getenv("RAG_MODEL")
        self.hybrid_retriever = HybridRetriever()
        self.lexical_retriever = LexicalRetriever()

    def _get_embedding(self, text: str) -> Optional[List[float]]:
        try:
            return self.embed_provider.get_embedding(text, task_type="query")
        except Exception as e:
            logger.warning("Embedding retrieval error (%s); falling back to BM25 local.", e)
            return None

    @staticmethod
    def build_context(matches: List[Dict[str, Any]], min_score: float) -> tuple:
        context_parts = []
        sources = []
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        dropped = 0
        for match in matches:
            meta = match.get("metadata", {})
            post_url = meta.get("url", "Unknown URL")
            score = match.get("score")
            if min_score is not None and score is not None and score < min_score:
                dropped += 1
                continue
            grouped.setdefault(post_url, []).append(match)

        for post_url, source_matches in grouped.items():
            source_matches = source_matches[:2]
            meta = source_matches[0].get("metadata", {})
            post_creator = meta.get("creator_username") or meta.get("author", "Unknown")
            source_title = meta.get("title", "")
            knowledge = "\n\n".join(
                m.get("metadata", {}).get("extracted_knowledge", "")
                for m in source_matches
                if m.get("metadata", {}).get("extracted_knowledge")
            )
            caption = meta.get("original_description", "")
            score = max((m.get("score") or 0.0 for m in source_matches), default=None)

            summary = _extract_brief_summary(knowledge, caption)
            part = f"[Source {len(sources) + 1}]\nCreator: @{post_creator}\nSource URL: {post_url}\n"
            if source_title:
                part += f"Title: {source_title}\n"
            if caption:
                part += f"Caption: {caption[:MAX_CAPTION_CHARS]}\n"
            part += f"Knowledge:\n{knowledge}\n"
            context_parts.append(part)
            sources.append({
                "creator": post_creator,
                "author": post_creator,
                "title": source_title,
                "url": post_url,
                "platform": meta.get("platform", ""),
                "source_id": meta.get("source_id") or meta.get("post_id"),
                "score": score,
                "summary": summary,
            })

        full_context = "\n---\n".join(context_parts)
        return full_context, sources, dropped


    @staticmethod
    def build_prompt(
        question: str,
        context: str,
        mode: str,
        history_block: str = "",
        artifact_type: Optional[str] = None,
    ) -> str:
        artifact_prompt = get_artifact_system_prompt(artifact_type)
        if artifact_prompt:
            rules = artifact_prompt
        else:
            rules = _STRICT_RULES if mode == "strict" else _GROUNDED_PLUS_RULES

        conversation_section = ""
        if history_block:
            conversation_section = f"Conversation so far (for continuity only; do not repeat it):\n{history_block}\n\n"

        return f"""{rules}

{conversation_section}Context from Creator Posts:
{context}

User Question:
{question}"""

    @staticmethod
    def annotate_citations(answer: str, sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        cited = set(_CITATION_RE.findall(answer))
        return [{**src, "cited": str(i) in cited} for i, src in enumerate(sources, start=1)]

    @staticmethod
    def sanitize_citations(answer: str, source_count: int) -> str:
        """Remove references to source numbers that were not supplied."""
        def replace(match: re.Match) -> str:
            number = int(match.group(1))
            return match.group(0) if 1 <= number <= source_count else ""

        return re.sub(r"\[Source\s*(\d+)\]", replace, answer or "", flags=re.IGNORECASE)

    def _condense_question(self, question: str, pairs: List[Tuple[str, str]]) -> str:
        if not pairs:
            return question.strip()

        history_text = "\n".join(f"{role.capitalize()}: {content}" for role, content in pairs)
        prompt = f"""Given the following conversation and a follow-up question, rephrase the follow-up question to be a standalone search query that contains all necessary context from previous turns. Do NOT answer the question. Only return the standalone question in the same language.

Conversation:
{history_text}

Follow-up Question: {question}

Standalone Question:"""

        try:
            condensed = self.llm.generate(
                messages=[{"role": "user", "content": prompt}],
                model=self.rag_model,
                temperature=0.0,
            )
            return condensed.strip() if condensed else question.strip()
        except Exception as e:
            logger.warning("Question condensation failed (%s). Using original question.", e)
            return question.strip()

    def query(
        self,
        question: str,
        creator: Optional[str] = None,
        library_id: Optional[str] = None,
        post_ids: Optional[List[str]] = None,
        top_k: int = DEFAULT_TOP_K,
        min_score: float = DEFAULT_MIN_SCORE,
        mode: str = "grounded_plus",
        history: Optional[List[Dict[str, Any]]] = None,
        artifact_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")

        pairs = normalize_history(history)
        timings: Dict[str, float] = {}
        search_query = self._condense_question(question, pairs)

        filter_dict: Optional[Dict[str, Any]] = None
        if library_id:
            filter_dict = {"library_id": {"$eq": library_id}}
        elif post_ids is not None:
            if not post_ids:
                return {
                    "answer": "Este grupo todavía no tiene posts indexados.",
                    "sources": [],
                    "mode": mode,
                }
            filter_dict = {"post_id": {"$in": post_ids}}
        elif creator:
            filter_dict = {"creator_username": {"$eq": creator}}

        started = time.perf_counter()
        query_vector = self._get_embedding(search_query)
        timings["embedding_ms"] = round((time.perf_counter() - started) * 1000, 2)
        dense_matches = []
        started = time.perf_counter()
        if query_vector is not None and self.index is not None:
            try:
                raw_k = max(top_k * 2, 10)
                results = self.index.query(
                    vector=query_vector,
                    top_k=raw_k,
                    include_metadata=True,
                    filter=filter_dict,
                )
                dense_matches = results.get("matches", [])
            except Exception as e:
                err_msg = str(e)
                if "does not match the dimension" in err_msg:
                    logger.info("Vector dimension (%d) differs from Pinecone index; relying on local BM25 retrieval.", len(query_vector))
                else:
                    logger.warning("Pinecone query notice: %s; using local BM25 retrieval.", e)
        timings["dense_ms"] = round((time.perf_counter() - started) * 1000, 2)



        local_documents: List[Dict[str, Any]] = []
        if library_id:
            started = time.perf_counter()
            local_documents = self.lexical_retriever.retrieve(search_query, library_id, top_k=max(top_k * 3, 20))
            timings["lexical_ms"] = round((time.perf_counter() - started) * 1000, 2)

        hybrid_matches = self.hybrid_retriever.retrieve(
            query=search_query,
            pinecone_matches=dense_matches,
            local_documents=local_documents,
            creator=creator,
            post_ids=post_ids,
            top_k=top_k,
        )

        if not hybrid_matches:
            response = {
                "answer": "No encontré posts relevantes en la base de datos para responder a tu consulta.",
                "sources": [],
                "mode": mode,
                "timings_ms": timings,
            }
            if pairs:
                response["standalone_question"] = search_query
            return response

        context, sources, _dropped = self.build_context(hybrid_matches, min_score=min_score)
        if not context:
            return {
                "answer": _LOW_CONFIDENCE_ANSWER,
                "sources": [],
                "mode": mode,
                "low_confidence": True,
                "timings_ms": timings,
                **({"standalone_question": search_query} if pairs else {}),
            }

        prompt = self.build_prompt(
            question,
            context,
            mode,
            history_block=build_history_block(pairs),
            artifact_type=artifact_type,
        )

        try:
            started = time.perf_counter()
            answer_text = self.llm.generate(
                messages=[{"role": "user", "content": prompt}],
                model=self.rag_model,
                temperature=0.3,
            )
            answer_text = self.sanitize_citations(answer_text, len(sources))
            timings["generation_ms"] = round((time.perf_counter() - started) * 1000, 2)
            result = {
                "answer": answer_text,
                "sources": self.annotate_citations(answer_text, sources),
                "mode": mode,
                "artifact_type": artifact_type,
                "timings_ms": timings,
            }
            if pairs:
                result["standalone_question"] = search_query
            return result
        except Exception as e:
            logger.error("RAG generation failed: %s", e)
            return {
                "answer": f"Error al generar respuesta: {e}",
                "sources": sources,
                "mode": mode,
            }

