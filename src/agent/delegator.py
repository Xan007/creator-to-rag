import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from src.agent.intent import ArtifactIntent
from src.rag.artifacts import export_artifact

logger = logging.getLogger(__name__)


class AgentArtifactDelegator:
    @classmethod
    def process_and_export(
        cls,
        answer: str,
        sources: List[Dict[str, Any]],
        intent: ArtifactIntent,
        output_path: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        if not intent.should_generate:
            return None

        target_path = output_path or intent.suggested_filename
        try:
            exported_path = export_artifact(
                content=answer,
                output_path=target_path,
                title=intent.title,
                sources=sources,
            )
            return {
                "path": str(exported_path),
                "filename": Path(exported_path).name,
                "type": intent.artifact_type,
                "format": intent.output_format,
                "title": intent.title,
            }
        except Exception as e:
            logger.warning("Agent artifact export failed: %s", e)
            return None
