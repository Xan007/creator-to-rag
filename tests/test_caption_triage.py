from src.analyzer.caption_triage import (
    CAPTION_INDEXED,
    FULL_INDEXED,
    heuristic_caption_verdict,
    resolve_ingest_plan,
    triage_caption,
)


def test_empty_and_generic_captions_are_thin():
    assert heuristic_caption_verdict("") == "thin"
    assert heuristic_caption_verdict("🔥") == "thin"
    assert heuristic_caption_verdict("link in bio") == "thin"
    assert heuristic_caption_verdict("#fyp #fitness") == "thin"


def test_detailed_caption_is_rich_without_llm():
    caption = (
        "Rutina Upper/Lower de 4 dias para hibridos. "
        "Upper A: press banca 4x8, remo con barra 4x10, elevaciones laterales 3x12. "
        "Lower A: sentadilla 4x6, peso muerto rumano 3x10. Descanso 90s entre series."
    )
    assert heuristic_caption_verdict(caption) == "rich"
    assert triage_caption(caption) == "rich"


def test_mid_length_caption_uses_llm(monkeypatch):
    monkeypatch.setattr(
        "src.analyzer.caption_triage._llm_caption_verdict",
        lambda description: "rich",
    )
    assert triage_caption("Hoy toca pierna con sentadillas y algo de core.") == "rich"


def test_llm_caption_verdict_uses_rag_client(monkeypatch):
    seen = {}

    class FakeClient:
        def generate(self, messages, *, model=None, temperature=0.0, json_mode=False):
            seen["model"] = model
            return "RICH"

    class FakeFactory:
        @staticmethod
        def get_client(stage="rag"):
            seen["stage"] = stage
            return FakeClient()

    monkeypatch.setenv("RAG_MODEL", "openai/gpt-oss-120b")
    monkeypatch.delenv("CAPTION_TRIAGE_MODEL", raising=False)
    monkeypatch.setattr("src.llm.factory.LLMClientFactory", FakeFactory)

    from src.analyzer.caption_triage import _llm_caption_verdict

    assert _llm_caption_verdict("Hoy toca pierna con sentadillas y algo de core.") == "rich"
    assert seen["stage"] == "rag"
    assert seen["model"] == "openai/gpt-oss-120b"


def test_llm_failure_defaults_to_thin(monkeypatch):
    monkeypatch.setattr(
        "src.analyzer.caption_triage.heuristic_caption_verdict",
        lambda description: None,
    )
    monkeypatch.setattr(
        "src.analyzer.caption_triage._llm_caption_verdict",
        lambda description: (_ for _ in ()).throw(RuntimeError("quota")),
    )
    assert triage_caption("algo intermedio sobre el video") == "thin"


def test_resolve_ingest_plan_flags():
    rich = "Press militar 4x8 con mancuernas, rest 2 min, espalda neutra y core apretado todo el set."
    should_download, status = resolve_ingest_plan(description=rich)
    assert should_download is False
    assert status == CAPTION_INDEXED

    should_download, status = resolve_ingest_plan(description=rich, caption_only=True)
    assert should_download is False
    assert status == CAPTION_INDEXED

    should_download, status = resolve_ingest_plan(description=rich, full_media=True)
    assert should_download is True
    assert status == FULL_INDEXED

    should_download, status = resolve_ingest_plan(
        description=rich, caption_only=True, full_media=True
    )
    assert should_download is True
    assert status == FULL_INDEXED

    should_download, status = resolve_ingest_plan(description="")
    assert should_download is True
    assert status == FULL_INDEXED


def test_rich_caption_does_not_need_downloader(monkeypatch):
    called = {"download": False}

    def fake_triage(description, platform=""):
        return "rich"

    monkeypatch.setattr("src.analyzer.caption_triage.triage_caption", fake_triage)
    should_download, status = resolve_ingest_plan(description="x" * 40)
    assert should_download is False
    assert status == CAPTION_INDEXED
    assert called["download"] is False
