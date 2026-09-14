from dataclasses import dataclass
from typing import Optional

VALID_ARTIFACT_TYPES = ("workout_plan", "recipe_book", "grocery_list")

ARTIFACT_TITLES = {
    "workout_plan": "Plan de entrenamiento",
    "recipe_book": "Receta",
    "grocery_list": "Lista de compras",
}


@dataclass
class ArtifactIntent:
    should_generate: bool
    artifact_type: Optional[str] = None
    output_format: str = "pdf"
    suggested_filename: str = "document.pdf"
    title: str = "Documento"


def normalize_artifact_type(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    key = value.strip().lower().replace("-", "_").replace(" ", "_")
    if key not in VALID_ARTIFACT_TYPES:
        raise ValueError(
            "artifact must be one of: " + ", ".join(VALID_ARTIFACT_TYPES)
        )
    return key


class ArtifactIntentDetector:
    """Build an export intent only from explicit flags, never from chat wording."""

    @classmethod
    def detect(
        cls,
        query: str = "",
        explicit_artifact: Optional[str] = None,
        explicit_export: Optional[str] = None,
    ) -> ArtifactIntent:
        if not explicit_artifact and not explicit_export:
            return ArtifactIntent(should_generate=False)

        artifact_type = normalize_artifact_type(explicit_artifact)
        output_format = "md" if (explicit_export or "").lower().endswith(".md") else "pdf"
        ext = ".md" if output_format == "md" else ".pdf"
        title = ARTIFACT_TITLES.get(artifact_type or "", "Documento")
        filename = explicit_export or f"{artifact_type or 'document'}{ext}"
        return ArtifactIntent(
            should_generate=True,
            artifact_type=artifact_type,
            output_format=output_format,
            suggested_filename=filename,
            title=title,
        )
