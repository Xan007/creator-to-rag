"""Unit tests for the RAG query engine's pure helpers (offline)."""
import pytest

from src.rag.query_engine import QueryEngine


def _match(score, url="https://ig/p/A/", creator="creatorA", knowledge="k", caption=None):
    meta = {"url": url, "username": creator, "extracted_knowledge": knowledge}
    if caption is not None:
        meta["original_description"] = caption
    return {"score": score, "metadata": meta}


class TestBuildContext:
    def test_includes_caption_and_knowledge(self):
        context, sources, dropped = QueryEngine.build_context(
            [_match(0.9, caption="receta original")], min_score=0.35
        )
        assert "receta original" in context
        assert "Knowledge:" in context
        assert len(sources) == 1 and dropped == 0

    def test_drops_matches_below_min_score(self):
        _, sources, dropped = QueryEngine.build_context(
            [_match(0.9), _match(0.2, url="https://ig/p/B/")], min_score=0.35
        )
        assert len(sources) == 1
        assert dropped == 1

    def test_min_score_zero_keeps_everything(self):
        _, sources, _ = QueryEngine.build_context([_match(0.1)], min_score=0.0)
        assert len(sources) == 1

    def test_dedupes_by_url_keeping_first(self):
        _, sources, _ = QueryEngine.build_context(
            [_match(0.9, knowledge="first"), _match(0.95, knowledge="second")], min_score=0.0
        )
        assert len(sources) == 1

    def test_none_score_survives_when_threshold_set(self):
        # Pinecone may omit score for zero-vector edge cases; treat as keep.
        _, sources, dropped = QueryEngine.build_context([_match(None)], min_score=0.35)
        assert len(sources) == 1 and dropped == 0


class TestBuildPrompt:
    def test_strict_mode_has_no_general_escape_hatch(self):
        prompt = QueryEngine.build_prompt("q?", "CTX", "strict")
        assert "ONLY the provided context" in prompt
        assert "General (no proviene" not in prompt

    def test_grounded_plus_allows_labeled_addendum(self):
        prompt = QueryEngine.build_prompt("q?", "CTX", "grounded_plus")
        assert "General (no proviene de los creadores):" in prompt
        assert "Never attribute anything in that final block" in prompt

    def test_history_block_included_for_continuity(self):
        prompt = QueryEngine.build_prompt("q?", "CTX", "strict", history_block="User: hola\nAssistant: ey")
        assert "Conversation so far" in prompt
        assert "User: hola" in prompt

    def test_mode_validation_constant_in_sync(self):
        from src.rag.query_engine import MODES

        assert set(MODES) == {"strict", "grounded_plus"}


class TestAnnotateCitations:
    def test_flags_cited_and_uncited(self):
        sources = [{"creator": "a", "url": "u1"}, {"creator": "b", "url": "u2"}, {"creator": "c", "url": "u3"}]
        answer = "Flexiones [Source 1] y dominadas [Source 3]."
        result = QueryEngine.annotate_citations(answer, sources)
        assert [s["cited"] for s in result] == [True, False, True]
        assert result[0]["url"] == "u1"

    def test_no_citations_marks_all_false(self):
        sources = [{"creator": "a", "url": "u1"}, {"creator": "b", "url": "u2"}]
        result = QueryEngine.annotate_citations("No tengo esa información.", sources)
        assert all(s["cited"] is False for s in result)

    def test_grounded_answer_without_brackets_still_lists_sources(self):
        sources = [{"creator": "dominicantips", "url": "https://ig/p/1"}]
        answer = (
            "Aquí tienes una mini rutina de piernas con sentadilla búlgara "
            "y pistol squat, de fácil a difícil, usando solo tu cuerpo."
        )
        result = QueryEngine.annotate_citations(answer, sources)
        assert result[0]["cited"] is True

    def test_original_keys_preserved(self):
        result = QueryEngine.annotate_citations("[Source 1]", [{"creator": "x", "url": "u", "score": 0.9}])
        assert result[0]["score"] == 0.9 and result[0]["creator"] == "x" and result[0]["cited"] is True
