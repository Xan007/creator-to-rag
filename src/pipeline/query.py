from typing import Any, Dict, List, Optional
from config.groups import get_post_ids_in_group, load_group_by_name, user_can_access_group

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
    group_name: Optional[str] = None,
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

    post_ids = None
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
    if group_name and user_id:
        group = load_group_by_name(user_id, group_name)
        if not group:
            raise ValueError(f"Group '{group_name}' not found for user.")
        if not user_can_access_group(user_id, group.id):
            raise ValueError(f"User does not have permission to access group '{group_name}'.")
        post_ids = get_post_ids_in_group(group.id)

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
        post_ids=post_ids,
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



