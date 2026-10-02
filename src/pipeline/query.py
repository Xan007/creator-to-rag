from typing import Any, Dict, List, Optional
_ENGINE = None


def _get_query_engine():
    global _ENGINE
    if _ENGINE is None:
        from src.rag.query_engine import QueryEngine
        _ENGINE = QueryEngine()
    return _ENGINE


def query_knowledge(
    question: str,
    creator: Optional[str] = None,
    library_id: Optional[str] = None,
    user_id: Optional[str] = None,
    *,
    top_k: int = 6,
    min_score: float = 0.25,
    mode: str = "grounded_plus",
    history: Optional[List[Dict[str, Any]]] = None,
    artifact_type: Optional[str] = None,
    export_path: Optional[str] = None,
) -> Dict[str, Any]:
    from src.agent.intent import ArtifactIntentDetector
    from src.agent.delegator import AgentArtifactDelegator

    if library_id and user_id:
        from storage.db import get_session
        import storage.repositories as repo
        db = get_session()
        try:
            library = repo.get_library(db, library_id)
            if not library or library.owner_id != user_id:
                raise ValueError("You do not have access to this library.")
        finally:
            db.close()
    intent = ArtifactIntentDetector.detect(
        query=question,
        explicit_artifact=artifact_type,
        explicit_export=export_path,
    )

    engine = _get_query_engine()
    result = engine.query(
        question=question,
        creator=creator,
        library_id=library_id,
        post_ids=None,
        top_k=top_k,
        min_score=min_score,
        mode=mode,
        history=history,
        artifact_type=intent.artifact_type,
    )

    if intent.should_generate and result.get("answer"):
        artifact_meta = AgentArtifactDelegator.process_and_export(
            answer=result["answer"],
            sources=result.get("sources", []),
            intent=intent,
            output_path=export_path,
        )
        if artifact_meta:
            result["artifact"] = artifact_meta

    return result


