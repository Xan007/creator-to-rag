import pytest
from src.agent.intent import ArtifactIntentDetector, ArtifactIntent
from src.agent.delegator import AgentArtifactDelegator


def test_artifact_not_inferred_from_chat():
    intent = ArtifactIntentDetector.detect("Arma una rutina de torso y pierna de 4 dias en pdf")
    assert intent.should_generate is False
    assert intent.artifact_type is None


def test_artifact_explicit_type():
    intent = ArtifactIntentDetector.detect(
        "Arma una rutina de 4 dias",
        explicit_artifact="workout_plan",
    )
    assert intent.should_generate is True
    assert intent.artifact_type == "workout_plan"
    assert intent.output_format == "pdf"
    assert intent.title == "Plan de entrenamiento"


def test_artifact_explicit_markdown_export():
    intent = ArtifactIntentDetector.detect(
        "Lista de compras",
        explicit_artifact="grocery_list",
        explicit_export="compras.md",
    )
    assert intent.should_generate is True
    assert intent.artifact_type == "grocery_list"
    assert intent.output_format == "md"


def test_artifact_export_without_type_still_writes_file():
    intent = ArtifactIntentDetector.detect(
        "Dame recomendaciones de comida",
        explicit_export="notes.pdf",
    )
    assert intent.should_generate is True
    assert intent.artifact_type is None
    assert intent.suggested_filename == "notes.pdf"
    assert intent.title == "Documento"


def test_invalid_artifact_type_rejected():
    with pytest.raises(ValueError, match="artifact must be one of"):
        ArtifactIntentDetector.detect("x", explicit_artifact="podcast")


def test_agent_artifact_delegator(tmp_path):
    intent = ArtifactIntent(
        should_generate=True,
        artifact_type="workout_plan",
        output_format="pdf",
        suggested_filename=str(tmp_path / "test_delegated.pdf"),
        title="Plan de entrenamiento",
    )
    answer = "# Upper / lower\n\n## Day 1\n\n| Exercise | Sets x reps | Rest | Cue |\n|---|---|---|---|\n| Press | 4 x 8 | 2 min | Brace [Source 1] |"
    sources = [{"creator": "coach", "url": "https://instagram.com/p/1", "cited": True, "summary": "Press"}]

    res = AgentArtifactDelegator.process_and_export(
        answer=answer,
        sources=sources,
        intent=intent,
    )
    assert res is not None
    assert "test_delegated.pdf" in res["filename"]
    assert (tmp_path / "test_delegated.pdf").stat().st_size > 0
